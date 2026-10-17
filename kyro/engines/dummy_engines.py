"""Test ke liye nakli engines - ASLI bolne/sunne wale engines nahi hain.

Inse pata chalta hai ki Core ke LISTEN/SPEAK slots sahi jude hain:
    engine use speak dummy    -> har jawab ke saath "[SPEAK] ..." chhapega
    engine use listen dummy   -> "[MIC]" prompt par type karo (mic ki jagah)
    engine off speak / engine off listen   -> wapas normal

Asli engine (TTS / mic) baad me isi tarah ki ek file engines/ me daalna.
"""

from core.kyro_core import ListenEngine, SpeakEngine


class DummySpeak(SpeakEngine):
    name = "dummy"
    description = "Bolne ki jagah screen par [SPEAK] likhta hai (test)"

    def speak(self, text):
        print(f"[SPEAK] {text}")


class DummyListen(ListenEngine):
    name = "dummy"
    description = "Mic ki jagah keyboard se 'sunta' hai (test)"

    def listen(self, timeout=None):
        try:
            return input("[MIC] ")
        except EOFError:
            return None
        except KeyboardInterrupt:
            print()
            return ""
