"""Scam scoring v2 (additive, opt-in). Same return shape as v1 score(), plus 'stage'.
Fixes: clause-level negation ("never share your OTP" is awareness, not a request),
money-context rules (no more 'I'm fine' / 'transfer your call'), and a kill-chain gate."""
import re

W = {  # label: (weight, kind) -- labels identical to v1 so the UI works unchanged
 "Asks for OTP / PIN / password": (50, "take"), "Claims to be an official": (20, "press"),
 "Threatens arrest or case": (25, "press"), "Demands secrecy": (30, "press"),
 "Creates urgency": (10, "press"), "Asks for identity data": (15, "take"),
 "Asks for money transfer": (40, "take"), "Threatens service cut-off": (30, "press")}
P = {k: v for k, v in {
 "Asks for OTP / PIN / password": r"otp|ओटीपी|cvv|\bpin\b|पिन|पासवर्ड|password|कार्ड\s*नंबर|ஓடிபி|ஒடிபி|கடவுச்சொல்|ఓటీపీ|పాస్వర్డ్|ওটিপি|পাসওয়ার্ড",
 "Claims to be an official": r"cbi|सीबीआई|police|पुलिस|trai|ट्राई|customs|कस्टम|\bed\b|ईडी|rbi|आरबीआई|income tax|इनकम टैक्स|cyber|साइबर|कोर्ट|court|ऑफिसर|officer|சிபிஐ|போலீஸ்|அதிகாரி|சுங்கத்துறை|సీబీఐ|పోలీస్|అధికారి|కస్టమ్స్|সিবিআই|পুলিশ|অফিসার|কাস্টমস",
 "Threatens arrest or case": r"arrest|अरेस्ट|गिरफ्तार|warrant|वारंट|case\W+(is\W+)?(registered|filed)|case against|(केस|मामला)\s*(दर्ज|जुड़ा)|आपके\s*खिलाफ|जेल|jail|laundering|लॉन्ड्रिंग|\bfir\b|एफआईआर|கைது|வழக்கு|வாரண்ட்|சிறை|అరెస్ట్|కేసు|వారెంట్|జైలు|গ্রেফতার|গ্রেপ্তার|মামলা|ওয়ারেন্ট|জেল",
 "Demands secrecy": r"किसी\s*(को|से).{0,15}(मत|न|नहीं).{0,15}(बता|बात)|don'?t tell|do not tell|गोपनीय|confidential|quietly|யாரிடமும்.{0,10}(சொல்ல|கூற)|ఎవరికీ.{0,10}చెప్ప|কাউকে.{0,10}(বলবেন|জানাবেন)",
 "Creates urgency": r"अभी|तुरंत|right now|immediately|urgent|जल्दी|आज ही|वरना|உடனே|இப்போதே|உடனடியாக|వెంటనే|ఇప్పుడే|এখনই|এক্ষুনি",
 "Asks for identity data": r"aadhaar|aadhar|आधार|pan card|पैन कार्ड|kyc|केवाईसी|ஆதார்|ఆధార్|আধার",
 "Asks for money transfer": r"transfer\W+(\S+\s+){0,4}(money|amount|rupees|payment|funds?|₹|rs)|(money|payment|amount|rupees)\W+(\S+\s+){0,3}transfer|send\W+(\S+\s+){0,3}(money|rupees)|(pay|paying)\W+(\S+\s+){0,3}(fine|penalty)|(fine|penalty)\W+(\S+\s+){0,3}pay|(?:\bupi\b|यूपीआई).{0,30}(?:pay|payment|transfer|send|भुगतान|ट्रांसफर)|(?:pay|payment|transfer|send|भुगतान|ट्रांसफर).{0,30}(?:\bupi\b|यूपीआई)|जुर्माना|safe account|(पैसे|रुपये|राशि|भुगतान)\S*\s+(\S+\s+){0,3}(ट्रांसफर|भेज|जमा)|पैसे\s*(भेज|जमा)|பணம்.{0,10}(அனுப்ப|செலுத்த)|డబ్బు.{0,10}(పంపండి|పంపించ|చెల్లించ)|টাকা.{0,10}(পাঠান|জমা)|ট্রান্সফার",
 "Threatens service cut-off": r"बिजली.{0,20}(कट|बंद)|कनेक्शन.{0,15}(कट|बंद)|disconnect|डिस्कनेक्ट|digital arrest|डिजिटल अरेस्ट|மின்சாரம்.{0,15}(துண்டிக்|கட்)|டிஜிட்டல் கைது|కరెంట్.{0,15}(కట్|నిలిపి)|విద్యుత్.{0,15}(కట్|నిలిపి)|డిజిటల్ అరెస్ట్|বিদ্যুৎ.{0,15}(কেটে|বন্ধ)|ডিজিটাল অ্যারেস্ট"}.items()}
P = {k: re.compile(v, re.I) for k, v in P.items()}
NEG = re.compile(r"(?:never|do not|don'?t|कभी|मत|(?:^|\s)न)\s+(?:\S+\s+){0,3}(?:share|tell|give|disclose|provide|बता|दें|साझा)", re.I)
POST = re.compile(r"^(?:\\S+\\s+){0,6}?(?:न|नहीं|मत)\\s+(?:\\S+\\s+){0,2}?(?:बता|दें|साझा|करें)")

