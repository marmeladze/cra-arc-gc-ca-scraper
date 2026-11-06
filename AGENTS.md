# CRA charities dataset

Builds one CSV of Canadian charities, one row per registration number, from Canada Revenue Agency (CRA) public data.

- `charities_final.csv`: the merged output, committed to the repo
- `build_final.py`: joins the sources into that CSV
- `harvest_list.py`: slow, resumable crawler for the CRA search list
- `data/`: source files, git-ignored and about 428 MB, so a fresh clone doesn't have them

## Methodology

There are two sources, joined on the registration number:

1. **Open data (the base).** The yearly "List of charities" datasets on open.canada.ca, 1990-2024, under the Open Government Licence - Canada. The build uses the Identification files (`ident_<year>.csv`, 1990-2024) and the Charity Contact Web Addresses files (`weburl_<year>.csv`, 2009-2024).
2. **CRA search list (the only source of status).** `retrieveBasicSearchResult`, 100 records per page, 139,456 records and so 1,395 pages when checked on 2026-11-06.

How the join resolves each field:

- Newer open data years overwrite older ones, so each charity keeps its most recent address and name details.
- `website` comes from the newest `weburl` file listing that charity. If none does, it falls back to the `Website` column in the 2003-2008 Identification files.
- `name`, `city` and `province` prefer the search list when a charity is in it.
- `status` and `status_effective_date` come only from the search list.

Results of the 2026-11-06 build: 134,958 unique charities, 42,454 with a website, and 200 with a status (search list pages 1 and 42 only).

## Reading `charities_final.csv`

The file is UTF-8 with a BOM, so read it with `encoding="utf-8-sig"`.

| Column | Meaning |
|---|---|
| `registration_number` | Unique ID, such as `136747276RR0001` |
| `name`, `account_name` | Search list name or legal name; account name from open data |
| `status`, `status_effective_date` | From the search list, date as `YYYY-MM-DD` |
| `website` | Several URLs are joined with `; `. Values are raw and often have no scheme |
| `website_source_year` | The data year the website came from |
| `designation`, `category` | CRA codes, explained in the Codes Lists PDF on each dataset page |
| `address_line_1`, `address_line_2`, `city`, `province`, `postal_code`, `country` | Mailing address |
| `latest_open_data_year` | Newest Identification file containing the charity |
| `in_search_list`, `in_open_data` | `yes` or `no` for each source |

Do not over-read these fields:

- **A blank `status` means unknown.** It doesn't mean registered or revoked.
- **`latest_open_data_year` is not a status.** Some revoked charities still appear in the 2024 file.
- **A blank `website` doesn't prove there is no website.** The source may just not list one.
- **Older websites may be dead.** Filter on `website_source_year` if you need recent ones: 34,095 are from 2024 and the rest are older.
- **Don't assume IDs end in `RR0001`.** Some end in `RR0002` or `RR0004`. Build IDs from all three `bnNumber` fields.

## How to run

Needs Python 3 and its standard library only. Run everything from the repo root.

**1. Download the open data.** This takes a while because the portal is slow and often returns 504, so the script retries and skips files it already has. Rerun it until it prints `missing: []`.

```python
import json, os, re, time, urllib.request

API = "https://open.canada.ca/data/api/3/action/package_search?q=title:%22List%20of%20charities%22&rows=60"
OUT = "data/open_data"
os.makedirs(OUT, exist_ok=True)
os.makedirs("data/list_pages", exist_ok=True)

missing = []
for pkg in json.load(urllib.request.urlopen(API, timeout=120))["result"]["results"]:
    match = re.match(r"(\d{4}) List of charities", pkg["title"])
    if not match:
        continue
    for res in pkg["resources"]:
        name = (res.get("name") or "").strip().lower()
        kind = "ident" if name == "identification" else "weburl" if "web address" in name else None
        if not kind or (res.get("format") or "").upper() != "CSV":
            continue
        path = f"{OUT}/{kind}_{match.group(1)}.csv"
        url = res["url"] if res["url"].startswith("http") else "https://open.canada.ca" + res["url"]
        for attempt in range(3):
            if os.path.exists(path):
                break
            try:
                with urllib.request.urlopen(url, timeout=200) as resp:
                    body = resp.read()
                with open(path + ".tmp", "wb") as f:
                    f.write(body)
                os.replace(path + ".tmp", path)
            except OSError as e:
                print("retrying", path, e)
                time.sleep(15)
        if not os.path.exists(path):
            missing.append(path)
print("files:", len(os.listdir(OUT)), "missing:", missing)
```

A complete download is 51 files.

**2. Optional: crawl the search list for status.**

```
python3 -I harvest_list.py data/list_pages
```

It pauses 3 seconds between pages, resumes from saved pages, and stops by itself after repeated failures. A full run takes hours. See the access rules below before running it.

**3. Build the CSV.**

```
python3 -I build_final.py data/open_data data/list_pages charities_final.csv
```

Check the printed summary: the row count should equal the unique ID count, and all IDs should be well-formed. With no search list pages, status is blank on every row. The committed CSV also used pages 1 and 42, which aren't in the repo, so a fresh build without them has 10 fewer rows and differs from the committed file.

## Access rules

- **Don't bypass the captcha.** Charity detail pages such as `dsplyRprtngPrd/<id>` run hCaptcha until `userValid` is true. The `retrieveReportingPeriod` JSON returns the full record with `userValid: false`, so the check can be skipped technically, but don't scrape it or automate solving the captcha without the repo owner's explicit decision.
- **Respect refusals.** On 2026-11-06 the search endpoint began returning HTTP 417 with `outageError` after a small number of requests, cause unknown. Back off and stop if it continues. Don't rotate IPs or spoof headers, and don't increase the crawl rate.
- **Credit the source.** Reuse of the open data is subject to the Open Government Licence - Canada, which requires attribution.
- **Never commit secrets or local files.** `.ghtok`, `start.txt`, `data/` and `charities_poc_pages_*.csv` are git-ignored. Never print `.ghtok` or put its contents in a remote URL or git config.

## Getting complete status data

CRA's [request form](https://www.canada.ca/en/revenue-agency/services/charities-giving/charities/guidance-videos-forms/request-charities-listings.html) offers a CSV that lists registration number, effective date of status, names, address, email and website, including revoked and annulled charities. CRA says most requests take at least six business days. Prefer this to crawling if you need status for every record. As of 2026-11-06 it hasn't been tried for this project.

## Sources

- [2024 List of charities](https://open.canada.ca/data/en/dataset/80c00cdb-1358-415c-bb8b-0de7f12675b8)
- [CRA charity search](https://apps.cra-arc.gc.ca/ebci/hacc/srch/pub/dsplyBscSrch?request_locale=en)
