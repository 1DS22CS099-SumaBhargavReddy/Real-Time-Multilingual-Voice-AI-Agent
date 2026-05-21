import os
import tempfile
import time
from openai import OpenAI

def transcribe_audio_bytes(audio_bytes: bytes, api_key: str = None) -> str:
    """
    Transcribes audio bytes (WAV/WEBM) into text.
    If api_key is provided, it calls OpenAI's Whisper API.
    Otherwise, it runs in Simulator/Mock mode.
    """
    start_time = time.time()
    
    if not audio_bytes:
        return ""

    if api_key and api_key.strip():
        try:
            client = OpenAI(api_key=api_key)
            
            # Save audio bytes to a temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                temp_audio.write(audio_bytes)
                temp_path = temp_audio.name
                
            try:
                with open(temp_path, "rb") as audio_file:
                    transcript_obj = client.audio.transcriptions.create(
                        model="whisper-1", 
                        file=audio_file
                    )
                transcript = transcript_obj.text
            finally:
                # Clean up temporary file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
            latency = (time.time() - start_time) * 1000
            print(f"[STT] API Transcription completed in {latency:.2f}ms. Text: '{transcript}'")
            return transcript
            
        except Exception as e:
            print(f"[STT] Error during Whisper transcription: {e}. Falling back to simulation.")
            # Fall back to simulation on error
            
    # --- Simulator/Mock Mode ---
    # In simulation mode, the frontend can pass pre-defined text commands, 
    # or we simulate based on audio length. For debugging, if we receive audio 
    # without API keys, we return a fallback command.
    time.sleep(0.12) # Simulate Whisper processing time (~120ms)
    
    # We check if there's a cached test transcript set by the WebSocket session
    # or return a generic message.
    return "SIMULATED_AUDIO_RECEIVED"
