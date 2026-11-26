"""Υπολογίζει τους δείκτες του «Ρώτησε τον Δήμο σου» από το Open Data API του ΚΗΜΔΗΣ.

Τρέχει μία φορά την εβδομάδα (GitHub Actions). Γράφει μόνο συγκεντρωτικά στοιχεία
ανά δήμο: κανένα όνομα ή ΑΦΜ αναδόχου δεν φεύγει από τη μνήμη του script.
Χρήση: python build.py [--end YYYY-MM-DD]
"""
import argparse, collections, datetime as dt, json, pathlib
from khmdhs import all_pages

ROOT = pathlib.Path(__file__).resolve().parent.parent
METHOD_VERSION = "0.3"
THRESHOLD = 30_000                      # όριο άρθρου 118 ν. 4412/2016 (χωρίς ΦΠΑ)
HHI_HIGH = 1_800                        # OCP Red Flags 2024, R051
MAX_DIRECT = 60_000                     # πάνω από αυτό, απευθείας ανάθεση = πιθανό λάθος καταχώρισης
EXCLUDE_TITLE = ("ΠΡΟΓΡΑΜΜΑΤΙΚΗ ΣΥΜΒΑΣΗ", "ΠΡΟΓΡΑΜΜΑΤΙΚΗΣ ΣΥΜΒΑΣΗΣ")
DIRECT, NEGOTIATED = "6", "12"
BAND_LO, BAND_HI = 28_000, 30_000      # ζώνη κάτω από το όριο του άρθρου 118
REPEAT_MIN = 3                          # ίδιος ανάδοχος, ίδια ομάδα CPV, ≥3 αναθέσεις/12μηνο

def windows(start, end, days=180):
    a = start
    while a <= end:
        b = min(a + dt.timedelta(days=days - 1), end)
        yield a.isoformat(), b.isoformat()
        a = b + dt.timedelta(days=1)

def contractor(c):
    m = ((c.get("contractingDataDetails") or {}).get("contractingMembersDataList") or [])
    return "|".join(sorted((x.get("vatNumber") or x.get("name") or "?") for x in m)) or "?"

def cpv_group(c):
    for o in c.get("objectDetailsList") or []:
        for cpv in o.get("cpvs") or []:
            if cpv.get("key"): return cpv["key"][:3]
    return "?"

def cases(contracts, awards):
    """Υποθέσεις προμήθειας: αρχικές συμβάσεις + αναθέσεις χωρίς σύνδεση με σύμβαση.
    Εξαιρούνται ακυρωμένες, τροποποιήσεις και προγραμματικές συμβάσεις."""
    title_ok = lambda c: not any(x in (c.get("title") or "").upper() for x in EXCLUDE_TITLE)
    out = [c for c in contracts if not c.get("cancelled") and not c.get("prevReferenceNo") and title_ok(c)]
    linked = set()
    for c in contracts:
        if c.get("auctionRefNo"): linked.add(c["auctionRefNo"])
        for o in c.get("objectDetailsList") or []:
            if o.get("requestRefNo", "") and "AWRD" in o["requestRefNo"]: linked.add(o["requestRefNo"])
    out += [a for a in awards if not a.get("cancelled") and not a.get("contractRefNo")
            and not a.get("amendsAuctionRefNo") and a.get("referenceNumber") not in linked and title_ok(a)]
    mods = sum(1 for c in contracts if not c.get("cancelled") and c.get("prevReferenceNo"))
    return out, mods

