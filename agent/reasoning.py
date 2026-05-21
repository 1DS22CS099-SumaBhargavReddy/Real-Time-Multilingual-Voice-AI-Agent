import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from openai import OpenAI

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.prompt import SYSTEM_PROMPT
from agent.tools import TOOL_MAP, AGENT_TOOLS_SCHEMA
from services.language_detection import detect_language
from memory.session_memory import SessionState, session_memory
from memory.persistent_memory import get_patient_profile, update_patient_profile

def get_current_date_context():
    now = datetime.now()
    return f"Today's date is {now.strftime('%Y-%m-%d')}, day is {now.strftime('%A')}."

class OfflineSimulatorAgent:
    """
    Heuristics-based simulator that reads transcripts, performs tool tasks,
    updates SQLite database, and returns conversational Hindi/Tamil/English responses.
    Allows complete offline execution of the appointment system with <100ms latency.
    """
    def __init__(self, state: SessionState):
        self.state = state

    def process(self, text: str) -> dict:
        text_lower = text.lower()
        lang = self.state.language
        
        # Keep track of active thinking logs to stream to the UI
        thinking_logs = []
        start_time = time.time()
        
        # Load persistent memory if available
        profile = get_patient_profile(self.state.patient_id)
        if profile:
            self.state.patient_name = profile["name"]
            if profile["preferred_language"]:
                self.state.language = profile["preferred_language"]
                lang = profile["preferred_language"]
                
        # Resolve doctor mentioned
        doc_id = self.state.doctor_id
        doc_name = self.state.doctor_name
        if "sharma" in text_lower or "cardiologist" in text_lower or "dil" in text_lower:
            doc_id, doc_name = 1, "Dr. Ramesh Sharma"
        elif "patel" in text_lower or "dermatologist" in text_lower or "skin" in text_lower or "twacha" in text_lower:
            doc_id, doc_name = 2, "Dr. Priya Patel"
        elif "raja" in text_lower or "ortho" in text_lower or "bone" in text_lower or "elumbu" in text_lower:
            doc_id, doc_name = 3, "Dr. Karthik Raja"
        elif "krishnan" in text_lower or "pediatrician" in text_lower or "child" in text_lower or "bacche" in text_lower or "kuzhandhai" in text_lower:
            doc_id, doc_name = 4, "Dr. Anjali Krishnan"
            
        if doc_id:
            self.state.update(doctor_id=doc_id, doctor_name=doc_name)

        # Parse Date/Time heuristics
        date_val = self.state.date
        time_val = self.state.time
        
        # Date parser
        today = datetime.now()
        if "tomorrow" in text_lower or "kal" in text_lower or "naalai" in text_lower:
            date_val = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "today" in text_lower or "aaj" in text_lower or "inniku" in text_lower:
            date_val = today.strftime("%Y-%m-%d")
        elif "day after tomorrow" in text_lower or "parso" in text_lower:
            date_val = (today + timedelta(days=2)).strftime("%Y-%m-%d")
        else:
            # Extract date regex YYYY-MM-DD
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text_lower)
            if date_match:
                date_val = date_match.group(1)
                
        # Time parser (e.g. "10:30", "10 am", "10 baje")
        time_match = re.search(r'(\d{1,2})[:.](\d{2})', text_lower)
        if time_match:
            time_val = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"
        elif "10" in text_lower:
            time_val = "10:00"
        elif "11" in text_lower:
            time_val = "11:00"
        elif "12" in text_lower:
            time_val = "12:00"
        elif "2" in text_lower or "two" in text_lower:
            time_val = "14:00"
        elif "3" in text_lower or "three" in text_lower:
            time_val = "15:00"
        elif "4" in text_lower or "four" in text_lower:
            time_val = "16:00"

        if date_val or time_val:
            self.state.update(date=date_val, time=time_val)

        # Detect intent
        intent = self.state.intent
        if any(w in text_lower for w in ["book", "appointment", "milna", "parkanum", "schedule"]):
            intent = "book"
        elif any(w in text_lower for w in ["reschedule", "change", "badalna", "matra", "move"]):
            intent = "reschedule"
        elif any(w in text_lower for w in ["cancel", "delete", "hatao", "radd", "panna"]):
            intent = "cancel"
            
        if intent:
            self.state.update(intent=intent)

        response_text = ""
        tool_was_called = None
        tool_result = None

        # Process Booking Heuristic
        if self.state.intent == "book":
            if not self.state.doctor_id:
                thinking_logs.append("No doctor specified. Requesting doctor details.")
                response_text = {
                    "English": "Which doctor or specialty would you like to book with? We have Dr. Sharma (Cardiologist), Dr. Patel (Dermatologist), Dr. Raja (Orthopedician), and Dr. Krishnan (Pediatrician).",
                    "Hindi": "आप किस डॉक्टर से मिलना चाहते हैं? हमारे पास डॉक्टर शर्मा (हृदय रोग विशेषज्ञ) और डॉक्टर पटेल (त्वचा विशेषज्ञ) हैं।",
                    "Tamil": "நீங்கள் எந்த மருத்துவரை பார்க்க வேண்டும்? டாக்டர் கார்த்திக் ராஜா அல்லது டாக்டர் அஞ்சலி கிருஷ்ணன் இருக்கிறார்கள்."
                }.get(lang)
            elif not self.state.date or not self.state.time:
                thinking_logs.append(f"Doctor identified: {self.state.doctor_name}. Missing date/time. Asking patient.")
                response_text = {
                    "English": f"Sure, booking with {self.state.doctor_name}. What date and time works best for you?",
                    "Hindi": f"ठीक है, {self.state.doctor_name} के साथ। आप किस तारीख और समय पर मिलना चाहेंगे?",
                    "Tamil": f"நிச்சயமாக, {self.state.doctor_name} உடன். எந்த தேதி மற்றும் நேரம் உங்களுக்கு வசதியாக இருக்கும்?"
                }.get(lang)
            else:
                # We have all details, attempt to book
                thinking_logs.append(f"Executing book_appointment tool for doctor_id={self.state.doctor_id}, date={self.state.date}, time={self.state.time}")
                tool_was_called = "book_appointment"
                tool_result = TOOL_MAP["book_appointment"](
                    self.state.patient_id, 
                    self.state.doctor_id, 
                    self.state.date, 
                    self.state.time
                )
                
                if tool_result["status"] == "success":
                    thinking_logs.append("Booking successful. Clearing session context.")
                    response_text = {
                        "English": f"Your appointment is confirmed with {self.state.doctor_name} on {self.state.date} at {self.state.time}.",
                        "Hindi": f"आपका अपॉइंटमेंट {self.state.doctor_name} के साथ {self.state.date} को {self.state.time} बजे बुक हो गया है।",
                        "Tamil": f"{self.state.doctor_name} உடன் உங்கள் அப்பாயிண்ட்மெண்ட் {self.state.date} அன்று {self.state.time} மணிக்கு உறுதியானது."
                    }.get(lang)
                    # Clear session booking parameters, but save language
                    self.state.update(intent=None, doctor_id=None, doctor_name=None, date=None, time=None)
                else:
                    # Collision or out of operating hours
                    thinking_logs.append(f"Slot conflict: {tool_result['message']}. Generating alternatives.")
                    alts = tool_result.get("alternatives", [])
                    self.state.update(alternatives_offered=alts)
                    
                    if alts:
                        alt_strs = [f"{a[0]} at {a[1]}" for a in alts]
                        alt_str = " or ".join(alt_strs[:2])
                        
                        response_text = {
                            "English": f"I'm sorry, {self.state.doctor_name} is unavailable then. Would {alt_str} work instead?",
                            "Hindi": f"क्षमा करें, उस समय {self.state.doctor_name} उपलब्ध नहीं हैं। क्या आप {alt_str} पर आ सकते हैं?",
                            "Tamil": f"மன்னிக்கவும், அந்த நேரத்தில் {self.state.doctor_name} வர முடியாது. அதற்கு பதிலாக {alt_str} வரலாமா?"
                        }.get(lang)
                    else:
                        response_text = {
                            "English": f"I'm sorry, {self.state.doctor_name} has no available slots on that day. Could we try another date?",
                            "Hindi": f"क्षमा करें, उस दिन {self.state.doctor_name} के पास कोई स्लॉट नहीं है। क्या हम कोई और दिन चुन सकते हैं?",
                            "Tamil": f"மன்னிக்கவும், அந்த நாளில் {self.state.doctor_name} இடம் இல்லை. வேறு தேதியை முயற்சிக்கலாமா?"
                        }.get(lang)

        # Process Rescheduling Heuristic
        elif self.state.intent == "reschedule":
            # Check if patient has any active appointments
            thinking_logs.append("Fetching active appointments for patient to reschedule.")
            appts_res = TOOL_MAP["get_patient_appointments"](self.state.patient_id)
            appts = appts_res.get("appointments", [])
            
            if not appts:
                thinking_logs.append("No active appointments found.")
                response_text = {
                    "English": "You don't have any active appointments to reschedule. Would you like to book a new one?",
                    "Hindi": "आपके पास रीशेड्यूल करने के लिए कोई अपॉइंटमेंट नहीं है। क्या आप नया बुक करना चाहते हैं?",
                    "Tamil": "மாற்றுவதற்கு உங்களிடம் எந்த அப்பாயிண்ட்மெண்ட்டும் இல்லை. புதியதை பதிவு செய்யலாமா?"
                }.get(lang)
                self.state.update(intent=None)
            elif not self.state.date or not self.state.time:
                # Ask where to reschedule
                appt = appts[0]
                self.state.update(appointment_id=appt["id"])
                thinking_logs.append(f"Selected appointment ID={appt['id']}. Requesting new date/time.")
                response_text = {
                    "English": f"You have an appointment with {appt['doctor_name']} on {appt['date']} at {appt['time']}. What new date and time would you like?",
                    "Hindi": f"आपका अपॉइंटमेंट {appt['doctor_name']} के साथ {appt['date']} को {appt['time']} बजे है। आप इसे किस नई तारीख या समय पर बदलना चाहते हैं?",
                    "Tamil": f"{appt['doctor_name']} உடன் உங்களுக்கு {appt['date']} அன்று {appt['time']} மணிக்கு ஒரு அப்பாயிண்ட்மெண்ட் உள்ளது. அதை எப்போது மாற்ற வேண்டும்?"
                }.get(lang)
            else:
                # Attempt to reschedule
                appt_id = self.state.appointment_id or appts[0]["id"]
                thinking_logs.append(f"Executing reschedule_appointment tool for ID={appt_id}, new date={self.state.date}, new time={self.state.time}")
                tool_was_called = "reschedule_appointment"
                tool_result = TOOL_MAP["reschedule_appointment"](appt_id, self.state.date, self.state.time)
                
                if tool_result["status"] == "success":
                    thinking_logs.append("Rescheduling successful.")
                    response_text = {
                        "English": f"Your appointment has been successfully rescheduled to {self.state.date} at {self.state.time}.",
                        "Hindi": f"आपका अपॉइंटमेंट बदल दिया गया है, अब यह {self.state.date} को {self.state.time} बजे होगा।",
                        "Tamil": f"உங்கள் அப்பாயிண்ட்மெண்ட் வெற்றிகரமாக {self.state.date} அன்று {self.state.time} மணிக்கு மாற்றப்பட்டது."
                    }.get(lang)
                    self.state.update(intent=None, date=None, time=None, appointment_id=None)
                else:
                    thinking_logs.append(f"Rescheduling conflict: {tool_result['message']}. Generating alternatives.")
                    alts = tool_result.get("alternatives", [])
                    self.state.update(alternatives_offered=alts)
                    if alts:
                        alt_strs = [f"{a[0]} at {a[1]}" for a in alts]
                        alt_str = " or ".join(alt_strs[:2])
                        response_text = {
                            "English": f"That slot is not available. Would {alt_str} work instead?",
                            "Hindi": f"वह स्लॉट खाली नहीं है। क्या {alt_str} समय ठीक रहेगा?",
                            "Tamil": f"அந்த நேரம் கிடைக்கவில்லை. அதற்கு பதிலாக {alt_str} வரலாமா?"
                        }.get(lang)
                    else:
                        response_text = {
                            "English": "The doctor is not available at that time. Let's try a different time.",
                            "Hindi": "डॉक्टर उस समय उपलब्ध नहीं हैं। कोई और समय प्रयास करें।",
                            "Tamil": "அந்த நேரத்தில் மருத்துவர் வர முடியாது. வேறு நேரத்தை முயற்சிக்கவும்."
                        }.get(lang)

        # Process Cancellation Heuristic
        elif self.state.intent == "cancel":
            thinking_logs.append("Fetching active appointments to cancel.")
            appts_res = TOOL_MAP["get_patient_appointments"](self.state.patient_id)
            appts = appts_res.get("appointments", [])
            
            if not appts:
                thinking_logs.append("No active appointments found to cancel.")
                response_text = {
                    "English": "You do not have any active appointments to cancel.",
                    "Hindi": "आपके पास रद्द करने के लिए कोई एक्टिव अपॉइंटमेंट नहीं है।",
                    "Tamil": "ரத்து செய்ய உங்களிடம் எந்த அப்பாயிண்ட்மெண்ட்டும் இல்லை."
                }.get(lang)
                self.state.update(intent=None)
            else:
                appt = appts[0]
                thinking_logs.append(f"Executing cancel_appointment tool for ID={appt['id']}.")
                tool_was_called = "cancel_appointment"
                tool_result = TOOL_MAP["cancel_appointment"](appt["id"])
                
                response_text = {
                    "English": f"Your appointment with {appt['doctor_name']} on {appt['date']} has been cancelled.",
                    "Hindi": f"{appt['doctor_name']} के साथ आपका {appt['date']} का अपॉइंटमेंट रद्द कर दिया गया है।",
                    "Tamil": f"{appt['doctor_name']} உடன் {appt['date']} அன்று இருந்த உங்கள் அப்பாயிண்ட்மெண்ட் ரத்து செய்யப்பட்டது."
                }.get(lang)
                self.state.update(intent=None)

        # Default Greeting Heuristics
        else:
            thinking_logs.append("Greeting patient using past preferences.")
            past_doc = profile["doctor_name"] if profile and profile.get("doctor_name") else "Dr. Ramesh Sharma"
            response_text = {
                "English": f"Hello {self.state.patient_name}, welcome to 2Care Clinical scheduler. Would you like to book an appointment with {past_doc} today?",
                "Hindi": f"नमस्ते {self.state.patient_name}, 2Care क्लिनिक में आपका स्वागत है। क्या आप {past_doc} के साथ अपॉइंटमेंट बुक करना चाहते हैं?",
                "Tamil": f"வணக்கம் {self.state.patient_name}, 2Care மருத்துவமனைக்கு உங்களை வரவேற்கிறோம். இன்று {past_doc} உடன் அப்பாயிண்ட்மெண்ட் புக் செய்யலாமா?"
            }.get(lang)

        latency_ms = (time.time() - start_time) * 1000
        
        # Log to console
        print(f"[REASONING] Simulated reasoning completed in {latency_ms:.2f}ms. Logs: {thinking_logs}")
        
        return {
            "response": response_text,
            "language": lang,
            "tool_called": tool_was_called,
            "tool_result": tool_result,
            "thinking_logs": thinking_logs,
            "latency_ms": latency_ms
        }

