"""SurakshaSetu backend: FastAPI + Gnani Prisma (STT) + Gnani Timbre (TTS).
Audio is analysed in a temp file that is deleted immediately. Nothing is stored."""
import io, os, re, time, wave, random, tempfile, threading
from pathlib import Path
from urllib.parse import quote
from dotenv import load_dotenv
load_dotenv()
if not os.getenv("GNANI_API_KEY"):
    raise SystemExit("Set your key first (cmd):  set GNANI_API_KEY=your-key")

from fastapi import FastAPI, Request, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from gnani.stt import GnaniSTTClient
from gnani.tts import GnaniTTSClient, AudioConfig

BASE = Path(__file__).parent
SAMPLES = BASE / "samples"; SAMPLES.mkdir(exist_ok=True)
SR = 16000
app = FastAPI()
stt, tts = GnaniSTTClient(), GnaniTTSClient()
KEYTERMS = ["OTP", "CBI", "Aadhaar", "digital arrest", "TRAI", "KYC", "UPI"]
# Caller identities use different Timbre v2.5 voices. The alert has its own voice.
# These are v2.5 catalogue names (do not use legacy v2.0-only voices such as Deepak).
SCAM_VOICE = {"hi-IN": "Hemraj", "en-IN": "Girish", "ta-IN": "Hemraj", "te-IN": "Hemraj", "bn-IN": "Hemraj"}
GENUINE_VOICE = {"hi-IN": "Bhavna", "en-IN": "Kaveri", "ta-IN": "Asmita", "te-IN": "Suhana", "bn-IN": "Nalini"}
WARNING_VOICE = {"hi-IN": "Jwala", "en-IN": "Kaveri", "ta-IN": "Asmita", "te-IN": "Suhana", "bn-IN": "Nalini"}
LANGUAGES = {"hi-IN", "en-IN", "ta-IN", "te-IN", "bn-IN"}
TTS_MODEL = "timbre-v2.5"

# (label, weight, regex). Each label scores once per call.
RULES = [
    ("Asks for OTP / PIN / password", 50, r"otp|ओटीपी|cvv|\bpin\b|पिन|पासवर्ड|password|कार्ड\s*नंबर"),
    ("Claims to be an official", 20, r"cbi|सीबीआई|police|पुलिस|trai|ट्राई|customs|कस्टम|\bed\b|ईडी|rbi|आरबीआई|income tax|इनकम टैक्स|cyber|साइबर|कोर्ट|court|ऑफिसर|officer"),
    ("Threatens arrest or case", 25, r"arrest|अरेस्ट|गिरफ्तार|warrant|वारंट|\bcase\b|केस|जेल|jail|laundering|लॉन्ड्रिंग|\bfir\b|एफआईआर"),
    ("Demands secrecy", 30, r"किसी\s*(को|से).{0,15}(मत|न|नहीं).{0,15}(बता|बात)|don'?t tell|do not tell|गोपनीय|confidential"),
    ("Creates urgency", 10, r"अभी|तुरंत|right now|immediately|urgent|जल्दी|आज ही|वरना"),
    ("Asks for identity data", 15, r"aadhaar|aadhar|आधार|pan card|पैन कार्ड|kyc|केवाईसी"),
    ("Asks for money transfer", 40, r"ट्रांसफर|transfer|पैसे\s*(भेज|जमा)|\bupi\b|यूपीआई|जुर्माना|\bfine\b|safe account"),
    ("Threatens service cut-off", 30, r"बिजली.{0,20}(कट|बंद)|कनेक्शन.{0,15}(कट|बंद)|disconnect|डिस्कनेक्ट|digital arrest|डिजिटल अरेस्ट"),
]
# Starter keywords for Tamil, Telugu, Bengali (added to the rules above). Tune after reading real transcripts.
EXTRA = {
    "Asks for OTP / PIN / password": r"ஓடிபி|ஒடிபி|கடவுச்சொல்|ఓటీపీ|పాస్వర్డ్|ওটিপি|পাসওয়ার্ড",
    "Claims to be an official": r"சிபிஐ|போலீஸ்|அதிகாரி|சுங்கத்துறை|సీబీఐ|పోలీస్|అధికారి|కస్టమ్స్|সিবিআই|পুলিশ|অফিসার|কাস্টমস",
    "Threatens arrest or case": r"கைது|வழக்கு|வாரண்ட்|சிறை|అరెస్ట్|కేసు|వారెంట్|జైలు|গ্রেফতার|গ্রেপ্তার|মামলা|ওয়ারেন্ট|জেল",
    "Demands secrecy": r"யாரிடமும்.{0,10}(சொல்ல|கூற)|ఎవరికీ.{0,10}చెప్ప|কাউকে.{0,10}(বলবেন|জানাবেন)",
    "Creates urgency": r"உடனே|இப்போதே|உடனடியாக|వెంటనే|ఇప్పుడే|এখনই|এক্ষুনি",
    "Asks for identity data": r"ஆதார்|ఆధార్|আধার",
    "Asks for money transfer": r"பணம்.{0,10}(அனுப்ப|செலுத்த)|డబ్బు.{0,10}(పంపండి|పంపించ|చెల్లించ)|টাকা.{0,10}(পাঠান|জমা)|ট্রান্সফার",
    "Threatens service cut-off": r"மின்சாரம்.{0,15}(துண்டிக்|கட்)|டிஜிட்டல் கைது|కరెంట్.{0,15}(కట్|నిలిపి)|విద్యుత్.{0,15}(కట్|నిలిపి)|డిజిటల్ అరెస్ట్|বিদ্যুৎ.{0,15}(কেটে|বন্ধ)|ডিজিটাল অ্যারেস্ট",
}
FRAUD, SUSPICIOUS = 70, 35

