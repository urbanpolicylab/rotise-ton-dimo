"""Υπολογίζει τους δείκτες του «Ρώτησε τον Δήμο σου» από το Open Data API του ΚΗΜΔΗΣ.

Τρέχει μία φορά την εβδομάδα (GitHub Actions). Γράφει μόνο συγκεντρωτικά στοιχεία
ανά δήμο: κανένα όνομα ή ΑΦΜ αναδόχου δεν φεύγει από τη μνήμη του script.

Οι δείκτες είναι περιγραφικοί ή ενδείξεις κινδύνου προς διερεύνηση. Δεν είναι ευρήματα
ελέγχου νομιμότητας. Πλήρεις ορισμοί: METHODOLOGY.md.

Χρήση: python build.py [--end YYYY-MM-DD] [--no-cache]
"""
import argparse, collections, datetime as dt, json, pathlib, statistics
from khmdhs import all_pages

ROOT = pathlib.Path(__file__).resolve().parent.parent
METHOD_VERSION = "0.4"
THRESHOLD = 30_000          # γενικό όριο απευθείας ανάθεσης, άρθρο 118 ν. 4412/2016 (χωρίς ΦΠΑ)
MAX_DIRECT = 60_000         # ανώτατο ειδικό όριο· πάνω από αυτό, η τιμή επισημαίνεται για έλεγχο
EXCLUDE_TITLE = ("ΠΡΟΓΡΑΜΜΑΤΙΚΗ ΣΥΜΒΑΣΗ", "ΠΡΟΓΡΑΜΜΑΤΙΚΗΣ ΣΥΜΒΑΣΗΣ")
DIRECT, NEGOTIATED = "6", "12"
BAND_LO, BAND_HI = 28_000, 30_000   # κλειστό διάστημα: 28.000 ≤ αξία ≤ 30.000
REPEAT_MIN = 3              # ίδιος ανάδοχος, ίδια ομάδα CPV, ≥3 αναθέσεις στο 12μηνο
UNKNOWN = "?"

def months_back(end, n=12):
    """Πρώτη ημέρα του μήνα που απέχει n-1 μήνες από τον μήνα του end (12 πλήρεις μήνες)."""
    y, m = end.year, end.month - (n - 1)
    while m <= 0:
        m += 12; y -= 1
    return dt.date(y, m, 1)

def windows(start, end, days=90):
    a = start
    while a <= end:
        b = min(a + dt.timedelta(days=days - 1), end)
        yield a.isoformat(), b.isoformat()
        a = b + dt.timedelta(days=1)

def contractor(c):
    m = ((c.get("contractingDataDetails") or {}).get("contractingMembersDataList") or [])
    ids = sorted((x.get("vatNumber") or x.get("name") or "").strip() for x in m)
    ids = [i for i in ids if i]
    return "|".join(ids) or UNKNOWN

def cpvs(c):
    return [cpv["key"] for o in (c.get("objectDetailsList") or []) for cpv in (o.get("cpvs") or []) if cpv.get("key")]

def cpv_prefix(c, n):
    """Το CPV της μεγαλύτερης σε αξία γραμμής του αντικειμένου, κομμένο στα n ψηφία."""
    best, best_v = None, -1.0
    for o in c.get("objectDetailsList") or []:
        keys = [x["key"] for x in (o.get("cpvs") or []) if x.get("key")]
        v = float(o.get("costWithoutVAT") or 0)
        if keys and v > best_v:
            best, best_v = keys[0], v
    return best[:n] if best else UNKNOWN

