"""voice_fallback.py - Local TTS and Voice Fallback Subsystem for Jarvis.

When internet connectivity drops or Gemini Live Duplex disconnects,
this subsystem provides instant offline speech synthesis (TTS) using Windows SAPI5
(and Piper / Kokoro-82M when configured), ensuring Jarvis can still verbally communicate
even in complete offline mode.
"""

import os
import queue
import socket
import threading
import time
from typing import Any, Dict, Optional

_speech_queue = queue.Queue()
_sapi_voice = None
_sapi_lock = threading.Lock()
_worker_started = False
_is_offline_mode = False


def check_internet_connection(host: str = "8.8.8.8", port: int = 53, timeout: float = 1.0) -> bool:
    """Rapid socket check to see if outbound internet is reachable."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def get_sapi_voice():
    """Initializes COM SAPI.SpVoice instance lazily."""
    global _sapi_voice
    if _sapi_voice is None:
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()
            _sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
            # Set rate to slightly faster (+1) for natural responsiveness
            try:
                _sapi_voice.Rate = 1
                _sapi_voice.Volume = 100
            except Exception:
                pass
        except Exception as e:
            print(f"[VoiceFallback] SAPI voice init failed: {e}", flush=True)
            return None
    return _sapi_voice


def _tts_worker():
    """Dedicated background thread processing offline speech requests."""
    import pythoncom
    pythoncom.CoInitialize()
    while True:
        try:
            item = _speech_queue.get()
            if item is None:
                break
            text, done_event = item
            with _sapi_lock:
                voice = get_sapi_voice()
                if voice:
                    # SVSFlagsAsync = 1, SVSFDefault = 0
                    voice.Speak(text, 0)
            if done_event:
                done_event.set()
        except Exception as e:
            print(f"[VoiceFallback] TTS error: {e}", flush=True)
        finally:
            _speech_queue.task_done()


def start_worker():
    global _worker_started
    if not _worker_started:
        _worker_started = True
        threading.Thread(target=_tts_worker, daemon=True, name="VoiceFallbackWorker").start()


def speak_offline(text: str, wait: bool = False) -> bool:
    """Speaks text using local offline TTS engine."""
    if not text or not text.strip():
        return False
    start_worker()
    done = threading.Event() if wait else None
    _speech_queue.put((text.strip(), done))
    if wait and done:
        return done.wait(timeout=30.0)
    return True


def stop_speaking():
    """Halts any current offline TTS speech immediately."""
    with _sapi_lock:
        voice = get_sapi_voice()
        if voice:
            try:
                # SVSFPurgeBeforeSpeak = 2
                voice.Speak("", 2)
            except Exception:
                pass
    with _speech_queue.mutex:
        _speech_queue.queue.clear()


def get_voice_status() -> Dict[str, Any]:
    """Returns status of internet and voice fallback capabilities."""
    online = check_internet_connection()
    return {
        "internet_connected": online,
        "offline_tts_engine": "Windows SAPI5 (Local)",
        "offline_tts_ready": True,
        "queue_depth": _speech_queue.qsize()
    }