# Test calls. "scam" and "ok" pools per language; each click plays a different one.
SCENARIOS = {
 "hi-IN": {
  "scam": [
   ("Hindi: fake CBI digital arrest", ["नमस्ते, मैं सीबीआई ऑफिसर राकेश शर्मा बोल रहा हूँ।", "आपके आधार कार्ड से एक मनी लॉन्ड्रिंग केस जुड़ा हुआ है।", "आप अभी डिजिटल अरेस्ट में हैं। यह बात किसी को मत बताइए।", "केस बंद करने के लिए अभी आपके फोन पर आया ओटीपी बताइए।"]),
   ("Hindi: electricity disconnection", ["नमस्ते, मैं बिजली विभाग से बोल रहा हूँ।", "आपका पिछला बिल बकाया है, आज रात आपका बिजली कनेक्शन कट जाएगा।", "अभी यूपीआई से पैसे ट्रांसफर कीजिए।"]),
   ("Hindi: bank KYC OTP", ["मैं आपके बैंक का मैनेजर बोल रहा हूँ।", "आपका केवाईसी अपडेट नहीं है, आपका खाता अभी ब्लॉक हो जाएगा।", "खाता बचाने के लिए आपके मोबाइल पर आया ओटीपी तुरंत बताइए।"]),
   ("Hindi: customs parcel", ["मैं कस्टम विभाग से बोल रहा हूँ, आपके नाम के पार्सल में गैरकानूनी सामान मिला है।", "आपके खिलाफ केस दर्ज होगा, यह बात किसी को मत बताइए।", "जुर्माना भरना होगा, अभी पैसे ट्रांसफर कीजिए।"]),
   ("Hindi: lottery prize", ["बधाई हो! आपने पच्चीस लाख रुपये की लॉटरी जीती है।", "इनाम पाने के लिए पहले पाँच हज़ार रुपये ट्रांसफर कीजिए।", "अपना आधार नंबर और ओटीपी भी अभी बताइए।"]),
   ("Hindi: fake police, son arrested", ["मैं पुलिस इंस्पेक्टर बोल रहा हूँ, आपका बेटा गिरफ्तार हो गया है।", "उसे छुड़ाने के लिए तुरंत पैसे भेजिए, किसी को मत बताइए।", "अभी यूपीआई से भुगतान कीजिए।"]),
  ],
  "ok": [
   ("Hindi: bank customer care", ["नमस्ते, मैं आपके बैंक की कस्टमर केयर से बोल रही हूँ।", "आपने कल एक शिकायत दर्ज की थी, उसका समाधान हो गया है।", "क्या मैं आपकी और कोई मदद कर सकती हूँ?"]),
   ("Hindi: courier delivery", ["नमस्ते, मैं कूरियर से बोल रहा हूँ।", "आपका पार्सल कल सुबह दस बजे पहुँचेगा।", "कृपया घर पर किसी का होना सुनिश्चित करें, धन्यवाद।"]),
   ("Hindi: doctor appointment", ["नमस्ते, यह सिटी क्लिनिक से कॉल है।", "आपकी अपॉइंटमेंट कल शाम चार बजे डॉक्टर के साथ है।", "कृपया दस मिनट पहले पहुँचिए।"]),
   ("Hindi: school teacher", ["नमस्ते, मैं आपके बच्चे की क्लास टीचर बोल रही हूँ।", "शुक्रवार को अभिभावक बैठक है, कृपया समय पर आइए।"]),
   ("Hindi: friend", ["हेलो, मैं रोहन बोल रहा हूँ, शाम को चाय पर आ रहे हो?", "मैं सात बजे तक पहुँच जाऊँगा।"]),
  ]},
 "en-IN": {
  "scam": [
   ("English: fake CBI digital arrest", ["Hello, this is Inspector Rakesh Sharma from the CBI.", "A money laundering case is registered against your Aadhaar. You are under digital arrest.", "Do not tell anyone, and share the OTP on your phone right now."]),
   ("English: electricity disconnection", ["This is the electricity board. Your bill is pending.", "Your power connection will be disconnected tonight.", "Transfer the payment through UPI immediately."]),
   ("English: bank KYC OTP", ["I am calling from your bank. Your KYC is not updated.", "Your account will be blocked right now.", "Tell me the OTP you just received."]),
   ("English: customs parcel", ["This is the customs department. A parcel in your name contains illegal items.", "A case will be filed and you will be arrested. Do not tell anyone.", "Pay the fine by transfer immediately."]),
   ("English: lottery prize", ["Congratulations, you won a lottery of twenty five lakh rupees.", "To claim it, transfer five thousand rupees first.", "Also share your Aadhaar number and OTP."]),
   ("English: fake police, son arrested", ["This is the police. Your son has been arrested.", "Send money immediately to release him. Do not tell anyone.", "Pay by UPI right now."]),
  ],
  "ok": [
   ("English: bank customer care", ["Hello, I am calling from your bank's customer care.", "Your complaint from yesterday has been resolved.", "Is there anything else I can help you with?"]),
   ("English: courier delivery", ["Hi, your parcel will be delivered tomorrow morning.", "Please keep someone at home to receive it. Thank you."]),
   ("English: doctor appointment", ["This is a reminder from City Clinic about your appointment tomorrow at four in the evening.", "Please arrive ten minutes early."]),
   ("English: school teacher", ["Good morning, I am your child's class teacher.", "There is a parents' meeting on Friday. Please attend."]),
   ("English: friend", ["Hey, it's Rohan. Are you coming over for tea this evening?", "I will reach by seven."]),
  ]},
 "ta-IN": {
  "scam": [("Tamil: fake CBI digital arrest", ["வணக்கம், நான் சிபிஐ அதிகாரி பேசுகிறேன்.", "உங்கள் ஆதார் எண்ணில் ஒரு வழக்கு பதிவாகியுள்ளது, நீங்கள் டிஜிட்டல் கைது நிலையில் உள்ளீர்கள்.", "இதை யாரிடமும் சொல்லாதீர்கள், உங்கள் ஓடிபி எண்ணை உடனே சொல்லுங்கள்."])],
  "ok": [("Tamil: bank customer care", ["வணக்கம், நான் உங்கள் வங்கி வாடிக்கையாளர் சேவையிலிருந்து பேசுகிறேன்.", "நேற்று நீங்கள் அளித்த புகார் சரி செய்யப்பட்டுள்ளது, வேறு ஏதாவது உதவி வேண்டுமா?"])]},
 "te-IN": {
  "scam": [("Telugu: fake CBI digital arrest", ["నమస్కారం, నేను సీబీఐ అధికారిని మాట్లాడుతున్నాను.", "మీ ఆధార్ మీద ఒక కేసు నమోదైంది, మీరు డిజిటల్ అరెస్ట్ లో ఉన్నారు.", "ఇది ఎవరికీ చెప్పకండి, మీ ఓటీపీ ఇప్పుడే చెప్పండి."])],
  "ok": [("Telugu: bank customer care", ["నమస్కారం, నేను మీ బ్యాంక్ కస్టమర్ కేర్ నుండి మాట్లాడుతున్నాను.", "నిన్న మీరు ఇచ్చిన ఫిర్యాదు పరిష్కరించబడింది, ఇంకేమైనా సహాయం కావాలా?"])]},
 "bn-IN": {
  "scam": [("Bengali: fake CBI digital arrest", ["নমস্কার, আমি সিবিআই অফিসার বলছি।", "আপনার আধার নম্বরে একটি মামলা হয়েছে, আপনি ডিজিটাল অ্যারেস্টে আছেন।", "এটা কাউকে বলবেন না, আপনার ওটিপি এখনই বলুন।"])],
  "ok": [("Bengali: bank customer care", ["নমস্কার, আমি আপনার ব্যাংকের গ্রাহক সেবা থেকে বলছি।", "গতকালের অভিযোগটির সমাধান হয়েছে, আর কোনো সাহায্য লাগবে?"])]},
}
WARNING_TEXT = {
    "hi-IN": "सावधान! यह कॉल धोखाधड़ी हो सकती है। कृपया अपना ओटीपी, पिन या पासवर्ड किसी को न बताएं और पैसे ट्रांसफर न करें।",
    "en-IN": "Warning! This call may be a scam. Do not share your OTP, PIN or password, and do not transfer any money.",
    "te-IN": "జాగ్రత్త! ఇది మోసపూరిత కాల్ కావచ్చు. మీ ఓటీపీ, పిన్ లేదా పాస్‌వర్డ్ ఎవరికీ చెప్పకండి. డబ్బులు బదిలీ చేయకండి.",
    "ta-IN": "எச்சரிக்கை! இது மோசடி அழைப்பாக இருக்கலாம். உங்கள் ஓடிபி, பின் அல்லது கடவுச்சொல்லை யாரிடமும் பகிர வேண்டாம். பணம் அனுப்ப வேண்டாம்.",
    "bn-IN": "সতর্কতা! এটি প্রতারণামূলক কল হতে পারে। আপনার ওটিপি, পিন বা পাসওয়ার্ড কাউকে বলবেন না এবং কোনো টাকা পাঠাবেন না।",
}

