"""
Voice Client: Veterinaria Minos Clinic
Records audio via microphone, sends it to Dialogflow, and plays the synthesized audio response.
"""

import os
import uuid
import wave
import numpy as np
import sounddevice as sd
from google.cloud import dialogflow

# --- PROJECT CONFIGURATION ---
PROJECT_ID = os.environ.get("DIALOGFLOW_PROJECT_ID", "veterinariabot-geeu") 
LANGUAGE_CODE = "es"
SAMPLE_RATE = 16000  # Dialogflow expects 16 kHz for LINEAR_16 encoding
RECORD_SECONDS = 5

# Session ID to maintain the conversation context (e.g., appointment booking flow)
SESSION_ID = str(uuid.uuid4())

# Initialize Dialogflow session client
session_client = dialogflow.SessionsClient()
session_path = session_client.session_path(PROJECT_ID, SESSION_ID)

# --- RECORDING AND PLAYBACK FUNCTIONS ---
def record_audio(seconds: int = RECORD_SECONDS) -> bytes:
    """Records audio from the default microphone for a given number of seconds."""
    print(f"\nHabla ({seconds}s)...")
    audio_data = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    print("Procesando consulta veterinaria...")
    return audio_data.tobytes()

def play_audio(wav_bytes: bytes, filename: str = "respuesta.wav") -> None:
    """
    Saves the LINEAR_16 audio returned by Dialogflow to a WAV file and plays it.
    The base64 payload starts with 'RIFF', representing a valid WAV header.
    """
    with open(filename, "wb") as f:
        f.write(wav_bytes)

    with wave.open(filename, "rb") as w:
        frames = w.readframes(w.getnframes())
        framerate = w.getframerate()

    audio_array = np.frombuffer(frames, dtype=np.int16)
    sd.play(audio_array, framerate)
    sd.wait()

# --- DIALOGFLOW INTERACTION ---
def interact_with_agent(audio_bytes: bytes):
    """Sends the recorded audio to Dialogflow and retrieves the text/audio response."""
    query_input = dialogflow.QueryInput(
        audio_config=dialogflow.InputAudioConfig(
            audio_encoding=dialogflow.AudioEncoding.AUDIO_ENCODING_LINEAR_16,
            language_code=LANGUAGE_CODE,
            sample_rate_hertz=SAMPLE_RATE,
        )
    )

    output_config = dialogflow.OutputAudioConfig(
        audio_encoding=dialogflow.OutputAudioEncoding.OUTPUT_AUDIO_ENCODING_LINEAR_16
    )

    return session_client.detect_intent(
        request={
            "session": session_path,
            "query_input": query_input,
            "input_audio": audio_bytes,
            "output_audio_config": output_config,
        }
    )

# --- MAIN CONVERSATION LOOP ---
def main():
    """Main loop handling the voice interaction with the Dialogflow agent."""
    print("=" * 60)
    print("🐾 Cliente de Voz - Clínica Veterinaria Minos 🐾")
    print(f"Proyecto : {PROJECT_ID}")
    print(f"Sesión   : {SESSION_ID}")
    print("Presiona Enter para hablar, o escribe 'q' + Enter para salir.")
    print("=" * 60)

    while True:
        user_input = input("\n> ").strip().lower()
        if user_input == "q":
            break

        response = interact_with_agent(record_audio())
        result = response.query_result

        # Dialogflow performs built-in Speech-to-Text during detect_intent
        print(f"  Has dicho  : {result.query_text}")
        print(f"  Intención  : {result.intent.display_name} (Confianza: {result.intent_detection_confidence:.2f})")
        print(f"  Parámetros : {dict(result.parameters)}")
        print(f"  Responde   : {result.fulfillment_text}")

        if response.output_audio:
            play_audio(response.output_audio)

if __name__ == "__main__":
    main()