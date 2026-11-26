"""Βρίσκει τους κωδικούς φορέα ΚΗΜΔΗΣ των πιλοτικών δήμων και τους γράφει στο pilot.json.
Σαρώνει ημέρα προς ημέρα τις απευθείας αναθέσεις και σταματά όταν βρεθούν όλοι."""
import datetime as dt, json, pathlib, sys
from khmdhs import all_pages
P = pathlib.Path(__file__).with_name("pilot.json")
pilot = json.loads(P.read_text(encoding="utf-8"))
todo = {m["id"]: m for m in pilot["municipalities"] if not m.get("khmdhs_code")}
seen = {}
day = dt.date(2026, 10, 31)
while todo and day > dt.date(2026, 6, 1):
    d = day.isoformat()
    for c in all_pages("contract", {"dateFrom": d, "dateTo": d, "procedureType": "6"}):
        o = c.get("organization") or {}
        name = (o.get("value") or "").upper()
        if "ΔΗΜΟΣ" not in name or o.get("key") in seen: continue
        seen[o.get("key")] = name
        for mid, m in list(todo.items()):
            if m["match"] in name and "ΛΙΜΕΝ" not in name and "ΕΠΙΧΕΙΡ" not in name and "ΝΠΔΔ" not in name:
                m["khmdhs_code"] = o["key"]; m["khmdhs_name"] = o["value"]
                print("βρέθηκε:", m["name"], "→", o["key"], o["value"], flush=True); del todo[mid]
    print(d, "ΟΤΑ-φορείς:", len(seen), "υπόλοιποι:", len(todo), flush=True)
    day -= dt.timedelta(days=1)
P.write_text(json.dumps(pilot, ensure_ascii=False, indent=1), encoding="utf-8")
json.dump(seen, open(pathlib.Path(__file__).with_name("seen_orgs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("δεν βρέθηκαν:", [m["name"] for m in todo.values()])