def run_agent_reasoning(session_id: str, text: str, api_key: str = None) -> dict:
    """
    Translates user text into action. 
    Routes requests to OpenAI API (with tool calls) or the Offline Heuristic Agent.
    """
    state = session_memory.get_session(session_id)
    
    # 1. Update language based on the query text
    detected_lang = detect_language(text)
    state.update(language=detected_lang)
    
    # 2. Add to session history
    state.history.append({"role": "user", "content": text})

    # --- Live API Mode (OpenAI Tool Calling) ---
    if api_key and api_key.strip():
        try:
            client = OpenAI(api_key=api_key)
            start_time = time.time()
            thinking_logs = ["Invoking OpenAI ChatCompletion with Tool Calling."]
            
            # Format history for LLM
            messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n" + get_current_date_context()}]
            # Load persistent memory notes
            profile = get_patient_profile(state.patient_id)
            if profile:
                messages.append({
                    "role": "system", 
                    "content": f"Patient Persistent Context: Name: {profile['name']}, Lang: {profile['preferred_language']}, Notes: {profile['notes']}. Preferred Doc: {profile.get('doctor_name')}."
                })
                
            # Limit history to last 6 messages
            for h in state.history[-6:]:
                messages.append(h)
                
            # Call OpenAI API
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Very fast reasoning model
                messages=messages,
                tools=[{"type": "function", "function": t} for t in AGENT_TOOLS_SCHEMA],
                tool_choice="auto",
                temperature=0.2
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls
            tool_was_called = None
            tool_result = None

            # Handle LLM Tool Calling
            if tool_calls:
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    thinking_logs.append(f"LLM requested tool call: {function_name} with arguments: {function_args}")
                    
                    # Execute tool
                    if function_name in TOOL_MAP:
                        tool_was_called = function_name
                        tool_func = TOOL_MAP[function_name]
                        tool_result = tool_func(**function_args)
                        
                        # Add tool result to LLM context and make final call
                        messages.append(response_message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": json.dumps(tool_result)
                        })
                        
                        thinking_logs.append(f"Tool executed. Result: {tool_result}")
                        
                        # Make the second OpenAI call
                        second_response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=messages
                        )
                        final_text = second_response.choices[0].message.content
                        thinking_logs.append("Final LLM response generated.")
                    else:
                        final_text = "I am having difficulty executing that tool."
            else:
                final_text = response_message.content
                thinking_logs.append("LLM responded directly without tool call.")
                
            # Update state with variables that LLM may have set/changed
            # We run a lightweight regex match to sync local state variables 
            # (so the UI updates dynamically with the values LLM determined)
            # In a production app, we would have the LLM return structured updates.
            # Here we sync variables by parsing the final_text or tool args.
            if tool_calls:
                args = json.loads(tool_calls[0].function.arguments)
                if "doctor_id" in args:
                    state.update(doctor_id=args["doctor_id"])
                if "date" in args:
                    state.update(date=args["date"])
                if "time" in args:
                    state.update(time=args["time"])
                if "new_time" in args:
                    state.update(time=args["new_time"])
                if "appointment_id" in args:
                    state.update(appointment_id=args["appointment_id"])
                    
            state.history.append({"role": "assistant", "content": final_text})
            latency_ms = (time.time() - start_time) * 1000
            
            return {
                "response": final_text,
                "language": state.language,
                "tool_called": tool_was_called,
                "tool_result": tool_result,
                "thinking_logs": thinking_logs,
                "latency_ms": latency_ms
            }
            
        except Exception as e:
            print(f"[REASONING] Live OpenAI reasoning failed: {e}. Falling back to Simulator.")
            # Fall back to simulation on error
            
    # --- Offline Simulator Agent (Heuristic matching) ---
    simulator = OfflineSimulatorAgent(state)
    res = simulator.process(text)
    
    # Save response to history
    state.history.append({"role": "assistant", "content": res["response"]})
    return res

if __name__ == "__main__":
    # Test simulator agent
    print("Testing Offline Simulator:")
    res1 = run_agent_reasoning("test_session_1", "I want to see a cardiologist tomorrow at 11:00 AM")
    print("Response 1:", res1["response"])
    print("State:", session_memory.get_session("test_session_1").to_dict())
    
    # Check booking triggers
    res2 = run_agent_reasoning("test_session_1", "Yes, go ahead and book it.")
    print("\nResponse 2:", res2["response"])
