import sqlite3
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.database import get_db_connection
from scheduler.appointment_engine import (
    check_doctor_availability, 
    check_collision, 
    suggest_alternative_slots
)

def get_doctors_list():
    """
    Returns a list of all doctors, their specialties, hours, days, and languages.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, specialty, available_days, available_hours, languages FROM doctors")
    doctors = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"status": "success", "doctors": doctors}

def check_availability(doctor_id: int, date: str, time: str):
    """
    Checks if Dr. is operating and if the slot is free.
    Date format: YYYY-MM-DD. Time format: HH:MM.
    """
    # 1. Check if doctor works and slot is in the future
    is_operating, msg = check_doctor_availability(doctor_id, date, time)
    if not is_operating:
        alternatives = suggest_alternative_slots(doctor_id, date)
        return {
            "status": "unavailable",
            "message": msg,
            "alternatives": alternatives
        }
        
    # 2. Check collision / double bookings
    is_collided, collision_msg = check_collision(doctor_id, date, time)
    if is_collided:
        alternatives = suggest_alternative_slots(doctor_id, date)
        return {
            "status": "unavailable",
            "message": collision_msg,
            "alternatives": alternatives
        }
        
    return {
        "status": "available",
        "message": f"Slot {date} at {time} is available.",
        "doctor_id": doctor_id,
        "date": date,
        "time": time
    }

def book_appointment(patient_id: str, doctor_id: int, date: str, time: str):
    """
    Books an appointment for a patient.
    Checks availability first to avoid conflicts.
    """
    # Double check availability first
    avail_status = check_availability(doctor_id, date, time)
    if avail_status["status"] == "unavailable":
        return avail_status
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Create appointment
        cursor.execute("""
            INSERT INTO appointments (patient_id, doctor_id, date, time, status)
            VALUES (?, ?, ?, ?, 'booked')
        """, (patient_id, doctor_id, date, time))
        appointment_id = cursor.lastrowid
        conn.commit()
        
        # Get doctor name
        cursor.execute("SELECT name FROM doctors WHERE id = ?", (doctor_id,))
        doc_name = cursor.fetchone()["name"]
        
        # Update patient preference
        cursor.execute("UPDATE patients SET preferred_doctor_id = ? WHERE id = ?", (doctor_id, patient_id))
        conn.commit()
        
        return {
            "status": "success",
            "message": f"Appointment successfully booked for {date} at {time} with {doc_name}.",
            "appointment_id": appointment_id,
            "doctor_name": doc_name,
            "date": date,
            "time": time
        }
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": f"Failed to book appointment: {str(e)}"}
    finally:
        conn.close()

def reschedule_appointment(appointment_id: int, date: str, new_time: str):
    """
    Reschedules an existing active appointment.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get original appointment
        cursor.execute("""
            SELECT patient_id, doctor_id, status FROM appointments WHERE id = ?
        """, (appointment_id,))
        appt = cursor.fetchone()
        
        if not appt:
            return {"status": "error", "message": f"Appointment with ID {appointment_id} not found."}
            
        if appt["status"] == "cancelled":
            return {"status": "error", "message": "Cannot reschedule a cancelled appointment. Please book a new one."}
            
        doctor_id = appt["doctor_id"]
        
        # Check availability for the new slot (ignoring collision with the current appointment itself)
        is_operating, msg = check_doctor_availability(doctor_id, date, new_time)
        if not is_operating:
            alternatives = suggest_alternative_slots(doctor_id, date)
            return {
                "status": "unavailable",
                "message": msg,
                "alternatives": alternatives
            }
            
        is_collided, collision_msg = check_collision(doctor_id, date, new_time, ignore_appointment_id=appointment_id)
        if is_collided:
            alternatives = suggest_alternative_slots(doctor_id, date)
            return {
                "status": "unavailable",
                "message": collision_msg,
                "alternatives": alternatives
            }
            
        # Perform rescheduling update
        cursor.execute("""
            UPDATE appointments 
            SET date = ?, time = ?, status = 'rescheduled'
            WHERE id = ?
        """, (date, new_time, appointment_id))
        conn.commit()
        
        cursor.execute("SELECT name FROM doctors WHERE id = ?", (doctor_id,))
        doc_name = cursor.fetchone()["name"]
        
        return {
            "status": "success",
            "message": f"Appointment rescheduled successfully to {date} at {new_time} with {doc_name}.",
            "appointment_id": appointment_id,
            "doctor_name": doc_name,
            "date": date,
            "time": new_time
        }
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": f"Failed to reschedule: {str(e)}"}
    finally:
        conn.close()