def dedupe(rows):
    seen, out = set(), []
    for i, c in enumerate(rows):
        key = c.get("referenceNumber") or f"__χωρίς_ΑΔΑΜ_{i}"
        if key not in seen:
            seen.add(key); out.append(c)
    return out

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
    year = lambda c: (c.get("submissionDate") or "")[:4]
    pct = lambda a, b: round(100 * a / b, 1) if b else None

    direct = [c for c in orig if proc(c) == DIRECT]
    nego = [c for c in orig if proc(c) == NEGOTIATED]
    flagged = [c for c in direct if raw(c) > MAX_DIRECT]
    fl = {id(c) for c in flagged}
    val = lambda c: 0.0 if id(c) in fl else raw(c)          # κύρια σειρά: χωρίς τις επισημασμένες τιμές

    n_all, v_all = len(orig), sum(map(val, orig))
    n_d, v_d = len(direct), sum(map(val, direct))
    v_all_raw, v_d_raw = sum(map(raw, orig)), sum(map(raw, direct))   # ανάλυση ευαισθησίας

    band = [c for c in direct if BAND_LO <= val(c) <= BAND_HI]

    # Επαναλαμβανόμενος ανάδοχος: ίδιος ανάδοχος + ίδια ομάδα CPV (3 ψηφία), ≥3 αναθέσεις
    pairs = collections.defaultdict(list)
    for c in direct:
        if contractor(c) != UNKNOWN: pairs[(contractor(c), cpv_prefix(c, 3))].append(val(c))
    rep = {k: v for k, v in pairs.items() if len(v) >= REPEAT_MIN}

    # Σωρευτική αξία συναφών αναθέσεων προς διερεύνηση (OCP R055, προσαρμοσμένο):
    # (α) ίδιος ανάδοχος + ίδια κλάση CPV (4 ψηφία) + ίδιο έτος, ≥2 αναθέσεις, άθροισμα > 30.000
    # (β) οποιοσδήποτε ανάδοχος + ίδια κλάση CPV (4 ψηφία) + ίδιο έτος, ≥2 αναθέσεις, άθροισμα > 30.000
    same_firm, any_firm = collections.defaultdict(list), collections.defaultdict(list)
    for c in direct:
        cls = cpv_prefix(c, 4)
        if cls == UNKNOWN: continue
        any_firm[(cls, year(c))].append(val(c))
        if contractor(c) != UNKNOWN: same_firm[(contractor(c), cls, year(c))].append(val(c))
    cum_same = {k: v for k, v in same_firm.items() if len(v) >= 2 and sum(v) > THRESHOLD}
    cum_any = {k: v for k, v in any_firm.items() if len(v) >= 2 and sum(v) > THRESHOLD}

    # Συγκέντρωση: μόνο αναθέσεις με γνωστό ανάδοχο
    by_firm = collections.Counter()
    for c in direct:
        if contractor(c) != UNKNOWN: by_firm[contractor(c)] += val(c)
    v_known = sum(by_firm.values())
    top5 = sum(v for _, v in by_firm.most_common(5))
    hhi = round(sum((100 * v / v_known) ** 2 for v in by_firm.values())) if v_known else None
    unknown_n = sum(1 for c in direct if contractor(c) == UNKNOWN)

    quarters = collections.defaultdict(lambda: [0, 0])
    for c in orig:
        d = (c.get("submissionDate") or "")[:7]
        if len(d) == 7:
            q = f"{d[:4]}-Q{(int(d[5:7]) - 1) // 3 + 1}"
            quarters[q][1] += 1
            if proc(c) == DIRECT: quarters[q][0] += 1

    return {
        "contracts": n_all, "value": round(v_all),
        "direct": n_d, "direct_value": round(v_d),
        "direct_share_count": pct(n_d, n_all), "direct_share_value": pct(v_d, v_all),
        "direct_share_value_incl_flagged": pct(v_d_raw, v_all_raw),
        "band_28_30": len(band), "band_share_of_direct": pct(len(band), n_d),
        "repeat_pairs": len(rep), "repeat_awards": sum(len(v) for v in rep.values()),
        "repeat_share_of_direct_value": pct(sum(sum(v) for v in rep.values()), v_d),
        "cum_same_pairs": len(cum_same), "cum_same_share_of_direct_value": pct(sum(sum(v) for v in cum_same.values()), v_d),
        "cum_any_groups": len(cum_any), "cum_any_share_of_direct_value": pct(sum(sum(v) for v in cum_any.values()), v_d),
        "top5_share_of_direct_value": pct(top5, v_known),
        "hhi_direct": hhi, "distinct_direct_contractors": len(by_firm), "unknown_contractor_awards": unknown_n,
        "negotiated_no_notice": len(nego), "negotiated_value": round(sum(map(val, nego))),
        "modifications": mods,
        "data_quality_flags": len(flagged), "flagged_value": round(sum(map(raw, flagged))),
        "by_quarter": {q: {"direct": a, "all": b} for q, (a, b) in sorted(quarters.items())},
    }

