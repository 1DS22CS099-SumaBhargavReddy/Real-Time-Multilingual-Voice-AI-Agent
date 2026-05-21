import asyncio
import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Optional
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from memory.session_memory import session_memory
from memory.persistent_memory import get_patient_profile, update_patient_profile
from services.speech_to_text import transcribe_audio_bytes
from services.text_to_speech import text_to_speech
from agent.reasoning import run_agent_reasoning

router = APIRouter()

# Outbound campaign queue
# Maps patient_id -> {"doctor_id": int, "script": str, "language": str}
OUTBOUND_QUEUE: Dict[str, dict] = {}

def queue_outbound_call(patient_id: str, doctor_id: int, script: str, language: str):
    OUTBOUND_QUEUE[patient_id] = {
        "doctor_id": doctor_id,
        "script": script,
        "language": language
    }
    print(f"[OUTBOUND] Call queued for patient {patient_id}. Script: '{script}'")

@router.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Query parameters
    params = websocket.query_params
    session_id = params.get("session_id", f"sess_{int(time.time())}")
    patient_id = params.get("patient_id", "P101")
    api_key = params.get("api_key", None)
    
    print(f"[WS] Client connected. Session: {session_id}, Patient: {patient_id}")
    
    state = session_memory.get_session(session_id)
    state.update(patient_id=patient_id)
    
    # Initialize patient details in state
    profile = get_patient_profile(patient_id)
    if profile:
        state.update(
            patient_name=profile["name"],
            language=profile["preferred_language"] or "English"
        )
        
    audio_buffer = bytearray()
    
    try:
        # Check if there is an active outbound campaign queued for this patient
        if patient_id in OUTBOUND_QUEUE:
            campaign = OUTBOUND_QUEUE.pop(patient_id)
            print(f"[WS] Triggering outbound campaign for {patient_id}")
            
            # Greet user with campaign message first
            greeting_text = campaign["script"]
            state.update(
                language=campaign["language"],
                doctor_id=campaign["doctor_id"],
                intent="reschedule" if "reschedule" in greeting_text.lower() or "change" in greeting_text.lower() else "book"
            )
            
            # Send state sync
            await websocket.send_json({
                "type": "state",
                "state": state.to_dict()
            })
            
            # Generate greeting TTS
            await websocket.send_json({"type": "thinking", "log": "Synthesizing campaign greeting..."})
            tts_start = time.time()
            greeting_audio = await text_to_speech(greeting_text, state.language, api_key)
            tts_latency = (time.time() - tts_start) * 1000
            
            await websocket.send_json({
                "type": "agent_response",
                "text": greeting_text,
                "audio_len": len(greeting_audio)
            })
            
            # Send audio chunk
            await websocket.send_bytes(greeting_audio)
            
            # Add to transcript history
            state.history.append({"role": "assistant", "content": greeting_text})
            
            # Send latency report
            await websocket.send_json({
                "type": "latency",
                "metrics": {
                    "stt": 0.0,
                    "llm": 0.0,
                    "tts": tts_latency,
                    "network": 20.0,
                    "total": tts_latency + 20.0
                }
            })
        else:
            # Inbound call: greet the patient
            greeting_text = {
                "English": f"Hello {state.patient_name}, welcome to 2Care Clinic. How can I help you manage your appointments today?",
                "Hindi": f"नमस्ते {state.patient_name}, 2Care क्लिनिक में आपका स्वागत है। आज मैं आपके अपॉइंटमेंट प्रबंधन में क्या सहायता कर सकता हूँ?",
                "Tamil": f"வணக்கம் {state.patient_name}, 2Care மருத்துவமனைக்கு உங்களை வரவேற்கிறோம். இன்று உங்கள் அப்பாயிண்ட்மெண்ட்களை நிர்வகிக்க நான் எவ்வாறு உதவலாம்?"
            }.get(state.language, f"Hello {state.patient_name}, welcome to 2Care Clinic.")
            
            await websocket.send_json({
                "type": "state",
                "state": state.to_dict()
            })
            
            await websocket.send_json({"type": "thinking", "log": "Synthesizing welcome greeting..."})
            tts_start = time.time()
            greeting_audio = await text_to_speech(greeting_text, state.language, api_key)
            tts_latency = (time.time() - tts_start) * 1000
            
            await websocket.send_json({
                "type": "agent_response",
                "text": greeting_text,
                "audio_len": len(greeting_audio)
            })
            await websocket.send_bytes(greeting_audio)
            
            state.history.append({"role": "assistant", "content": greeting_text})
            
            await websocket.send_json({
                "type": "latency",
                "metrics": {
                    "stt": 0.0,
                    "llm": 0.0,
                    "tts": tts_latency,
                    "network": 20.0,
                    "total": tts_latency + 20.0
                }
            })
            
        # Loop for receiving messages
        while True:
            message = await websocket.receive()
            
            if "bytes" in message:
                # Accumulate raw audio stream bytes (e.g. WAV or PCM chunks)
                audio_buffer.extend(message["bytes"])
                
            elif "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type")
                
                if msg_type == "interrupt":
                    # User interrupted speaking (barge-in)
                    # Clear buffers and notify client to stop audio playback
                    print("[WS] Interrupt received (barge-in). Stopping agent output.")
                    audio_buffer.clear()
                    await websocket.send_json({"type": "stop_audio"})
                    
                elif msg_type == "stop-speaking":
                    # Finished speaking. Process the accumulated audio buffer
                    if len(audio_buffer) == 0:
                        continue
                        
                    print(f"[WS] Speech end detected. Processing {len(audio_buffer)} audio bytes.")
                    await websocket.send_json({"type": "thinking", "log": "Transcribing audio..."})
                    
                    stt_start = time.time()
                    # Transcribe
                    # Note: If no API key, this runs in fast simulator mode
                    user_text = transcribe_audio_bytes(bytes(audio_buffer), api_key)
                    stt_latency = (time.time() - stt_start) * 1000
                    audio_buffer.clear()
                    
                    # If STT simulator is triggered, we can check if frontend sent a fallback text
                    if user_text == "SIMULATED_AUDIO_RECEIVED" and "text_fallback" in data:
                        user_text = data["text_fallback"]
                        
                    await websocket.send_json({
                        "type": "user_transcript",
                        "text": user_text
                    })
                    
                    # Run AI reasoning pipeline
                    await websocket.send_json({"type": "thinking", "log": "Agent is reasoning..."})
                    
                    agent_res = run_agent_reasoning(session_id, user_text, api_key)
                    llm_latency = agent_res["latency_ms"]
                    thinking_logs = agent_res["thinking_logs"]
                    response_text = agent_res["response"]
                    
                    # Send thinking logs to UI
                    for log in thinking_logs:
                        await websocket.send_json({"type": "thinking", "log": log})
                        
                    # Generate speech
                    await websocket.send_json({"type": "thinking", "log": "Generating audio response..."})
                    tts_start = time.time()
                    agent_audio = await text_to_speech(response_text, agent_res["language"], api_key)
                    tts_latency = (time.time() - tts_start) * 1000
                    
                    # Sync state details (updates calendar and appointment status)
                    await websocket.send_json({
                        "type": "state",
                        "state": state.to_dict()
                    })
                    
                    # Send response details
                    await websocket.send_json({
                        "type": "agent_response",
                        "text": response_text,
                        "audio_len": len(agent_audio)
                    })
                    await websocket.send_bytes(agent_audio)
                    
                    # Log total latency metrics
                    total_latency = stt_latency + llm_latency + tts_latency + 30.0 # adding mock network time
                    await websocket.send_json({
                        "type": "latency",
                        "metrics": {
                            "stt": stt_latency,
                            "llm": llm_latency,
                            "tts": tts_latency,
                            "network": 30.0,
                            "total": total_latency
                        }
                    })

                elif msg_type == "text_transcript":
                    # Text-only input for Hybrid low-latency mode
                    user_text = data.get("text", "")
                    print(f"[WS] Received text transcript: '{user_text}'")
                    
                    await websocket.send_json({
                        "type": "user_transcript",
                        "text": user_text
                    })
                    
                    await websocket.send_json({"type": "thinking", "log": "Agent is reasoning..."})
                    
                    agent_res = run_agent_reasoning(session_id, user_text, api_key)
                    llm_latency = agent_res["latency_ms"]
                    thinking_logs = agent_res["thinking_logs"]
                    response_text = agent_res["response"]
                    
                    # Stream thinking logs
                    for log in thinking_logs:
                        await websocket.send_json({"type": "thinking", "log": log})
                        
                    # Generate Speech
                    await websocket.send_json({"type": "thinking", "log": "Generating audio response..."})
                    tts_start = time.time()
                    agent_audio = await text_to_speech(response_text, agent_res["language"], api_key)
                    tts_latency = (time.time() - tts_start) * 1000
                    
                    await websocket.send_json({
                        "type": "state",
                        "state": state.to_dict()
                    })
                    
                    await websocket.send_json({
                        "type": "agent_response",
                        "text": response_text,
                        "audio_len": len(agent_audio)
                    })
                    await websocket.send_bytes(agent_audio)
                    
                    # Report Latency (STT is 0 since text is input directly from browser Speech API)
                    total_latency = 0.0 + llm_latency + tts_latency + 15.0
                    await websocket.send_json({
                        "type": "latency",
                        "metrics": {
                            "stt": 0.0,
                            "llm": llm_latency,
                            "tts": tts_latency,
                            "network": 15.0,
                            "total": total_latency
                        }
                    })

    except WebSocketDisconnect:
        print(f"[WS] Session {session_id} disconnected.")
        session_memory.delete_session(session_id)
    except Exception as e:
        print(f"[WS] Error in websocket connection: {e}")
        session_memory.delete_session(session_id)
