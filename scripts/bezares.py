#!/usr/bin/env python3
"""Scrape Bezares official Chelsea/Muncie PTO cross-reference tables (wpDataTables)
into CSV in the HD Cross CSV-feed format. Resumable via state.json."""
import csv, json, re, sys, time, os, urllib.parse, urllib.request, http.cookiejar

PAGE = "https://bezares.com/en-us/bezares-chelsea-muncie-pto-correspondence-codes-cross-reference/"
AJAX = "https://bezares.com/wp-admin/admin-ajax.php?action=get_wdtable&table_id=%d"
TABLES = {1: "Chelsea", 2: "Muncie"}
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "500"))
PAGES_PER_RUN = int(os.environ.get("PAGES_PER_RUN", "10"))  # per table
UA = "Mozilla/5.0 (compatible; HDCrossFeedBot/1.0; +https://github.com/eze21212121)"
FIELDS = ["manufacturer","part_number","description","related_manufacturer","related_part_number",
          "relationship_type","source_name","source_url","source_confidence"]

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", UA)]

def get_nonces():
    html = op.open(PAGE, timeout=60).read().decode("utf8", "replace")
    return {int(m.group(1)): m.group(2) for m in
            re.finditer(r'id="wdtNonceFrontendServerSide_(\d+)"[^>]*value="([^"]+)"', html)} or \
           {int(m.group(2)): m.group(1) for m in
            re.finditer(r'value="([^"]+)"[^>]*id="wdtNonceFrontendServerSide_(\d+)"', html)}

def fetch(tid, nonce, start):
    body = urllib.parse.urlencode({"draw": "1", "start": start, "length": PAGE_SIZE,
        "order[0][column]": "0", "order[0][dir]": "asc", "wdtNonce": nonce,
        "sRangeSeparator": "|"}).encode()
    req = urllib.request.Request(AJAX % tid, data=body, headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": PAGE})
    for a in range(4):
        try:
            return json.loads(op.open(req, timeout=120).read())
        except Exception as e:
            print("retry", tid, start, e, file=sys.stderr); time.sleep(3 * (a + 1))
    raise SystemExit("fetch failed")

def main(out="feeds/bezares-latest.csv", state_path="state/bezares.json"):
    os.makedirs(os.path.dirname(out), exist_ok=True); os.makedirs(os.path.dirname(state_path), exist_ok=True)
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    nonces = get_nonces()
    rows = []
    for tid, brand in TABLES.items():
        start = state.get(str(tid), 0)
        total = None
        for _ in range(PAGES_PER_RUN):
            j = fetch(tid, nonces[tid], start)
            total = int(j["recordsTotal"])
            if start >= total: start = 0; break  # wrap around to re-verify from the top
            for r in j["data"]:
                other, bz, note = (r + ["", "", ""])[:3]
                other, bz = other.strip(), bz.strip()
                if not other or not bz: continue
                rows.append({"manufacturer": brand, "part_number": other, "description": re.sub(r"\s+", " ", note).strip(),
                    "related_manufacturer": "Bezares", "related_part_number": bz, "relationship_type": "cross",
                    "source_name": "bezares-official", "source_url": PAGE, "source_confidence": "0.99"})
            start += PAGE_SIZE
            time.sleep(1)
        state[str(tid)] = start
        print(brand, "cursor", start, "of", total)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows)
    json.dump(state, open(state_path, "w"))
    print("wrote", len(rows), "rows to", out)

if __name__ == "__main__":
    main()
