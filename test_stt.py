from gnani.stt import GnaniSTTClient

client = GnaniSTTClient()
result = client.transcribe(
    "warning.wav",
    language_code="indic-auto",
    model="prisma-v3.0",
    format="codemix",
    keywords=["OTP", "CBI", "Aadhaar", "digital arrest"],
)
print(result["transcript"])
print(result.get("detected_language_code"))