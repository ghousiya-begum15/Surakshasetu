import asyncio, os, re
from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent

RULES = [
    (r"otp|ओटीपी|cvv|पिन", 50, "credential ask"),
    (r"cbi|सीबीआई|police|पुलिस|trai|ट्राई", 20, "authority claim"),
    (r"arrest|अरेस्ट|गिरफ्तार|केस|case|वारंट", 25, "threat"),
    (r"किसी को.{0,12}(मत|न|नहीं).{0,12}बता|do not tell|don't tell", 30, "secrecy"),
    (r"अभी|तुरंत|right now|immediately", 10, "urgency"),
    (r"aadhaar|aadhar|आधार", 15, "identity data"),
]
THRESHOLD = 70

async def main():
    pcm = open("scam_call.pcm", "rb").read()
    hit = set()
    score = 0
    alerted = False

    async with GnaniSTTStreamClient(
        language_code="indic-auto",
        model="prisma-v3.0",
        format="codemix",
        keywords=["OTP", "CBI", "Aadhaar", "digital arrest", "TRAI"],
        sample_rate=16000,
    ) as stream:

        async def sender():
            for i in range(0, len(pcm), 1024):
                chunk = pcm[i:i + 1024].ljust(1024, b"\x00")
                await stream.send_audio(chunk)
                await asyncio.sleep(0.032)   # real-time pacing
            await asyncio.sleep(4)           # let the last segment come back

        async def receiver():
            nonlocal score, alerted
            async for event in stream:
                if isinstance(event, StreamTranscriptEvent):
                    for pattern, weight, label in RULES:
                        if label not in hit and re.search(pattern, event.text, re.IGNORECASE):
                            hit.add(label)
                            score += weight
                    print(f"[{event.latency}ms] {event.text}  | risk={score} {sorted(hit)}")
                    if score >= THRESHOLD and not alerted:
                        alerted = True
                        print(">>> ALERT: likely scam call <<<")
                        os.startfile("warning.wav")

        send_task = asyncio.create_task(sender())
        recv_task = asyncio.create_task(receiver())
        await send_task
        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass

asyncio.run(main())