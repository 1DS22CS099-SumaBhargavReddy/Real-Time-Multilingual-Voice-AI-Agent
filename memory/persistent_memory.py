import sqlite3
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
from database import get_db_connection

def get_patient_profile(patient_id):
    """
    Retrieves long-term patient details and booking history.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get patient details
    cursor.execute("""
        SELECT p.id, p.name, p.preferred_language, p.preferred_doctor_id, p.notes, d.name as doctor_name
        FROM patients p
        LEFT JOIN doctors d ON p.preferred_doctor_id = d.id
        WHERE p.id = ?
    """, (patient_id,))
    patient = cursor.fetchone()
    
    if not patient:
        conn.close()
        return None
        
    # Get past and active appointments
    cursor.execute("""
        SELECT a.id, a.date, a.time, a.status, d.name as doctor_name, d.specialty
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.patient_id = ?
        ORDER BY a.date DESC, a.time DESC
    """, (patient_id,))
    appointments = [dict(row) for row in cursor.fetchall()]
    conn.close()

    patient_dict = dict(patient)
    patient_dict["appointments"] = appointments
    return patient_dict

def update_patient_profile(patient_id, preferred_language=None, preferred_doctor_id=None, notes=None):
    """
    Updates patient persistent memory details.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if patient exists
    cursor.execute("SELECT id FROM patients WHERE id = ?", (patient_id,))
    if not cursor.fetchone():
        # Create user if they don't exist
        cursor.execute("""
            INSERT INTO patients (id, name, preferred_language, preferred_doctor_id, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (patient_id, "Unknown Patient", preferred_language, preferred_doctor_id, notes))
    else:
        # Build update query dynamically
        updates = []
        params = []
        if preferred_language is not None:
            updates.append("preferred_language = ?")
            params.append(preferred_language)
        if preferred_doctor_id is not None:
            updates.append("preferred_doctor_id = ?")
            params.append(preferred_doctor_id)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
            
        if updates:
            query = f"UPDATE patients SET {', '.join(updates)} WHERE id = ?"
            params.append(patient_id)
            cursor.execute(query, tuple(params))
            
    conn.commit()
    conn.close()
    return True

if __name__ == "__main__":
    # Test persistent memory
    print("Testing persistent memory retrieval for P101:")
    profile = get_patient_profile("P101")
    print(profile)
