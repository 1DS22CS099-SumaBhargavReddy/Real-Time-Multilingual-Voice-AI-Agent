import re
try:
    from langdetect import detect
except ImportError:
    detect = None

def detect_language(text: str) -> str:
    """
    Detects whether the input text is in English, Hindi, or Tamil.
    Uses regex checks for Unicode blocks for maximum speed and correctness,
    falling back to langdetect.
    """
    if not text or not text.strip():
        return "English"

    text_cleaned = text.strip()
    
    # Regex checks for specific unicode scripts
    # Devanagari script: \u0900-\u097F (Hindi)
    hindi_pattern = re.compile(r'[\u0900-\u097F]')
    # Tamil script: \u0B80-\u0BFF (Tamil)
    tamil_pattern = re.compile(r'[\u0B80-\u0BFF]')
    
    # Count matching characters to handle mixed text
    hindi_chars = len(hindi_pattern.findall(text_cleaned))
    tamil_chars = len(tamil_pattern.findall(text_cleaned))
    
    if hindi_chars > 0 or tamil_chars > 0:
        if hindi_chars >= tamil_chars:
            return "Hindi"
        else:
            return "Tamil"
            
    # Try langdetect for romanized text (e.g., "aap kaise ho" or "tamilil pesunga")
    if detect:
        try:
            detected = detect(text_cleaned).lower()
            if detected == 'hi':
                return "Hindi"
            elif detected == 'ta':
                return "Tamil"
        except Exception:
            pass
            
    # Heuristics for common romanized Hindi/Tamil words
    roman_hindi_keywords = ["aap", "kaise", "milna", "doctor", " appointment", "karna", "hai", "kal", "parso", "baje"]
    roman_tamil_keywords = ["naalai", "valikuthu", "parkanum", "maruthuvar", "vendum", "yenaku", "nalla"]
    
    words = text_cleaned.lower().split()
    hindi_matches = sum(1 for w in words if w in roman_hindi_keywords)
    tamil_matches = sum(1 for w in words if w in roman_tamil_keywords)
    
    if hindi_matches > 0 or tamil_matches > 0:
        if hindi_matches >= tamil_matches:
            return "Hindi"
        else:
            return "Tamil"

    # Default fallback
    return "English"

if __name__ == "__main__":
    # Test cases
    test_phrases = [
        "Hello, I want to book an appointment with Dr Ramesh.",
        "मुझे कल डॉक्टर से मिलना है",
        "நாளை மருத்துவரை பார்க்க வேண்டும்",
        "Aap kaise ho",
        "Yenaku doctor parkanum"
    ]
    for p in test_phrases:
        print(f"Text: '{p}' -> Detected: {detect_language(p)}")