# Sensitive terms count only when paired with an actual disclosure request.
CREDENTIAL = r"(?:otp|ओटीपी|cvv|\bpin\b|पिन|पासवर्ड|password|card\s*number|ஓடிபி|ஒடிபி|கடவுச்சொல்|ఓటీపీ|పాస్వర్డ్|ওটিপি|পাসওয়ার্ড)"
ASK_CREDENTIAL = re.compile(
    rf"\b(?:share|tell|give|send|provide|read(?:\s+out)?|disclose|reveal|repeat|enter|type|submit|confirm)\b[^.!?;]{{0,45}}?{CREDENTIAL}"
    rf"|{CREDENTIAL}[^.!?;]{{0,35}}?\b(?:with me|to me|share|send|tell me|read it out)\b"
    rf"|(?:मुझे|हमें)?\s*(?:अपना|आपका)?\s*(?:ओटीपी|पिन|पासवर्ड)\s*(?:बताइए|बताएं|बता दीजिए|भेजिए|शेयर कीजिए)"
    rf"|(?:ओटीपी|पिन|पासवर्ड)\s*(?:मुझे|हमें)\s*(?:बताइए|बताएं|भेजिए)"
    rf"|(?:మీ\s*)?(?:ఓటీపీ|పిన్|పాస్వర్డ్)\s*(?:చెప్పండి|పంపండి|ఇవ్వండి)"
    rf"|(?:உங்கள்\s*)?(?:ஓடிபி|ஒடிபி|கடவுச்சொல்)\s*(?:சொல்லுங்கள்|அனுப்புங்கள்|கொடுங்கள்)"
    rf"|(?:আপনার\s*)?(?:ওটিপি|পাসওয়ার্ড)\s*(?:বলুন|পাঠান|দিন)", re.I)
LEGITIMATE_PAYMENT = re.compile(
    r"\b(?:emi|bill|installment|instalment)\b.{0,70}\b(?:due|reminder|scheduled)\b"
    r"|\b(?:pay|payment)\b.{0,35}\b(?:in|through|via)\s+(?:the\s+)?(?:official\s+)?app\b|\bupi\s+(?:option|payment)\b.{0,30}\bapp\b", re.I)
FRAUD, SUSPICIOUS = 70, 35


def negated(sent, m):
    context = sent[max(0, m.start() - 60):min(len(sent), m.end() + 20)]
    refusal = re.search(
        r"(?:never|do not|don't|does not|doesn't|will not|won't|cannot|can't)\b.{0,55}\b(?:ask|request|collect|need|require|share|tell|give|disclose|provide)\b",
        context, re.I)
    hindi_refusal = re.search(r"(?:कभी नहीं|मत|नहीं)\s*.{0,35}(?:माँग|मांग|बता|साझा|दे)", context)
    return bool(NEG.search(context) or refusal or hindi_refusal or POST.match(sent[m.end():].lstrip()))


CHAIN = ("Demands secrecy", "Claims to be an official")  # + arrest/cut-off = "digital arrest" pattern


def make_score(sessions):
    def score(sid, text):
        s = sessions.setdefault(sid, dict(score=0, hit=[], alerted=False))
        found = {}
        for sent in (c for c in re.split(r"[.!?।;\n]+", text) if c.strip()):
            for label, (w, kind) in W.items():
                # A mention or safety disclaimer is not an extraction attempt.
                if label == "Asks for OTP / PIN / password":
                    for x in ASK_CREDENTIAL.finditer(sent):
                        if not negated(sent, x):
                            found.setdefault(label, set()).add(x.group(0))
                    continue
                for x in P[label].finditer(sent):
                    if kind == "take" and negated(sent, x):
                        continue
                    if label == "Asks for money transfer" and LEGITIMATE_PAYMENT.search(sent):
                        continue
                    found.setdefault(label, set()).add(x.group(0))
        matches = [dict(label=k, texts=list(v)) for k, v in found.items()]
        for label in found:
            if label not in s["hit"]:
                s["hit"].append(label); s["score"] = min(100, s["score"] + W[label][0])
        hit = s["hit"]
        take = any(W[l][1] == "take" for l in hit); press = any(W[l][1] == "press" for l in hit)
        chain = all(c in hit for c in CHAIN) and ("Threatens arrest or case" in hit or "Threatens service cut-off" in hit)
        fraud = (s["score"] >= FRAUD and take and press) or chain
        shown = max(s["score"], FRAUD) if fraud else min(s["score"], FRAUD - 1)
        verdict = "FRAUD" if fraud else "SUSPICIOUS" if shown >= SUSPICIOUS else "SAFE"
        alert = verdict == "FRAUD" and not s["alerted"]
        if alert: s["alerted"] = True
        stage = "extraction" if take else "pressure" if press else "none"
        return dict(matches=matches, score=shown, verdict=verdict, signals=list(hit), alert=alert, stage=stage)
    return score
