from datetime import datetime, timedelta
import sqlite3
import os
import sys

# Add backend directory to sys.path so we can import database
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
from database import get_db_connection

def parse_time(time_str):
    return datetime.strptime(time_str, "%H:%M").time()

def parse_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").date()

def get_day_name(date_str):
    # Returns weekday name like "Monday", "Tuesday", etc.
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%A")

def check_doctor_availability(doctor_id, date_str, time_str):
    """
    Checks if a doctor is available on a specific date and time based on their weekly schedule.
    Returns (bool, message)
    """
    try:
        # Check if date is in the past
        req_date = parse_date(date_str)
        today = datetime.now().date()
        if req_date < today:
            return False, "Cannot book appointments in the past."

        # Check if booking today but in the past hour
        if req_date == today:
            req_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            if req_datetime < datetime.now():
                return False, "Cannot book a slot that has already passed today."

        day_name = get_day_name(date_str)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, available_days, available_hours FROM doctors WHERE id = ?", (doctor_id,))
        doctor = cursor.fetchone()
        conn.close()

        if not doctor:
            return False, f"Doctor with ID {doctor_id} not found."

        # Check if doctor works on this day
        active_days = [day.strip() for day in doctor['available_days'].split(',')]
        if day_name not in active_days:
            return False, f"{doctor['name']} does not practice on {day_name}s. Practicing days: {doctor['available_days']}."

        # Check if time is within working hours
        req_time = parse_time(time_str)
        start_str, end_str = doctor['available_hours'].split('-')
        start_time = parse_time(start_str)
        end_time = parse_time(end_str)

        if not (start_time <= req_time < end_time):
            return False, f"Requested time {time_str} is outside working hours ({doctor['available_hours']}) for {doctor['name']}."

        return True, "Doctor is operating."
    except ValueError:
        return False, "Invalid date or time format. Please use YYYY-MM-DD and HH:MM."
    except Exception as e:
        return False, f"Error checking doctor availability: {str(e)}"

def check_collision(doctor_id, date_str, time_str, ignore_appointment_id=None):
    """
    Checks if there is a double booking for the doctor.
    Returns (bool, message) - True if there IS a collision, False if available.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if ignore_appointment_id:
        cursor.execute("""
            SELECT id FROM appointments 
            WHERE doctor_id = ? AND date = ? AND time = ? AND status = 'booked' AND id != ?
        """, (doctor_id, date_str, time_str, ignore_appointment_id))
    else:
        cursor.execute("""
            SELECT id FROM appointments 
            WHERE doctor_id = ? AND date = ? AND time = ? AND status = 'booked'
        """, (doctor_id, date_str, time_str))
        
    collision = cursor.fetchone()
    conn.close()
    
    if collision:
        return True, "This slot is already booked."
    return False, "Slot is open."

def suggest_alternative_slots(doctor_id, date_str, limit=3):
    """
    Returns a list of alternative available slots for a doctor on a given date.
    """
    try:
        req_date = parse_date(date_str)
        today = datetime.now().date()
        if req_date < today:
            # Suggest slots for today or tomorrow instead
            date_str = today.strftime("%Y-%m-%d")
            req_date = today

        day_name = get_day_name(date_str)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT available_days, available_hours FROM doctors WHERE id = ?", (doctor_id,))
        doctor = cursor.fetchone()
        
        if not doctor:
            conn.close()
            return []

        # Find the next working day if this day is not active
        active_days = [day.strip() for day in doctor['available_days'].split(',')]
        iterations = 0
        while day_name not in active_days and iterations < 7:
            req_date += timedelta(days=1)
            day_name = req_date.strftime("%A")
            date_str = req_date.strftime("%Y-%m-%d")
            iterations += 1

        if iterations >= 7:
            conn.close()
            return []

        # Generate 30-minute intervals during working hours
        start_str, end_str = doctor['available_hours'].split('-')
        start_dt = datetime.strptime(f"{date_str} {start_str}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{date_str} {end_str}", "%Y-%m-%d %H:%M")
        
        # Get existing bookings for this doctor on this day
        cursor.execute("""
            SELECT time FROM appointments 
            WHERE doctor_id = ? AND date = ? AND status = 'booked'
        """, (doctor_id, date_str))
        booked_times = {row['time'] for row in cursor.fetchall()}
        conn.close()

        alternatives = []
        current_dt = start_dt
        now = datetime.now()

        while current_dt < end_dt:
            # If date is today, ensure slot is in the future
            if req_date == today and current_dt <= now:
                current_dt += timedelta(minutes=30)
                continue

            time_slot = current_dt.strftime("%H:%M")
            if time_slot not in booked_times:
                alternatives.append((date_str, time_slot))
                if len(alternatives) >= limit:
                    break
            current_dt += timedelta(minutes=30)
            
        return alternatives
    except Exception as e:
        print("Error suggesting alternatives:", e)
        return []

if __name__ == "__main__":
    # Test scheduling engine
    print("Checking availability for Dr. Ramesh on 2026-05-22 at 10:00 (seeded as booked):")
    available, msg = check_doctor_availability(1, "2026-05-22", "10:00")
    collided, col_msg = check_collision(1, "2026-05-22", "10:00")
    print(f"Operating check: {available} ({msg})")
    print(f"Collision check: {collided} ({col_msg})")
    
    print("\nAlternative slots for Dr. Ramesh on 2026-05-22:")
    alts = suggest_alternative_slots(1, "2026-05-22")
    print(alts)
