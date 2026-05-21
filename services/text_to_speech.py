import os
import tempfile
import asyncio
import time
from openai import OpenAI
try:
    import edge_tts
except ImportError:
    edge_tts = None

# Mapping languages to specific natural-sounding neural voices
VOICE_MAPPING = {
    "English": "en-IN-NeerjaNeural",  # Indian English neural voice (very clear and natural)
    "Hindi": "hi-IN-SwaraNeural",      # Hindi Female neural voice
    "Tamil": "ta-IN-PallaviNeural"     # Tamil Female neural voice
}

# Fallback voice names if mapping keys differ
FALLBACK_VOICE_MAPPING = {
    "English": "en-US-AriaNeural",
    "Hindi": "hi-IN-MadhurNeural",
    "Tamil": "ta-IN-ValluvarNeural"
}

async def generate_tts_edge(text: str, voice: str) -> bytes:
    """Runs edge_tts to generate audio bytes."""
    communicate = edge_tts.Communicate(text, voice)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
        temp_path = temp_file.name
    try:
        await communicate.save(temp_path)
        with open(temp_path, "rb") as f:
            audio_data = f.read()
        return audio_data
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

async def text_to_speech(text: str, language: str = "English", api_key: str = None) -> bytes:
    """
    Converts text to speech bytes (MP3/WAV).
    Supports English, Hindi, and Tamil.
    """
    start_time = time.time()
    voice = VOICE_MAPPING.get(language, VOICE_MAPPING["English"])

    # 1. Use OpenAI TTS if key is present
    if api_key and api_key.strip():
        try:
            client = OpenAI(api_key=api_key)
            # Map languages to OpenAI voices
            openai_voice = "alloy"
            if language == "Hindi":
                openai_voice = "shimmer"
            elif language == "Tamil":
                openai_voice = "nova"
                
            response = client.audio.speech.create(
                model="tts-1",
                voice=openai_voice,
                input=text
            )
            audio_bytes = response.content
            latency = (time.time() - start_time) * 1000
            print(f"[TTS] OpenAI TTS generated in {latency:.2f}ms for text: '{text[:30]}...'")
            return audio_bytes
        except Exception as e:
            print(f"[TTS] OpenAI TTS failed: {e}. Falling back to Edge-TTS.")

    # 2. Use Edge-TTS (Neural and Free)
    if edge_tts:
        try:
            audio_bytes = await generate_tts_edge(text, voice)
            latency = (time.time() - start_time) * 1000
            print(f"[TTS] Edge-TTS generated in {latency:.2f}ms for voice {voice}.")
            return audio_bytes
        except Exception as e:
            print(f"[TTS] Edge-TTS failed: {e}. Falling back to gTTS or simulation.")

    # 3. Basic gTTS Fallback
    try:
        from gtts import gTTS
        lang_code = "en"
        if language == "Hindi":
            lang_code = "hi"
        elif language == "Tamil":
            lang_code = "ta"
            
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_path = temp_file.name
            
        try:
            tts = gTTS(text=text, lang=lang_code, slow=False)
            tts.save(temp_path)
            with open(temp_path, "rb") as f:
                audio_bytes = f.read()
            latency = (time.time() - start_time) * 1000
            print(f"[TTS] gTTS generated in {latency:.2f}ms.")
            return audio_bytes
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except Exception as e:
        print(f"[TTS] gTTS failed: {e}. Returning empty bytes.")
        
    # 4. Final Simulator Fallback (Mock Audio)
    # If everything fails, sleep 100ms and return a small blank sound or mock header
    await asyncio.sleep(0.10)
    # A tiny 1-second blank MP3 data or placeholder bytes
    return b"\x00" * 1000

if __name__ == "__main__":
    print("Testing Edge-TTS translation to audio...")
    audio = text_to_speech("नमस्ते, आपका स्वागत है।", "Hindi")
    print(f"Generated {len(audio)} bytes of Hindi speech.")
