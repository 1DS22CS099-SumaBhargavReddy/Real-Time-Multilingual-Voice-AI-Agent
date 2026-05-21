from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sqlite3
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.database import get_db_connection
from memory.persistent_memory import get_patient_profile, update_patient_profile
from agent.tools import book_appointment, cancel_appointment, reschedule_appointment, get_doctors_list

router = APIRouter()

class AppointmentBookRequest(BaseModel):
    patient_id: str
    doctor_id: int
    date: str
    time: str

class AppointmentRescheduleRequest(BaseModel):
    date: str
    new_time: str

class OutboundTriggerRequest(BaseModel):
    patient_id: str
    doctor_id: int
    campaign_type: str  # "reminder", "follow-up", "vaccination"

@router.get("/doctors")
def get_doctors():
    return get_doctors_list()

@router.get("/appointments")
def get_appointments():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.patient_id, p.name as patient_name, a.doctor_id, d.name as doctor_name, 
               d.specialty, a.date, a.time, a.status
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        LEFT JOIN patients p ON a.patient_id = p.id
        ORDER BY a.date, a.time
    """)
    appointments = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"status": "success", "appointments": appointments}

@router.get("/patients/{patient_id}")
def get_patient(patient_id: str):
    profile = get_patient_profile(patient_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"status": "success", "patient": profile}

@router.post("/appointments/book")
def api_book_appointment(req: AppointmentBookRequest):
    res = book_appointment(req.patient_id, req.doctor_id, req.date, req.time)
    if res["status"] == "error":
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@router.post("/appointments/reschedule/{appointment_id}")
def api_reschedule_appointment(appointment_id: int, req: AppointmentRescheduleRequest):
    res = reschedule_appointment(appointment_id, req.date, req.new_time)
    if res["status"] == "error":
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@router.post("/appointments/cancel/{appointment_id}")
def api_cancel_appointment(appointment_id: int):
    res = cancel_appointment(appointment_id)
    if res["status"] == "error":
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@router.post("/outbound/trigger")
def trigger_outbound_campaign(req: OutboundTriggerRequest):
    # Simulates an outbound campaign trigger.
    # We query the doctor and patient, then build a campaign script that will be 
    # fed into the WebSocket server so that the next voice call behaves like an outbound call.
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM doctors WHERE id = ?", (req.doctor_id,))
    doc = cursor.fetchone()
    cursor.execute("SELECT name, preferred_language FROM patients WHERE id = ?", (req.patient_id,))
    patient = cursor.fetchone()
    conn.close()
    
    if not doc or not patient:
        raise HTTPException(status_code=404, detail="Doctor or Patient not found")
        
    doc_name = doc["name"]
    pat_name = patient["name"]
    lang = patient["preferred_language"] or "English"
    
    # Store template text based on the campaign type
    campaign_scripts = {
        "reminder": {
            "English": f"Hello {pat_name}, this is a reminder about your appointment with {doc_name} tomorrow. Can you confirm if you are still coming, or would you like to reschedule?",
            "Hindi": f"नमस्ते {pat_name}, यह {doc_name} के साथ आपकी कल की अपॉइंटमेंट के लिए एक रिमाइंडर है। क्या आप आ रहे हैं, या आप इसे बदलना चाहेंगे?",
            "Tamil": f"வணக்கம் {pat_name}, நாளை {doc_name} உடன் உங்கள் அப்பாயிண்ட்மெண்ட் உள்ளது என்பதை நினைவூட்டுகிறோம். நீங்கள் வருகிறீர்களா, அல்லது மாற்றுவதற்கு விரும்புகிறீர்களா?"
        },
        "follow-up": {
            "English": f"Hello {pat_name}, this is a follow-up call from 2Care Clinic. How are you feeling after your recent appointment with {doc_name}?",
            "Hindi": f"नमस्ते {pat_name}, यह 2Care क्लिनिक से एक फॉलो-अप कॉल है। {doc_name} के साथ आपके इलाज के बाद अब आप कैसा महसूस कर रहे हैं?",
            "Tamil": f"வணக்கம் {pat_name}, 2Care கிளினிக்கிலிருந்து அழைக்கிறோம். {doc_name} உடனான உங்கள் அப்பாயிண்ட்மெண்டிற்கு பிறகு இப்போது உடம்பு எப்படி இருக்கிறது?"
        },
        "vaccination": {
            "English": f"Hello {pat_name}, your regular vaccination dose is scheduled for this week with {doc_name}. Would you like to book a slot for tomorrow?",
            "Hindi": f"नमस्ते {pat_name}, इस सप्ताह {doc_name} के साथ आपका नियमित टीकाकरण निर्धारित है। क्या आप कल के लिए एक समय बुक करना चाहेंगे?",
            "Tamil": f"வணக்கம் {pat_name}, இந்த வாரம் {doc_name} உடன் உங்களுக்கான வழக்கமான தடுப்பூசி போட வேண்டும். நாளை ஒரு நேரத்தை புக் செய்யலாமா?"
        }
    }
    
    script = campaign_scripts.get(req.campaign_type, campaign_scripts["reminder"]).get(lang, campaign_scripts["reminder"]["English"])
    
    # Create an outbound queue item that the backend WebSocket will consume
    # when the user connects for a simulated outbound campaign call.
    from backend.api.websocket import queue_outbound_call
    queue_outbound_call(req.patient_id, req.doctor_id, script, lang)
    
    return {
        "status": "success",
        "message": f"Outbound campaign triggered for {pat_name}.",
        "script": script,
        "language": lang
    }
