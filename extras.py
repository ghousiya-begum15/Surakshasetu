"""SurakshaSetu additive features. Nothing in app.py's existing routes changes.
Mounted by 3 appended lines in app.py. Written from docs.gnani.ai (Prisma v3 realtime, batch, voice cloning)."""
import os, re, io, json, time, asyncio, hashlib
from pathlib import Path
import requests, websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response, RedirectResponse
import app as A  # safe: imported at the bottom of app.py, after everything is defined

router = APIRouter()
BASE = "https://api.vachana.ai"
KEY = os.environ["GNANI_API_KEY"]
H = {"X-API-Key-ID": KEY}
VOICES = A.BASE / "voices"; VOICES.mkdir(exist_ok=True)
METRICS = []  # time-to-alert samples from streaming calls

# ---------- 1. Streaming Prisma v3 (browser -> this server -> Gnani WebSocket) ----------
@router.websocket("/ws/live")
async def ws_live(ws: WebSocket, sid: str = "", lang: str = "indic-auto"):
    """Browser sends raw 16 kHz mono Int16 PCM (any chunk size). We re-frame to the 1,024-byte frames Gnani requires
    and answer with JSON in the same shape as /api/analyze, so the existing UI renderer works unchanged."""
    await ws.accept()
    sid = sid or "ws" + str(time.time_ns())
    hdr = {"x-api-key-id": KEY, "x-model": "prisma-v3.0", "x-sample-rate": "16000", "x-format": "codemix",
           "lang_code": lang if lang in A.LANGUAGES or lang == "indic-auto" else "indic-auto",
           "x-min-silence-ms": "450", "x-keyterms": json.dumps(A.KEYTERMS)}  # json.dumps keeps the header ASCII
    t0 = time.time()
    try:
        try: up_cm = websockets.connect(BASE.replace("https", "wss") + "/stt/v3/stream", additional_headers=hdr)
        except TypeError: up_cm = websockets.connect(BASE.replace("https", "wss") + "/stt/v3/stream", extra_headers=hdr)
        async with up_cm as up:
            async def pump_up():
                buf = b""
                while True:
                    buf += await ws.receive_bytes()
                    while len(buf) >= 1024:
                        await up.send(buf[:1024]); buf = buf[1024:]
            async def pump_down():
                async for raw in up:
                    m = json.loads(raw)
                    if m.get("type") == "error":
                        await ws.send_json(dict(error=m.get("message", "Gnani streaming error"))); continue
                    text = (m.get("text") or "").strip() if m.get("type") == "transcript" else ""
                    if not text: continue
                    with A.lock:
                        A.stats["stt_calls"] += 1; A.stats["stt_audio_s"] += m.get("audio_duration_ms", 0) / 1000; A.stats["stt_ms"] += m.get("latency", 0)
                    det = m.get("detected_language_code") or "unknown"
                    out = dict(text=text, latency_ms=m.get("latency", 0), detected_language_code=det, transcript_language_code=det,
                               translation_applied=False, stats=A.stats_view(), **A.score(sid, text))
                    if out["alert"]: METRICS.append(dict(t=round(time.time() - t0, 1), lang=det, ts=time.time()))
                    await ws.send_json(out)
            tasks = [asyncio.create_task(pump_up()), asyncio.create_task(pump_down())]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in tasks: t.cancel()
    except (WebSocketDisconnect, websockets.ConnectionClosed):
        pass
    except Exception as e:
        try: await ws.send_json(dict(error=f"Streaming failed: {e}"))
        except Exception: pass

