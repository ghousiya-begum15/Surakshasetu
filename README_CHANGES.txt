SURAKSHASETU - GNANI-ONLY UPDATED BUILD

Included changes:
1. Live call mode uses Gnani Prisma v3.0 with indic-auto language detection.
2. Recording test mode has separate Call Language and Transcript Language selectors.
3. Prisma transcribes the spoken language. This build does not claim to translate transcripts across languages because no verified Gnani translation API is configured. The UI explains this limitation.
4. Scam and genuine sample calls use separate configured Timbre v2.5 voices. Voice availability depends on the voices enabled for your Gnani account/model. If a voice is rejected, check the catalogue with:
   python -c "from gnani.tts import GnaniTTSClient; print(GnaniTTSClient.supported_voices(model='timbre-v2.5'))"
5. Scam warning audio is generated in Hindi, English, Telugu, Tamil, or Bengali using Gnani Timbre. In recording mode it follows the selected Transcript Language. In live mode it follows Prisma's detected language. Hindi is the fallback if the detected language is unavailable.
6. Warning audio is cached separately by language. The alert message text is manually provided in each language; no external translation service is used.
7. The app serves static/index.html and falls back to root index.html.

RUN (Windows CMD):
  venv\Scripts\activate
  set GNANI_API_KEY=YOUR_EXISTING_KEY
  python -m pip install -r requirements.txt
  python -m uvicorn app:app --reload --port 8000
Open http://localhost:8000

To pre-generate sample calls (uses Gnani Timbre credits):
  python make_samples.py

Note: warning audio is generated on first alert for each language and then cached. Timbre voice IDs in the code must be enabled in your Gnani account for timbre-v2.5. No API key is included in this archive.


CONTEXT-AWARE DETECTOR UPDATE (2026-11-10)
- The newer context-aware engine (engine_v2.py) is now enabled by default for live and recording analysis.
- OTP/PIN/password mentions are counted only when the caller appears to ask the listener to disclose the credential. General warnings such as "We do not collect OTPs or passwords" and "Never share your OTP" do not trigger the credential signal.
- UPI mentions are checked in payment context; routine EMI/bill reminders and ordinary in-app payment wording are treated as legitimate contexts by the current rule set.
- Existing /api/analyze and WebSocket response shapes are retained. Gnani Prisma STT and Timbre TTS integration are unchanged.
- This remains a transparent rule-based contextual detector, not an LLM classifier. It can still miss novel scam wording or misclassify ambiguous calls; test with varied real-world-like scripts before relying on it.
- To temporarily use the previous detector, set SCAM_ENGINE=v1 before starting the server. Normally leave this unset.
