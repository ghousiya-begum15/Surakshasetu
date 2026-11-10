from gnani.tts import GnaniTTSClient, AudioConfig

client = GnaniTTSClient()  # reads GNANI_API_KEY
audio = client.synthesize(
    "सावधान! यह कॉल स्कैम हो सकती है। किसी को भी ओटीपी न बताएं।",
    voice="Sita",
    model="timbre-v2.5",
    language="hi-IN",
    speed=1.0,
    audio_config=AudioConfig(container="wav", sample_rate=16000, encoding="linear_pcm"),
)
with open("warning.wav", "wb") as f:
    f.write(audio)
print("Saved warning.wav", len(audio), "bytes")