"""Βρίσκει υποψήφιους εποπτευόμενους φορείς (ΝΠΔΔ, ΝΠΙΔ, ΔΕΥΑ, δημοτικές επιχειρήσεις) των πιλοτικών δήμων
στο ΚΗΜΔΗΣ, από τα ονόματα φορέων. Το αποτέλεσμα (entities_candidates.json) ελέγχεται από άνθρωπο
πριν μπει στο entities.json που διαβάζει το build.py."""
import datetime as dt, json, pathlib, re
from khmdhs import all_pages
STEMS = {"athina": ["ΑΘΗΝΑΙΩΝ"], "peiraias": ["ΠΕΙΡΑΙ"], "peristeri": ["ΠΕΡΙΣΤΕΡΙ"],
         "thessaloniki": ["ΘΕΣΣΑΛΟΝΙΚΗΣ"], "kalamaria": ["ΚΑΛΑΜΑΡΙ"], "lavreotiki": ["ΛΑΥΡΕΩΤΙΚ"],
         "drama": ["ΔΡΑΜΑΣ"], "kastoria": ["ΚΑΣΤΟΡΙΑΣ"], "karditsa": ["ΚΑΡΔΙΤΣΑΣ"], "tripoli": ["ΤΡΙΠΟΛ"],
         "syros": ["ΣΥΡΟΥ", "ΕΡΜΟΥΠΟΛ"], "rethymno": ["ΡΕΘΥΜΝ"], "zagori": ["ΖΑΓΟΡΙ"], "kalavryta": ["ΚΑΛΑΒΡΥΤ"]}
pilot = json.loads(pathlib.Path(__file__).with_name("pilot.json").read_text(encoding="utf-8"))
own = {m["khmdhs_code"] for m in pilot["municipalities"]}
seen, cand = set(), {k: {} for k in STEMS}
day = dt.date(2026, 10, 31)
while day > dt.date(2026, 5, 31):
    d = day.isoformat()
    for res in ("contract", "auction"):
        for c in all_pages(res, {"dateFrom": d, "dateTo": d}):
            o = c.get("organization") or {}
            k, name = o.get("key"), (o.get("value") or "").upper()
            if not k or k in seen or k in own: continue
            seen.add(k)
            cls = (c.get("classificationOfPublicLawOrganization") or {}).get("value")
            for mid, stems in STEMS.items():
                if any(s in name for s in stems) and not re.search(r"ΠΕΡΙΦΕΡΕΙ|ΠΑΝΕΠΙΣΤΗΜ|ΝΟΣΟΚΟΜΕΙ|ΥΠΟΥΡΓΕΙ|ΔΙΚΑΣΤ|ΕΦΟΡΕΙ|ΛΙΜΕΝΙΚ ΤΑΜΕΙ|ΑΠΟΚΕΝΤΡΩΜΕΝΗ", name):
                    cand[mid][k] = {"name": o.get("value"), "classification": cls, "type": (c.get("typeOfContractingAuthority") or {}).get("value")}
                    print(mid, k, o.get("value"), "|", cls, flush=True)
    day -= dt.timedelta(days=1)
pathlib.Path(__file__).with_name("entities_candidates.json").write_text(json.dumps(cand, ensure_ascii=False, indent=1), encoding="utf-8")
print("τέλος", sum(len(v) for v in cand.values()))
