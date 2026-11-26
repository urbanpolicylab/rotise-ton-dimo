"""Μικρός πελάτης για το Open Data API του ΚΗΜΔΗΣ (CC BY 4.0).
Τεκμηρίωση: https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help
Όριο: 350 αιτήματα/λεπτό, παράθυρο ημερομηνιών έως 180 ημέρες, 50 εγγραφές/σελίδα."""
import json, time, urllib.request, urllib.error
BASE = "https://cerpp.eprocurement.gov.gr/khmdhs-opendata"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json",
           "User-Agent": "rotise-ton-dimo-etl/0.1 (+https://www.urbanpolicylab.org)"}
def post(resource, body, page=0, tries=10):
    data = json.dumps(body).encode()
    for k in range(tries):
        try:
            req = urllib.request.Request(f"{BASE}/{resource}?page={page}", data=data, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=90) as r:
                time.sleep(0.2)  # ~300 αιτήματα/λεπτό, κάτω από το όριο
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:  # το API απαντά 404 όταν η αναζήτηση δεν έχει αποτελέσματα
                return {"content": [], "last": True, "totalPages": 0, "totalElements": 0}
            time.sleep(60 if e.code == 429 else min(2 ** k, 60))
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            wait = min(2 ** k, 60)
            if isinstance(e, urllib.error.HTTPError) and e.code == 429: wait = 60
            time.sleep(wait)
    raise RuntimeError(f"ΚΗΜΔΗΣ: αποτυχία μετά από {tries} προσπάθειες ({resource}, σελίδα {page})")
MAX_PAGES = 100  # το API δεν σερβίρει πέρα από 100 σελίδες ανά αναζήτηση

def all_pages(resource, body):
    """Όλες οι εγγραφές μιας αναζήτησης. Αν ξεπερνά τις 100 σελίδες,
    χωρίζει το διάστημα ημερομηνιών στα δύο και ξαναρωτά."""
    import datetime as dt
    first = post(resource, body, 0)
    if first.get("totalPages", 1) > MAX_PAGES and body.get("dateFrom") and body.get("dateTo"):
        a, b = dt.date.fromisoformat(body["dateFrom"]), dt.date.fromisoformat(body["dateTo"])
        if a < b:
            mid = a + (b - a) // 2
            yield from all_pages(resource, {**body, "dateTo": mid.isoformat()})
            yield from all_pages(resource, {**body, "dateFrom": (mid + dt.timedelta(days=1)).isoformat()})
            return
    yield from first.get("content", [])
    page = 1
    while not first.get("last", True) and page < min(first.get("totalPages", 1), MAX_PAGES):
        j = post(resource, body, page)
        yield from j.get("content", [])
        if j.get("last", True): break
        page += 1
