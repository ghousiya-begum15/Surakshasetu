import os, re, sys, time, wave
from gnani.stt import GnaniSTTClient

RULES = [
    (r"otp|ओटीपी|cvv|पिन", 50, "credential ask"),
    (r"cbi|सीबीआई|police|पुलिस|trai|ट्राई", 20, "authority claim"),
    (r"arrest|अरेस्ट|गिरफ्तार|केस|case|वारंट", 25, "threat"),
    (r"किसी को.{0,12}(मत|न|नहीं).{0,12}बता|do not tell|don't tell", 30, "secrecy"),
    (r"अभी|तुरंत|right now|immediately", 10, "urgency"),
    (r"aadhaar|aadhar|आधार", 15, "identity data"),
]
THRESHOLD = 70
SR = 16000

def split_segments(pcm, min_silence=SR):
    s = memoryview(pcm[: len(pcm) // 2 * 2]).cast("h")
    segs, start, zeros = [], None, 0
    for i in range(len(s)):
        if s[i] == 0:
            zeros += 1
            if start is not None and zeros >= min_silence:
                segs.append((start, i - zeros + 1))
                start = None
        else:
            if start is None:
                start = i
            zeros = 0
    if start is not None:
        segs.append((start, len(s)))
    return segs

pcm_file = sys.argv[1] if len(sys.argv) > 1 else "scam_call.pcm"
pcm = open(pcm_file, "rb").read()
client = GnaniSTTClient()
hit, score, alerted = set(), 0, False

print(f"\n=== SurakshaSetu: monitoring incoming call ({pcm_file}) ===\n")
for n, (a, b) in enumerate(split_segments(pcm)):
    chunk = pcm[a * 2 : b * 2]
    name = f"seg_{n}.wav"
    with wave.open(name, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(chunk)
    time.sleep(len(chunk) / 2 / SR)          # play out in real time
    t0 = time.time()
    r = client.transcribe(name, language_code="indic-auto", model="prisma-v3.0",
                          format="codemix",
                          keywords=["OTP", "CBI", "Aadhaar", "digital arrest", "TRAI"])
    text = r["transcript"]
    for pattern, weight, label in RULES:
        if label not in hit and re.search(pattern, text, re.IGNORECASE):
            hit.add(label); score += weight
    print(f"Caller: {text}")
    print(f"   risk={score}/100  signals={sorted(hit)}  ({int((time.time()-t0)*1000)}ms)\n")
    if score >= THRESHOLD and not alerted:
        alerted = True
        print("!!!!!!  ALERT: LIKELY SCAM CALL - DO NOT SHARE OTP  !!!!!!\n")
        os.startfile("warning.wav")

if not alerted:
    print("Result: no scam detected. This call looks normal.")