lock = threading.Lock()
sessions, decks = {}, {}
stats = dict(stt_calls=0, stt_audio_s=0.0, stt_ms=0, tts_calls=0, tts_chars=0)


def stats_view():
    with lock:
        n = stats["stt_calls"]
        return dict(stt_calls=n, stt_audio_s=round(stats["stt_audio_s"], 1),
                    stt_avg_ms=int(stats["stt_ms"] / n) if n else 0,
                    tts_calls=stats["tts_calls"], tts_chars=stats["tts_chars"])


def transcribe_pcm(pcm: bytes, lang: str):
    fd, path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    try:
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm)
        code = lang if lang in LANGUAGES else "indic-auto"
        result = stt.transcribe(path, language_code=code, model="prisma-v3.0", format="codemix", keywords=KEYTERMS)
        return {
            "text": (result.get("transcript") or "").strip(),
            "detected_language_code": result.get("detected_language_code") or (lang if lang in LANGUAGES else "unknown"),
        }
    finally:
        try: os.remove(path)
        except OSError: pass


def synth(text: str, lang: str = "hi-IN", kind: str = "warning") -> bytes:
    if kind == "scam":
        voice = SCAM_VOICE.get(lang, "Hemraj")
    elif kind == "genuine":
        voice = GENUINE_VOICE.get(lang, "Nalini")
    else:
        voice = WARNING_VOICE.get(lang, WARNING_VOICE["hi-IN"])
    audio = tts.synthesize(text, voice=voice, model=TTS_MODEL, language=lang, speed=1.0,
                           audio_config=AudioConfig(container="wav", sample_rate=SR, encoding="linear_pcm"))
    with lock:
        stats["tts_calls"] += 1; stats["tts_chars"] += len(text)
    return audio


