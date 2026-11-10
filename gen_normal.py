import io, wave
from gnani.tts import GnaniTTSClient, AudioConfig

LINES = [
    "नमस्ते, मैं आपके बैंक की कस्टमर केयर से बोल रही हूँ।",
    "आपने कल एक शिकायत दर्ज की थी, उसका समाधान हो गया है।",
    "आपके खाते की सभी सेवाएँ सामान्य रूप से चल रही हैं।",
    "क्या मैं आपकी और कोई मदद कर सकती हूँ?",
]

client = GnaniTTSClient()
cfg = AudioConfig(container="wav", sample_rate=16000, encoding="linear_pcm")
silence = b"\x00\x00" * int(16000 * 1.5)
pcm = b""
for line in LINES:
    audio = client.synthesize(line, voice="Nalini", model="timbre-v2.5",
                              language="hi-IN", speed=1.0, audio_config=cfg)
    with wave.open(io.BytesIO(audio)) as w:
        pcm += w.readframes(w.getnframes())
    pcm += silence
open("normal_call.pcm", "wb").write(pcm)
print("Done:", len(pcm) // 32000, "seconds")