import io, wave
from gnani.tts import GnaniTTSClient, AudioConfig

LINES = [
    "नमस्ते, मैं सीबीआई ऑफिसर राकेश शर्मा बोल रहा हूँ।",
    "आपके आधार कार्ड से एक मनी लॉन्ड्रिंग केस जुड़ा हुआ है।",
    "आप अभी डिजिटल अरेस्ट में हैं। यह बात किसी को मत बताइए।",
    "अगर आपने कॉल काटी तो पुलिस आपके घर पहुँच जाएगी।",
    "केस बंद करने के लिए अभी आपके फोन पर आया ओटीपी बताइए।",
]

client = GnaniTTSClient()
cfg = AudioConfig(container="wav", sample_rate=16000, encoding="linear_pcm")
silence = b"\x00\x00" * int(16000 * 1.5)   # 1.5 s pause so each line becomes its own segment
pcm = b""

for line in LINES:
    audio = client.synthesize(line, voice="Deepak", model="timbre-v2.5",
                              language="hi-IN", speed=1.0, audio_config=cfg)
    with wave.open(io.BytesIO(audio)) as w:
        print(w.getparams())
        pcm += w.readframes(w.getnframes())
    pcm += silence

with open("scam_call.pcm", "wb") as f:
    f.write(pcm)
with wave.open("scam_call.wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(pcm)
print("Done:", len(pcm) // 32000, "seconds")