def write_wav(path, pcm):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm)


def build_sample(lang: str, kind: str, i: int) -> Path:
    path = SAMPLES / f"{lang}_{kind}_{i}_voices_v2.wav"
    if path.exists():
        return path
    pcm, gap = b"", b"\x00\x00" * int(SR * 1.5)
    for line in SCENARIOS[lang][kind][i][1]:
        with wave.open(io.BytesIO(synth(line, lang, "scam" if kind == "scam" else "genuine"))) as w:
            pcm += w.readframes(w.getnframes()) + gap
    write_wav(path, pcm); return path


def pick(kind: str, lang: str):
    """Shuffled deck: no scenario repeats until all have played."""
    if lang not in SCENARIOS:
        lang = random.choice(["hi-IN", "en-IN"])
    pool = SCENARIOS[lang][kind]
    if not decks.get((lang, kind)):
        decks[(lang, kind)] = random.sample(range(len(pool)), len(pool))
    return lang, decks[(lang, kind)].pop()


def score(sid: str, text: str):
    s = sessions.setdefault(sid, dict(score=0, hit=[], alerted=False))
    matches = []
    for label, weight, pat in RULES:
        if label in EXTRA:
            pat = pat + "|" + EXTRA[label]
        found = list({m.group(0) for m in re.finditer(pat, text, re.I)})
        if found:
            matches.append(dict(label=label, texts=found))
            if label not in s["hit"]:
                s["hit"].append(label); s["score"] = min(100, s["score"] + weight)
    verdict = "FRAUD" if s["score"] >= FRAUD else "SUSPICIOUS" if s["score"] >= SUSPICIOUS else "SAFE"
    alert = verdict == "FRAUD" and not s["alerted"]
    if alert: s["alerted"] = True
    return dict(matches=matches, score=s["score"], verdict=verdict, signals=list(s["hit"]), alert=alert)


