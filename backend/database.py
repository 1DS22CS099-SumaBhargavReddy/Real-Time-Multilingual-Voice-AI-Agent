import sqlite3
import os

DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "appointments.db")

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create Doctors table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        specialty TEXT NOT NULL,
        available_days TEXT NOT NULL, -- Comma-separated list of weekdays, e.g., "Monday,Tuesday"
        available_hours TEXT NOT NULL, -- Format "HH:MM-HH:MM"
        languages TEXT NOT NULL -- Comma-separated list, e.g., "English,Hindi"
    )
    """)
    
    # Create Patients table (Persistent Memory)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        preferred_language TEXT,
        preferred_doctor_id INTEGER,
        notes TEXT,
        FOREIGN KEY (preferred_doctor_id) REFERENCES doctors (id)
    )
    """)
    
    # Create Appointments table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        doctor_id INTEGER NOT NULL,
        date TEXT NOT NULL, -- Format "YYYY-MM-DD"
        time TEXT NOT NULL, -- Format "HH:MM"
        status TEXT NOT NULL CHECK(status IN ('booked', 'rescheduled', 'cancelled')),
        FOREIGN KEY (doctor_id) REFERENCES doctors (id),
        FOREIGN KEY (patient_id) REFERENCES patients (id)
    )
    """)
    
    conn.commit()
    seed_data(conn)
    conn.close()

def seed_data(conn):
    cursor = conn.cursor()
    
    # Seed Doctors if table is empty
    cursor.execute("SELECT COUNT(*) FROM doctors")
    if cursor.fetchone()[0] == 0:
        doctors_data = [
            (1, "Dr. Ramesh Sharma", "Cardiologist", "Monday,Tuesday,Wednesday,Thursday,Friday", "09:00-17:00", "English,Hindi"),
            (2, "Dr. Priya Patel", "Dermatologist", "Monday,Tuesday,Wednesday,Thursday", "10:00-16:00", "English,Hindi"),
            (3, "Dr. Karthik Raja", "Orthopedician", "Tuesday,Wednesday,Friday", "09:00-15:00", "English,Tamil"),
            (4, "Dr. Anjali Krishnan", "Pediatrician", "Monday,Wednesday,Thursday,Friday", "08:00-14:00", "English,Hindi,Tamil")
        ]
        cursor.executemany("""
        INSERT INTO doctors (id, name, specialty, available_days, available_hours, languages)
        VALUES (?, ?, ?, ?, ?, ?)
        """, doctors_data)
        
    # Seed Patients if table is empty
    cursor.execute("SELECT COUNT(*) FROM patients")
    if cursor.fetchone()[0] == 0:
        patients_data = [
            ("P101", "Amit Kumar", "Hindi", 1, "Patient has high blood pressure. Prefers morning slots."),
            ("P102", "Srinivasan", "Tamil", 3, "Undergoing knee rehabilitation. Prefers Dr. Karthik Raja."),
            ("P103", "Sarah Jenkins", "English", 2, "Sensitive skin. Prefers afternoon slots."),
            ("P104", "Kiran Reddy", "English", 4, "Routine checkups. Prefers Dr. Anjali.")
        ]
        cursor.executemany("""
        INSERT INTO patients (id, name, preferred_language, preferred_doctor_id, notes)
        VALUES (?, ?, ?, ?, ?)
        """, patients_data)
        
    # Seed sample appointments
    cursor.execute("SELECT COUNT(*) FROM appointments")
    if cursor.fetchone()[0] == 0:
        # Let's seed a few dummy future/past appointments
        appointments_data = [
            ("P101", 1, "2026-05-22", "10:00", "booked"),
            ("P102", 3, "2026-05-22", "11:30", "booked"),
            ("P103", 2, "2026-05-25", "14:00", "booked")
        ]
        cursor.executemany("""
        INSERT INTO appointments (patient_id, doctor_id, date, time, status)
        VALUES (?, ?, ?, ?, ?)
        """, appointments_data)
        
    conn.commit()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DATABASE_PATH)
