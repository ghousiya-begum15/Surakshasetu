"""Compare scoring v1 (app.py, untouched) with v2 on text-only calls. Costs no Gnani credits.
Run:  python eval_detector.py      (put next to app.py)"""
import re, sys, pathlib
from engine_v2 import make_score
src = (pathlib.Path(__file__).parent / "app.py").read_text(encoding="utf-8")
ns = {"re": re, "sessions": {}}
exec(src[src.index("RULES = ["):src.index("# Test calls")], ns)           # v1 rules, thresholds
exec(src[src.index("def score("):src.index('@app.get("/")')], ns)           # v1 score()
v1 = ns["score"]; v2s = {}; v2 = make_score(v2s)

SCAM = [
 ("en CBI digital arrest", ["Hello, this is Inspector Rakesh Sharma from the CBI.", "A money laundering case is registered against your Aadhaar. You are under digital arrest.", "Do not tell anyone, and share the OTP on your phone right now."]),
 ("en electricity", ["This is the electricity board. Your bill is pending.", "Your power connection will be disconnected tonight.", "Transfer the payment through UPI immediately."]),
 ("en bank KYC", ["I am calling from your bank. Your KYC is not updated.", "Your account will be blocked right now.", "Tell me the OTP you just received."]),
 ("en cyber cell", ["Sir, this is the cyber cell. Your SIM card was used in illegal activity.", "Stay on the video call and do not disconnect.", "Move your savings to the RBI safe account to verify."]),
 ("en parcel, rephrased", ["Good evening, I am a senior officer from the narcotics bureau.", "A parcel with drugs came in your name. If you cooperate we will close this quietly.", "Please send ninety thousand rupees as a security deposit."]),
 ("en blackmail, evasive", ["Madam, I am from Mumbai police. Your daughter's photo is in an inappropriate video.", "Pay two lakh to delete it."]),
 ("hi CBI digital arrest", ["नमस्ते, मैं सीबीआई ऑफिसर राकेश शर्मा बोल रहा हूँ।", "आपके आधार कार्ड से एक मनी लॉन्ड्रिंग केस जुड़ा हुआ है।", "आप अभी डिजिटल अरेस्ट में हैं। यह बात किसी को मत बताइए।", "केस बंद करने के लिए अभी आपके फोन पर आया ओटीपी बताइए।"]),
 ("hi electricity", ["नमस्ते, मैं बिजली विभाग से बोल रहा हूँ।", "आपका पिछला बिल बकाया है, आज रात आपका बिजली कनेक्शन कट जाएगा।", "अभी यूपीआई से पैसे ट्रांसफर कीजिए।"]),
 ("hi lottery", ["बधाई हो! आपने पच्चीस लाख रुपये की लॉटरी जीती है।", "इनाम पाने के लिए पहले पाँच हज़ार रुपये ट्रांसफर कीजिए।", "अपना आधार नंबर और ओटीपी भी अभी बताइए।"]),
 ("hi fake police, son", ["मैं पुलिस इंस्पेक्टर बोल रहा हूँ, आपका बेटा गिरफ्तार हो गया है।", "उसे छुड़ाने के लिए तुरंत पैसे भेजिए, किसी को मत बताइए।", "अभी यूपीआई से भुगतान कीजिए।"]),
 ("hi cyber crime, PIN", ["नमस्ते, मैं साइबर क्राइम से बोल रहा हूँ।", "आपके मोबाइल नंबर से गलत कॉल्स हुई हैं।", "अगर आप चाहते हैं कि मामला यहीं खत्म हो जाए तो अपना बैंक का पिन बता दीजिए।"]),
 ("ta CBI", ["வணக்கம், நான் சிபிஐ அதிகாரி பேசுகிறேன்.", "உங்கள் ஆதார் எண்ணில் ஒரு வழக்கு பதிவாகியுள்ளது, நீங்கள் டிஜிட்டல் கைது நிலையில் உள்ளீர்கள்.", "இதை யாரிடமும் சொல்லாதீர்கள், உங்கள் ஓடிபி எண்ணை உடனே சொல்லுங்கள்."]),
 ("te CBI", ["నమస్కారం, నేను సీబీఐ అధికారిని మాట్లాడుతున్నాను.", "మీ ఆధార్ మీద ఒక కేసు నమోదైంది, మీరు డిజిటల్ అరెస్ట్ లో ఉన్నారు.", "ఇది ఎవరికీ చెప్పకండి, మీ ఓటీపీ ఇప్పుడే చెప్పండి."]),
 ("bn CBI", ["নমস্কার, আমি সিবিআই অফিসার বলছি।", "আপনার আধার নম্বরে একটি মামলা হয়েছে, আপনি ডিজিটাল অ্যারেস্টে আছেন।", "এটা কাউকে বলবেন না, আপনার ওটিপি এখনই বলুন।"]),
]
OK = [
 ("en bank awareness", ["This is an alert from the cyber security officer of your bank.", "Never share your OTP, PIN or password with anyone."]),
 ("hi bank awareness", ["नमस्ते, यह आपके बैंक की साइबर सुरक्षा टीम की ओर से सूचना है।", "किसी को भी अपना ओटीपी या पिन न बताएं।"]),
 ("en friend", ["Hey, I'm fine. In case the police stop you, call me right now."]),
 ("en call transfer", ["Thank you for calling. Let me transfer your call to the loan officer.", "The case number is 4471, please hold on."]),
 ("en EMI reminder", ["Hello, this is a reminder from your bank. Your EMI of two thousand rupees is due on the fifth.", "You can pay it through the UPI option in our app."]),
 ("en delivery OTP", ["Your delivery OTP is four five six.", "Please share it with our delivery executive when he arrives."]),
 ("en police verification", ["This is the local police station. We are doing a routine passport verification.", "Please keep your documents ready for the officer's visit on Friday."]),
 ("en courier", ["Hi, your parcel will be delivered tomorrow morning.", "Please keep someone at home to receive it. Thank you."]),
 ("en customer care", ["Hello, I am calling from your bank's customer care.", "Your complaint from yesterday has been resolved.", "Is there anything else I can help you with?"]),
 ("hi friend", ["हेलो, मैं रोहन बोल रहा हूँ, शाम को चाय पर आ रहे हो?", "मैं सात बजे तक पहुँच जाऊँगा।"]),
 ("hi clinic", ["नमस्ते, यह सिटी क्लिनिक से कॉल है।", "आपकी अपॉइंटमेंट कल शाम चार बजे डॉक्टर के साथ है।"]),
 ("hi power-cut notice", ["नमस्ते, बिजली विभाग से सूचना है।", "कल सुबह दस बजे से दो बजे तक मरम्मत के कारण बिजली बंद रहेगी।"]),
 ("ta bank care", ["வணக்கம், நான் உங்கள் வங்கி வாடிக்கையாளர் சேவையிலிருந்து பேசுகிறேன்.", "நேற்று நீங்கள் அளித்த புகார் சரி செய்யப்பட்டுள்ளது, வேறு ஏதாவது உதவி வேண்டுமா?"]),
 ("bn bank care", ["নমস্কার, আমি আপনার ব্যাংকের গ্রাহক সেবা থেকে বলছি।", "গতকালের অভিযোগটির সমাধান হয়েছে, আর কোনো সাহায্য লাগবে?"]),
]