@app.get("/")
def index():
    index_file = BASE / "static" / "index.html"
    if not index_file.exists():
        index_file = BASE / "index.html"
    return FileResponse(index_file, headers={"Cache-Control": "no-store"})


@app.post("/api/analyze")
async def analyze(request: Request, sid: str = Query(...), lang: str = Query("auto"), transcript_lang: str = Query("same")):
    pcm = await request.body()
    pcm = pcm[: len(pcm) // 2 * 2]
    secs = len(pcm) / 2 / SR
    if secs < 0.3:
        return dict(text="", stats=stats_view())
    if lang not in LANGUAGES and lang != "auto":
        lang = "auto"
    t0 = time.time()
    try:
        result = await run_in_threadpool(transcribe_pcm, pcm, lang)
        text = result["text"]
        detected = result["detected_language_code"]
    except Exception as e:
        return JSONResponse(dict(error=f"Gnani STT failed: {e}"), status_code=502)
    ms = int((time.time() - t0) * 1000)
    with lock:
        stats["stt_calls"] += 1; stats["stt_audio_s"] += secs; stats["stt_ms"] += ms
    if not text:
        return dict(text="", stats=stats_view(), detected_language_code=detected)
    # Prisma transcribes in the spoken language. No cross-language translation is
    # performed because this project is restricted to the verified Gnani APIs.
    return dict(text=text, latency_ms=ms, detected_language_code=detected,
                transcript_language_code=detected, translation_applied=False,
                translation_note=("Gnani Prisma returns the transcript in the spoken language. "
                                  "Cross-language translation is not available in this Gnani-only build."),
                stats=stats_view(), **score(sid, text))


@app.post("/api/reset")
def reset(sid: str = Query(...)):
    sessions.pop(sid, None); return dict(ok=True)


@app.get("/api/stats")
def get_stats():
    return stats_view()


@app.get("/api/warning")
def warning(lang: str = Query("hi-IN")):
    if lang not in LANGUAGES:
        lang = "hi-IN"
    path = SAMPLES / f"alert_{lang}_timbre_v2.wav"
    try:
        if not path.exists():
            path.write_bytes(synth(WARNING_TEXT[lang], lang, "warning"))
        return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "no-store"})
    except Exception as e:
        return JSONResponse(dict(error=f"Gnani TTS warning failed for {lang}: {e}"), status_code=502)

@app.get("/api/sample/{kind}")
def sample(kind: str, lang: str = Query("auto")):
    if kind not in ("scam", "ok"):
        return JSONResponse(dict(error="unknown sample"), status_code=404)
    lang, i = pick(kind, lang)
    try:
        path = build_sample(lang, kind, i)
        return FileResponse(path, media_type="audio/wav", headers={"X-Scenario": quote(SCENARIOS[lang][kind][i][0])})
    except Exception as e:
        return JSONResponse(dict(error=f"Gnani TTS failed for {lang}: {e}"), status_code=502)
if os.getenv("SCAM_ENGINE", "v2") == "v2":      # opt-in: default behaviour stays identical to today
    from engine_v2 import make_score
    score = make_score(sessions)                # /api/analyze looks up `score` at call time, so this swaps it
from extras import router
app.include_router(router)