def cancel_appointment(appointment_id: int):
    """
    Cancels an existing appointment.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if appointment exists
        cursor.execute("SELECT id, doctor_id, date, time, status FROM appointments WHERE id = ?", (appointment_id,))
        appt = cursor.fetchone()
        
        if not appt:
            return {"status": "error", "message": f"Appointment with ID {appointment_id} not found."}
            
        if appt["status"] == "cancelled":
            return {"status": "info", "message": "This appointment has already been cancelled."}
            
        # Perform cancel update
        cursor.execute("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (appointment_id,))
        conn.commit()
        
        cursor.execute("SELECT name FROM doctors WHERE id = ?", (appt["doctor_id"],))
        doc_name = cursor.fetchone()["name"]
        
        return {
            "status": "success",
            "message": f"Appointment on {appt['date']} at {appt['time']} with {doc_name} was successfully cancelled.",
            "appointment_id": appointment_id
        }
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": f"Failed to cancel: {str(e)}"}
    finally:
        conn.close()

def get_patient_appointments(patient_id: str):
    """
    Retrieves all appointments (booked or rescheduled) for a patient.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.date, a.time, a.status, d.name as doctor_name, d.specialty
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.patient_id = ? AND a.status IN ('booked', 'rescheduled')
        ORDER BY a.date, a.time
    """, (patient_id,))
    appts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"status": "success", "appointments": appts}

# Map strings to functions for ease of execution in our agent orchestrator
TOOL_MAP = {
    "get_doctors_list": get_doctors_list,
    "check_availability": check_availability,
    "book_appointment": book_appointment,
    "reschedule_appointment": reschedule_appointment,
    "cancel_appointment": cancel_appointment,
    "get_patient_appointments": get_patient_appointments
}

# Schemas for Gemini / OpenAI tool calling
AGENT_TOOLS_SCHEMA = [
    {
        "name": "get_doctors_list",
        "description": "Get details of all available doctors and their practicing hours, specialty, and languages.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "check_availability",
        "description": "Check if a doctor is available on a specific date (YYYY-MM-DD) and time (HH:MM). Returns alternative suggestions if slot is filled.",
        "parameters": {
            "type": "object",
            "properties": {
                "doctor_id": {"type": "integer", "description": "ID of the doctor"},
                "date": {"type": "string", "description": "Date formatted as YYYY-MM-DD"},
                "time": {"type": "string", "description": "Time formatted as HH:MM"}
            },
            "required": ["doctor_id", "date", "time"]
        }
    },
    {
        "name": "book_appointment",
        "description": "Book a new clinical appointment for a patient with a doctor.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient ID (e.g. 'P101')"},
                "doctor_id": {"type": "integer", "description": "ID of the doctor"},
                "date": {"type": "string", "description": "Date formatted as YYYY-MM-DD"},
                "time": {"type": "string", "description": "Time formatted as HH:MM"}
            },
            "required": ["patient_id", "doctor_id", "date", "time"]
        }
    },
    {
        "name": "reschedule_appointment",
        "description": "Reschedule an existing active appointment to a new date and/or time.",
        "parameters": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "integer", "description": "The unique appointment ID"},
                "date": {"type": "string", "description": "New date formatted as YYYY-MM-DD"},
                "new_time": {"type": "string", "description": "New time formatted as HH:MM"}
            },
            "required": ["appointment_id", "date", "new_time"]
        }
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel an active clinical appointment.",
        "parameters": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "integer", "description": "The unique appointment ID"}
            },
            "required": ["appointment_id"]
        }
    },
    {
        "name": "get_patient_appointments",
        "description": "Get all current booked or rescheduled appointments for a patient.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient ID (e.g. 'P101')"}
            },
            "required": ["patient_id"]
        }
    }
]
