"""Slowly and resumably save the CRA charity search list, one JSON file per page.

Only the search list is fetched, never the captcha-protected detail records.
Run: python3 harvest_list.py data/list_pages
"""
import json, os, sys, time, urllib.error, urllib.request

URL = ("https://apps.cra-arc.gc.ca/ebci/hacc/ngcids/rest/api/cidsRequest/"
       "retrieveBasicSearchResult?q.ordrClmn=NAME&q.ordrRnk=ASC&dsrdPg={}")
PER_PAGE = 100
DELAY = 3  # seconds between successful requests
BACKOFFS = [300, 900, 1800, 3600]  # waits after consecutive failures; then give up


def fetch(page):
    req = urllib.request.Request(URL.format(page), headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def main(out_dir):
    total = None
    page = 1
    failures = 0
    while total is None or page <= (total + PER_PAGE - 1) // PER_PAGE:
        path = os.path.join(out_dir, f"page_{page}.json")
        if os.path.exists(path):
            if total is None:
                with open(path, encoding="utf-8") as f:
                    total = json.load(f)["totalCount"]
            page += 1
            continue
        try:
            data = fetch(page)
            if data["query"]["pageNumber"] != page or not data["result"]:
                raise ValueError(f"unexpected content for page {page}")
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError, OSError) as e:
            if failures >= len(BACKOFFS):
                print(f"STOPPED at page {page} after {failures} consecutive failures: {e}", flush=True)
                sys.exit(2)
            wait = BACKOFFS[failures]
            failures += 1
            print(f"page {page} failed ({e}); waiting {wait}s", flush=True)
            time.sleep(wait)
            continue
        failures = 0
        total = data["totalCount"]
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
        if page % 25 == 0:
            print(f"saved page {page}, total records {total}", flush=True)
        page += 1
        time.sleep(DELAY)
    print(f"DONE through page {page - 1}, total records {total}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