def indicators(orig, mods):
    raw = lambda c: float(c.get("totalCostWithoutVAT") or 0)
    proc = lambda c: (c.get("procedureType") or {}).get("key")
    suspect = [c for c in orig if proc(c) == DIRECT and raw(c) > MAX_DIRECT]
    sus_ids = {id(c) for c in suspect}
    val = lambda c: 0.0 if id(c) in sus_ids else raw(c)
    direct = [c for c in orig if proc(c) == DIRECT]
    nego = [c for c in orig if proc(c) == NEGOTIATED]
    n_all, v_all = len(orig), sum(map(val, orig))
    n_d, v_d = len(direct), sum(map(val, direct))
    band = [c for c in direct if BAND_LO <= val(c) < BAND_HI]
    pairs = collections.defaultdict(list)
    for c in direct: pairs[(contractor(c), cpv_group(c))].append(val(c))
    rep = {k: v for k, v in pairs.items() if len(v) >= REPEAT_MIN and k[0] != "?"}
    by_firm = collections.Counter()
    for c in direct: by_firm[contractor(c)] += val(c)
    top5 = sum(v for _, v in by_firm.most_common(5))
    # OCP R051: δείκτης Herfindahl-Hirschman στην αξία των απευθείας αναθέσεων (0-10.000)
    hhi = round(sum((100 * v / v_d) ** 2 for v in by_firm.values())) if v_d else None
    # OCP R055: ίδιος ανάδοχος + ίδια ομάδα CPV + ίδιο ημερολογιακό έτος, άθροισμα > όριο
    yearly = collections.defaultdict(list)
    for c in direct:
        y = (c.get("submissionDate") or "")[:4]
        if contractor(c) != "?": yearly[(contractor(c), cpv_group(c), y)].append(val(c))
    r055 = {k: v for k, v in yearly.items() if len(v) >= 2 and sum(v) > THRESHOLD}
    quarters = collections.defaultdict(lambda: [0, 0])
    for c in orig:
        d = (c.get("submissionDate") or "")[:7]
        if len(d) == 7:
            q = f"{d[:4]}-Q{(int(d[5:7]) - 1) // 3 + 1}"
            quarters[q][1] += 1
            if proc(c) == DIRECT: quarters[q][0] += 1
    pct = lambda a, b: round(100 * a / b, 1) if b else None
    return {
        "contracts": n_all, "value": round(v_all),
        "direct": n_d, "direct_value": round(v_d),
        "direct_share_count": pct(n_d, n_all), "direct_share_value": pct(v_d, v_all),
        "band_28_30": len(band), "band_share_of_direct": pct(len(band), n_d),
        "repeat_pairs": len(rep), "repeat_awards": sum(len(v) for v in rep.values()),
        "repeat_share_of_direct_value": pct(sum(sum(v) for v in rep.values()), v_d),
        "top5_share_of_direct_value": pct(top5, v_d),
        "hhi_direct": hhi, "hhi_high": (hhi is not None and hhi > HHI_HIGH),
        "r055_pairs": len(r055), "r055_awards": sum(len(v) for v in r055.values()),
        "r055_share_of_direct_value": pct(sum(sum(v) for v in r055.values()), v_d),
        "distinct_direct_contractors": len(by_firm),
        "negotiated_no_notice": len(nego), "negotiated_value": round(sum(map(val, nego))),
        "modifications": mods,
        "data_quality_flags": len(suspect),
        "by_quarter": {q: {"direct": a, "all": b} for q, (a, b) in sorted(quarters.items())},
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", help="τελευταία ημέρα περιόδου (προεπιλογή: τέλος προηγούμενου μήνα)")
    args = ap.parse_args()
    today = dt.date.today()
    end = dt.date.fromisoformat(args.end) if args.end else today.replace(day=1) - dt.timedelta(days=1)
    start = (end.replace(day=1) - dt.timedelta(days=334)).replace(day=1)
    pilot = json.loads((ROOT / "etl" / "pilot.json").read_text(encoding="utf-8"))
    out, failed = [], []
    for m in pilot["municipalities"]:
        if not m.get("khmdhs_code"):
            print("χωρίς κωδικό ΚΗΜΔΗΣ:", m["name"]); continue
        got = {}
        try:
            for resource, tag in (("contract", ""), ("auction", "_awrd")):
                cache = ROOT / "etl" / ".cache" / f"{m['id']}{tag}_{start}_{end}.json"
                if cache.exists():
                    rows = json.loads(cache.read_text(encoding="utf-8"))
                else:
                    rows = []
                    for a, b in windows(start, end, days=90):
                        rows += list(all_pages(resource, {"organizations": [m["khmdhs_code"]], "dateFrom": a, "dateTo": b}))
                    cache.parent.mkdir(exist_ok=True)
                    cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                seen, uniq = set(), []
                for c in rows:
                    if c.get("referenceNumber") not in seen:
                        seen.add(c.get("referenceNumber")); uniq.append(c)
                got[resource] = uniq
        except RuntimeError as e:
            print("παραλείφθηκε (θα ξαναδοκιμαστεί):", m["name"], e); failed.append(m["name"]); continue
        ind = indicators(*cases(got["contract"], got["auction"]))
        out.append({k: m.get(k, "") for k in ("id", "name", "group", "region", "khmdhs_code", "protocol_email", "email_type", "eservice_url")} | ind)
        print(f"{m['name']}: {ind['contracts']} συμβάσεις, απευθείας {ind['direct_share_count']}% / {ind['direct_share_value']}%")
    data = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "method_version": METHOD_VERSION,
        "source": "ΚΗΜΔΗΣ Open Data API, https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help (CC BY 4.0)",
        "notes": "Μονάδα μέτρησης: υπόθεση προμήθειας = αρχική σύμβαση ή ανάθεση χωρίς σύνδεση με σύμβαση· εξαιρούνται ακυρώσεις, τροποποιήσεις και προγραμματικές συμβάσεις. Απευθείας αναθέσεις άνω των 60.000 € χωρίς ΦΠΑ θεωρούνται πιθανά λάθη καταχώρισης και δεν μετρούν στις αξίες. Ημερομηνία = καταχώριση στο ΚΗΜΔΗΣ. Αξίες χωρίς ΦΠΑ.",
        "municipalities": out,
        "incomplete": failed,
    }
    dest = ROOT / "site" / "data" / "indicators.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("γράφτηκε", dest)
    if failed:
        print("ΠΡΟΣΟΧΗ, δεν ολοκληρώθηκαν:", ", ".join(failed))

if __name__ == "__main__":
    main()