def run(fn, lines, tag):
    sid = f"{tag}{id(lines)}"; first = None; last = None
    for i, t in enumerate(lines):
        last = fn(sid, t)
        if last["alert"] and first is None: first = i + 1
    return last["verdict"], first

print(f"{'call':26}{'truth':7}{'v1':>12}{'v2':>12}   lines-to-alert v1/v2")
res = {"v1": [0, 0, 0, 0], "v2": [0, 0, 0, 0]}  # tp, fn, fp, tn
for truth, cases in (("scam", SCAM), ("ok", OK)):
    for name, lines in cases:
        out = {}
        for k, fn in (("v1", v1), ("v2", v2)):
            ns["sessions"].clear(); v2s.clear()
            verdict, first = run(fn, lines, k); out[k] = (verdict, first)
            pos = verdict == "FRAUD"
            idx = (0 if pos else 1) if truth == "scam" else (2 if pos else 3)
            res[k][idx] += 1
        print(f"{name:26}{truth:7}{out['v1'][0]:>12}{out['v2'][0]:>12}   {out['v1'][1]}/{out['v2'][1]} of {len(lines)}")
for k, (tp, fn_, fp, tn) in res.items():
    p = tp / (tp + fp) if tp + fp else 0; r = tp / (tp + fn_)
    print(f"{k}: precision {p:.0%}  recall {r:.0%}  false alarms {fp}/{fp+tn}  missed scams {fn_}/{tp+fn_}")
