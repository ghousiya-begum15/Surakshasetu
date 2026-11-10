"""Generate every sample call into the samples/ folder (uses Gnani Timbre credits).
Scam and genuine scenarios use different Timbre v2.5 voices.
Run:  python make_samples.py            (all languages)
      python make_samples.py hi-IN en-IN (only these)"""
import sys
from app import SCENARIOS, build_sample

langs = sys.argv[1:] or list(SCENARIOS)
for lang in langs:
    for kind in ("scam", "ok"):
        for i, (title, _) in enumerate(SCENARIOS[lang][kind]):
            try:
                print("saved", build_sample(lang, kind, i), "-", title)
            except Exception as e:
                print("FAILED", lang, kind, i, e)
