"""Φτιάχνει μια αυτόνομη εκδοχή της σελίδας με ενσωματωμένα δεδομένα (για Artifact ή αποστολή)."""
import json, pathlib, sys
root = pathlib.Path(__file__).resolve().parent.parent
page = (root / "site" / "index.html").read_text(encoding="utf-8")
data = {"indicators": json.loads((root / "site/data/indicators.json").read_text(encoding="utf-8")),
        "requests": json.loads((root / "site/data/requests.json").read_text(encoding="utf-8"))}
blob = json.dumps(data, ensure_ascii=False).replace("<", "\u003c")
out = page.replace('<script type="application/json" id="embedded-data"></script>',
                   f'<script type="application/json" id="embedded-data">{blob}</script>', 1)
pathlib.Path(sys.argv[1]).write_text(out, encoding="utf-8")
print("έτοιμο:", sys.argv[1])