def summary(rows):
    n = sum(m["contracts"] for m in rows); nd = sum(m["direct"] for m in rows)
    v = sum(m["value"] for m in rows); vd = sum(m["direct_value"] for m in rows)
    med = lambda k, g=None: round(statistics.median([m[k] for m in rows if m[k] is not None and (g is None or m["group"] == g)] or [0]), 1)
    groups = sorted({m["group"] for m in rows})
    return {
        "municipalities": len(rows), "cases": n, "direct": nd, "value": v, "direct_value": vd,
        "pooled_direct_share_count": round(100 * nd / n, 1) if n else None,
        "pooled_direct_share_value": round(100 * vd / v, 1) if v else None,
        "median_direct_share_count": med("direct_share_count"),
        "median_direct_share_value": med("direct_share_value"),
        "by_group": {g: {"n": sum(1 for m in rows if m["group"] == g),
                         "median_direct_share_count": med("direct_share_count", g),
                         "median_direct_share_value": med("direct_share_value", g)} for g in groups},
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", help="τελευταία ημέρα περιόδου (προεπιλογή: τέλος προηγούμενου μήνα)")
    ap.add_argument("--no-cache", action="store_true", help="αγνοεί τα αποθηκευμένα δεδομένα")
    args = ap.parse_args()
    today = dt.date.today()
    end = dt.date.fromisoformat(args.end) if args.end else today.replace(day=1) - dt.timedelta(days=1)
    start = months_back(end, 12)
    pilot = json.loads((ROOT / "etl" / "pilot.json").read_text(encoding="utf-8"))
    out, failed = [], []
    for m in pilot["municipalities"]:
        if not m.get("khmdhs_code"):
            print("χωρίς κωδικό ΚΗΜΔΗΣ:", m["name"]); failed.append(m["name"]); continue
        got = {}
        try:
            for resource, tag in (("contract", ""), ("auction", "_awrd")):
                cache = ROOT / "etl" / ".cache" / f"{m['id']}{tag}_{start}_{end}.json"
                if cache.exists() and not args.no_cache:
                    rows = json.loads(cache.read_text(encoding="utf-8"))
                else:
                    rows = []
                    for a, b in windows(start, end):
                        rows += list(all_pages(resource, {"organizations": [m["khmdhs_code"]], "dateFrom": a, "dateTo": b}))
                    cache.parent.mkdir(exist_ok=True)
                    cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                got[resource] = dedupe(rows)
        except RuntimeError as e:
            print("παραλείφθηκε:", m["name"], e); failed.append(m["name"]); continue
        ind = indicators(*cases(got["contract"], got["auction"]))
        out.append({k: m.get(k, "") for k in ("id", "name", "group", "region", "khmdhs_code", "protocol_email", "email_type", "eservice_url")} | ind)
        print(f"{m['name']}: {ind['contracts']} προμήθειες, απευθείας {ind['direct_share_count']}% / {ind['direct_share_value']}%")
    data = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "method_version": METHOD_VERSION,
        "source": "ΚΗΜΔΗΣ Open Data API, https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help (CC BY 4.0)",
        "notes": "Μονάδα: καταγεγραμμένη υπόθεση προμήθειας (αρχική σύμβαση ή ανάθεση χωρίς σύνδεση με σύμβαση), όπως ανακτήθηκε από το ΚΗΜΔΗΣ· εξαιρούνται ακυρώσεις, τροποποιήσεις και προγραμματικές συμβάσεις. Απευθείας αναθέσεις άνω των 60.000 € χωρίς ΦΠΑ επισημαίνονται για έλεγχο και δεν μετρούν στις αξίες της κύριας σειράς· δίνεται και η τιμή με αυτές. Ημερομηνία = καταχώριση στο ΚΗΜΔΗΣ. Αξίες χωρίς ΦΠΑ.",
        "summary": summary(out),
        "municipalities": out,
        "incomplete": failed,
    }
    dest = ROOT / "site" / "data" / "indicators.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if failed and not out:
        raise SystemExit("Καμία επιτυχής ανάκτηση· τα προηγούμενα δεδομένα μένουν ως έχουν.")
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("γράφτηκε", dest)
    if failed:
        print("ΠΡΟΣΟΧΗ, δεν ολοκληρώθηκαν:", ", ".join(failed))

if __name__ == "__main__":
    main()
