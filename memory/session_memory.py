from datetime import datetime, timedelta
import threading

class SessionState:
    def __init__(self, session_id):
        self.session_id = session_id
        self.patient_id = "P101" # Default fallback patient ID
        self.patient_name = "Guest Patient"
        self.intent = None # "book", "reschedule", "cancel", None
        self.doctor_id = None
        self.doctor_name = None
        self.date = None
        self.time = None
        self.appointment_id = None # Used for reschedule/cancel
        self.alternatives_offered = [] # List of (date, time) tuples
        self.language = "English" # Detected/chosen language
        self.history = [] # Chat history: [{"role": "user"/"assistant", "content": text}]
        self.last_activity = datetime.now()

    def touch(self):
        self.last_activity = datetime.now()

    def update(self, **kwargs):
        for key, val in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, val)
        self.touch()

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "intent": self.intent,
            "doctor_id": self.doctor_id,
            "doctor_name": self.doctor_name,
            "date": self.date,
            "time": self.time,
            "appointment_id": self.appointment_id,
            "language": self.language,
            "alternatives_offered": self.alternatives_offered,
            "last_activity": self.last_activity.isoformat()
        }

class SessionMemoryManager:
    def __init__(self, ttl_minutes=15):
        self.sessions = {}
        self.ttl_minutes = ttl_minutes
        self.lock = threading.Lock()

    def get_session(self, session_id) -> SessionState:
        with self.lock:
            self._cleanup_expired_sessions()
            if session_id not in self.sessions:
                self.sessions[session_id] = SessionState(session_id)
            else:
                self.sessions[session_id].touch()
            return self.sessions[session_id]

    def delete_session(self, session_id):
        with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]

    def _cleanup_expired_sessions(self):
        now = datetime.now()
        expired = []
        for sid, state in self.sessions.items():
            if now - state.last_activity > timedelta(minutes=self.ttl_minutes):
                expired.append(sid)
        for sid in expired:
            del self.sessions[sid]

# Singleton instance
session_memory = SessionMemoryManager()