@router.get("/api/metrics")
def metrics():
    ts = sorted(m["t"] for m in METRICS)
    return dict(alerts=len(ts), median_s=ts[len(ts) // 2] if ts else None, p95_s=ts[int(len(ts) * .95) - 1] if len(ts) > 1 else (ts[0] if ts else None), samples=METRICS[-50:])

# ---------- 2. Warnings that name the trigger (Timbre, cached per signal + language) ----------
SIGNAL_TEXT = {  # add ta/te/bn lines with a native-speaker review; unknown pairs fall back to the existing generic warning
 "Asks for OTP / PIN / password": {"en-IN": "Warning! The caller is asking for your OTP or PIN. Never share it with anyone.", "hi-IN": "सावधान! कॉल करने वाला आपसे ओटीपी या पिन माँग रहा है। इसे किसी को न बताएं।"},
 "Asks for money transfer": {"en-IN": "Warning! The caller is asking you to send money. Do not transfer anything.", "hi-IN": "सावधान! कॉल करने वाला आपसे पैसे भेजने को कह रहा है। कोई पैसा ट्रांसफर न करें।"},
 "Threatens arrest or case": {"en-IN": "Warning! Real police never arrest anyone over a phone call. This is a scam.", "hi-IN": "सावधान! असली पुलिस फोन पर गिरफ्तारी नहीं करती। यह धोखाधड़ी है।"},
 "Demands secrecy": {"en-IN": "Warning! Scammers ask you to keep secrets. Tell someone you trust right now.", "hi-IN": "सावधान! धोखेबाज़ बात छिपाने को कहते हैं। अभी किसी भरोसेमंद व्यक्ति को बताइए।"},
}
@router.get("/api/warning/signal")
def warning_signal(lang: str = Query("hi-IN"), signal: str = Query(...)):
    text = SIGNAL_TEXT.get(signal, {}).get(lang)
    if lang not in A.LANGUAGES or not text:
        return RedirectResponse(f"/api/warning?lang={lang}")  # existing generic warning, unchanged
    path = A.SAMPLES / f"sig_{hashlib.md5(signal.encode()).hexdigest()[:8]}_{lang}.wav"
    try:
        if not path.exists(): path.write_bytes(A.synth(text, lang, "warning"))
        return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "no-store"})
    except Exception as e:
        return JSONResponse(dict(error=f"Gnani TTS failed: {e}"), 502)

# ---------- 3. Family-voice alert (Gnani voice cloning; consent required, only the embedding is kept) ----------
FAMILY_TEXT = {"hi-IN": "रुकिए! यह कॉल धोखाधड़ी हो सकती है। फोन काट दीजिए और किसी को ओटीपी या पैसे मत दीजिए।",
               "en-IN": "Please stop. This call may be a scam. Hang up, and do not share any OTP or send any money."}
slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "family"

@router.post("/api/voice/enroll")
async def enroll(name: str = Form(...), consent: bool = Form(...), audio_file: UploadFile = File(...)):
    if not consent:
        return JSONResponse(dict(error="The person whose voice this is must agree before you continue."), 400)
    raw = await audio_file.read()
    r = await run_in_threadpool(lambda: requests.post(BASE + "/api/v1/tts/voice-clone/embeddings", headers=H,
                                files={"audio_file": (audio_file.filename or "ref.wav", raw)}, timeout=90))
    j = r.json()
    if r.status_code != 200 or not j.get("success"):
        return JSONResponse(dict(error=str(j.get("error") or j)), 502)
    vid = slug(name); (VOICES / f"{vid}.json").write_text(json.dumps(dict(name=name, embedding=j["data"]["voice_clone_embedding"])))
    return dict(id=vid, name=name)  # audio itself is not saved; 5-30 s of clean speech is what Gnani asks for

@router.get("/api/voice/list")
def voice_list():
    return [dict(id=p.stem, name=json.loads(p.read_text())["name"]) for p in VOICES.glob("*.json")]

@router.delete("/api/voice/{vid}")
def voice_delete(vid: str):
    p = VOICES / f"{slug(vid)}.json"; p.exists() and p.unlink(); return dict(ok=True)

@router.get("/api/warning/family")
async def warning_family(voice: str = Query(...), lang: str = Query("hi-IN"), text: str = Query("")):
    p = VOICES / f"{slug(voice)}.json"
    if not p.exists(): return JSONResponse(dict(error="Voice not found. Enrol it first."), 404)
    body = dict(text=text or FAMILY_TEXT.get(lang, FAMILY_TEXT["hi-IN"]), model="vachana-vc-v1", speaker_embedding=json.loads(p.read_text())["embedding"],
                audio_config=dict(sample_rate=16000, num_channels=1, sample_width=2, encoding="linear_pcm", container="wav"))
    r = await run_in_threadpool(lambda: requests.post(BASE + "/api/v1/tts/inference", headers={**H, "Content-Type": "application/json"}, json=body, timeout=90))
    if r.status_code != 200: return JSONResponse(dict(error=f"Gnani voice cloning failed ({r.status_code})"), 502)
    return Response(r.content, media_type="audio/wav", headers={"Cache-Control": "no-store"})

