"""Βρίσκει υποψήφιους εποπτευόμενους φορείς (ΝΠΔΔ, ΝΠΙΔ, ΔΕΥΑ, δημοτικές επιχειρήσεις) των πιλοτικών δήμων
στο ΚΗΜΔΗΣ, από τα ονόματα φορέων. Το αποτέλεσμα (entities_candidates.json) ελέγχεται από άνθρωπο
πριν μπει στο entities.json που διαβάζει το build.py.

Οι ημέρες που αποτυγχάνουν ξαναδοκιμάζονται έως 3 φορές στο τέλος. Τα ευρήματα προστίθενται σε όσα
υπάρχουν ήδη στο entities_candidates.json. Όλοι οι φορείς που συναντήθηκαν κρατιούνται στο
.cache/orgs_all.json, ώστε μια νέα αναζήτηση ονόματος να μη χρειάζεται νέα σάρωση.

Χρήση: python find_entities.py [--from YYYY-MM-DD] [--to YYYY-MM-DD]"""
import argparse, datetime as dt, json, pathlib, re
from khmdhs import all_pages

HERE = pathlib.Path(__file__).parent
STEMS = {"athina": ["ΑΘΗΝΑΙΩΝ"], "peiraias": ["ΠΕΙΡΑΙ"], "peristeri": ["ΠΕΡΙΣΤΕΡΙ"],
         "thessaloniki": ["ΘΕΣΣΑΛΟΝΙΚΗΣ"], "kalamaria": ["ΚΑΛΑΜΑΡΙ"], "thermi": ["ΘΕΡΜΗΣ"], "lavreotiki": ["ΛΑΥΡΕΩΤΙΚ"],
         "drama": ["ΔΡΑΜΑΣ"], "kastoria": ["ΚΑΣΤΟΡΙΑΣ"], "karditsa": ["ΚΑΡΔΙΤΣΑΣ"], "tripoli": ["ΤΡΙΠΟΛ"],
         "syros": ["ΣΥΡΟΥ-ΕΡΜΟΥΠΟΛ", "ΣΥΡΟΥ - ΕΡΜΟΥΠΟΛ", "ΕΡΜΟΥΠΟΛ"], "rethymno": ["ΡΕΘΥΜΝ"], "zagori": ["ΖΑΓΟΡΙ"], "kalavryta": ["ΚΑΛΑΒΡΥΤ"]}
EXCLUDE = r"ΠΕΡΙΦΕΡΕΙ|ΠΑΝΕΠΙΣΤΗΜ|ΝΟΣΟΚΟΜΕΙ|ΥΠΟΥΡΓΕΙ|ΔΙΚΑΣΤ|ΕΦΕΤΕΙ|ΕΦΟΡΕΙ|ΑΠΟΚΕΝΤΡΩΜΕΝΗ|ΣΥΝΔΕΣΜΟΣ ΔΗΜΩΝ|^ΔΗΜΟΣ "

ap = argparse.ArgumentParser()
ap.add_argument("--from", dest="d0", default="2026-06-01")
ap.add_argument("--to", dest="d1", default="2026-10-31")
args = ap.parse_args()

pilot = json.loads((HERE / "pilot.json").read_text(encoding="utf-8"))
own = {m["khmdhs_code"] for m in pilot["municipalities"]}
cand_path = HERE / "entities_candidates.json"
cand = json.loads(cand_path.read_text(encoding="utf-8")) if cand_path.exists() else {}
for k in STEMS: cand.setdefault(k, {})
orgs_path = HERE / ".cache" / "orgs_all.json"; orgs_path.parent.mkdir(exist_ok=True)
orgs = json.loads(orgs_path.read_text(encoding="utf-8")) if orgs_path.exists() else {}

def scan(d, res):
    for c in all_pages(res, {"dateFrom": d, "dateTo": d}):
        o = c.get("organization") or {}
        k, name = o.get("key"), (o.get("value") or "")
        if not k or k in own: continue
        cls = (c.get("classificationOfPublicLawOrganization") or {}).get("value")
        typ = (c.get("typeOfContractingAuthority") or {}).get("value")
        orgs[k] = {"name": name, "classification": cls, "type": typ}
        if cls != "ΟΤΑ": continue
        up = name.upper()
        for mid, stems in STEMS.items():
            if any(s in up for s in stems) and not re.search(EXCLUDE, up) and k not in cand[mid]:
                cand[mid][k] = {"name": name, "classification": cls, "type": typ}
                print("νέο:", mid, k, name, flush=True)

todo, day = [], dt.date.fromisoformat(args.d1)
while day >= dt.date.fromisoformat(args.d0):
    todo += [(day.isoformat(), "contract"), (day.isoformat(), "auction")]; day -= dt.timedelta(days=1)
for attempt in range(1, 4):
    failed = []
    for i, (d, res) in enumerate(todo):
        try: scan(d, res)
        except RuntimeError as e:
            failed.append((d, res)); print("αποτυχία", attempt, d, res, e, flush=True)
        if i % 20 == 0:
            orgs_path.write_text(json.dumps(orgs, ensure_ascii=False), encoding="utf-8")
    todo = failed
    print(f"γύρος {attempt}: {len(failed)} αποτυχίες", flush=True)
    if not failed: break

orgs_path.write_text(json.dumps(orgs, ensure_ascii=False), encoding="utf-8")
cand_path.write_text(json.dumps(cand, ensure_ascii=False, indent=1), encoding="utf-8")
print("τέλος", sum(len(v) for v in cand.values()), "υποψήφιοι·", len(orgs), "φορείς συνολικά· εκκρεμούν:", todo)
