import unittest
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import init_db
from scheduler.appointment_engine import (
    check_doctor_availability, 
    check_collision, 
    suggest_alternative_slots
)

class TestSchedulingEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize the database
        init_db()

    def test_doctor_availability_hours(self):
        # Test Dr Ramesh Sharma (id 1, Mon-Fri, 9:00-17:00)
        # 1. Available hour
        is_avail, msg = check_doctor_availability(1, "2026-05-22", "10:00")
        self.assertTrue(is_avail, msg)
        
        # 2. Outside hours
        is_avail, msg = check_doctor_availability(1, "2026-05-22", "08:00")
        self.assertFalse(is_avail, msg)
        
        # 3. Weekend (2026-05-23 is Saturday, Dr Ramesh is Mon-Fri)
        is_avail, msg = check_doctor_availability(1, "2026-05-23", "10:00")
        self.assertFalse(is_avail, msg)

    def test_past_date_rejection(self):
        # Rejects past dates
        is_avail, msg = check_doctor_availability(1, "2020-01-01", "10:00")
        self.assertFalse(is_avail)
        self.assertIn("past", msg.lower())

    def test_alternatives_generation(self):
        # Doctor 1 has available slots. Requesting a Sunday slot should suggest working days
        alts = suggest_alternative_slots(1, "2026-05-24") # Sunday
        self.assertTrue(len(alts) > 0)
        # All suggested slots must be valid YYYY-MM-DD
        for date_str, time_str in alts:
            self.assertEqual(len(date_str), 10)
            self.assertEqual(len(time_str), 5)

if __name__ == "__main__":
    unittest.main()