# ---------- 4. Post-call report (Batch STT with speaker diarization) ----------
def _batch(raw: bytes, name: str, lang: str):
    cfg = dict(model="gnani-prisma-v2.5", language_code=lang, mode="transcribe", with_diarization=True, num_speakers=2, is_multi_channel=False, with_denoise=True)
    j = requests.post(BASE + "/stt/v3/batch/jobs", headers=H, files={"config": (None, json.dumps(cfg), "application/json"), "files": (name, raw)}, timeout=90).json()
    jid = j["job_id"]; requests.post(f"{BASE}/stt/v3/batch/jobs/{jid}/start", headers=H, timeout=30)
    for _ in range(30):  # poll every 10 s, up to 5 min
        time.sleep(10)
        st = requests.get(f"{BASE}/stt/v3/batch/jobs/{jid}", headers=H, timeout=30).json().get("status")
        if st in ("COMPLETED", "PARTIAL_FAILURE", "FAILED", "START_FAILED", "CANCELLED"): break
    fl = requests.get(f"{BASE}/stt/v3/batch/jobs/{jid}/files?status=COMPLETED", headers=H, timeout=30).json()
    files = fl if isinstance(fl, list) else (fl.get("files") or fl.get("data") or [])  # shape not shown in docs: verify once
    return [requests.get(f["transcript_url"], timeout=60).json() for f in files if f.get("transcript_url")]

@router.post("/api/report")
async def report(audio_file: UploadFile = File(...), lang: str = Form("hi-IN,en-IN")):
    raw = await audio_file.read()
    if len(raw) > 10_000_000: return JSONResponse(dict(error="Direct upload is limited to 10 MB per file."), 413)
    try: docs = await run_in_threadpool(_batch, raw, audio_file.filename or "call.wav", lang)
    except Exception as e: return JSONResponse(dict(error=f"Gnani batch failed: {e}"), 502)
    if not docs: return JSONResponse(dict(error="No transcript returned. Check the job in the Gnani dashboard."), 502)
    sid, rows, first = f"rep{time.time_ns()}", [], None
    for seg in docs[0].get("segments", []):
        r = A.score(sid, seg.get("text", ""))
        if r["alert"] and first is None: first = seg.get("start_time")
        rows.append(dict(start=seg.get("start_time"), end=seg.get("end_time"), speaker=seg.get("speaker_id"), text=seg.get("text"), score=r["score"], verdict=r["verdict"], signals=r["signals"]))
    A.sessions.pop(sid, None)
    return dict(language=docs[0].get("language_code"), duration_s=docs[0].get("duration_seconds"), first_alert_at_s=first,
                final_verdict=rows[-1]["verdict"] if rows else "SAFE", timeline=rows)

# ---------- 5. Scam awareness trainer (reuses your Timbre sample calls) ----------
@router.get("/api/trainer/lesson")
def lesson(lang: str = Query("hi-IN")):
    lang, i = A.pick("scam", lang if lang in A.SCENARIOS else "hi-IN")
    title, lines = A.SCENARIOS[lang]["scam"][i]
    sid = f"tr{time.time_ns()}"; hit = []
    for t in lines: hit = A.score(sid, t)["signals"]
    A.sessions.pop(sid, None)
    return dict(lang=lang, index=i, title=title, lines=lines, answer=hit, options=[r[0] for r in A.RULES])

@router.get("/api/trainer/audio")
def trainer_audio(lang: str = Query("hi-IN"), i: int = Query(0)):
    try: return FileResponse(A.build_sample(lang, "scam", i), media_type="audio/wav")
    except Exception as e: return JSONResponse(dict(error=f"Gnani TTS failed: {e}"), 502)
