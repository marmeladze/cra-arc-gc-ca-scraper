"""Join CRA open data CSVs and saved search list pages into one CSV, one row per charity.

Run: python3 build_final.py data/open_data data/list_pages charities_final.csv
"""
import collections, csv, glob, json, os, re, sys

csv.field_size_limit(10**7)
FIELDS = ["registration_number", "name", "account_name", "status", "status_effective_date", "website",
          "website_source_year", "designation", "category", "address_line_1", "address_line_2", "city",
          "province", "postal_code", "country", "latest_open_data_year", "in_search_list", "in_open_data"]


def read(path):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=enc) as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"cannot decode {path}")


def col(row, *names):
    """Value of the first matching column, ignoring case and spacing differences between years."""
    norm = {re.sub(r"[^a-z0-9]", "", (k or "").lower()): v for k, v in row.items()}
    for n in names:
        v = norm.get(n)
        if v and v.strip():
            return v.strip()
    return ""


def main(od_dir, list_dir, out_path):
    ident, web, ident_web, skipped = {}, {}, {}, []
    paths = sorted(glob.glob(f"{od_dir}/*.csv"), key=lambda p: os.path.basename(p)[-8:-4])
    for path in paths:  # oldest first, so newer years overwrite older ones
        kind, year = re.match(r"(ident|weburl)_(\d{4})", os.path.basename(path)).groups()
        rows = read(path)
        if not rows or not col(rows[0], "bn", "bnne"):
            skipped.append((os.path.basename(path), list(rows[0])[:6] if rows else []))
            continue
        if kind == "ident":
            for r in rows:
                ident[col(r, "bn", "bnne")] = dict(r, _year=year)
                # Older ident files carry their own Website column; used only as a fallback.
                if col(r, "website"):
                    ident_web[col(r, "bn", "bnne")] = ([col(r, "website")], year)
        else:
            by_bn = collections.defaultdict(list)
            for r in rows:
                url = col(r, "contacturl", "url")
                if url and url not in by_bn[col(r, "bn", "bnne")]:
                    by_bn[col(r, "bn", "bnne")].append(url)
            for bn, urls in by_bn.items():
                web[bn] = (urls, year)

    listed, pages = {}, 0
    for path in glob.glob(f"{list_dir}/page_*.json"):
        pages += 1
        with open(path, encoding="utf-8") as f:
            for r in json.load(f)["result"]:
                b = r["bnNumber"]
                listed[b["BNRoot"] + b["ProgramID"] + b["BNProgramAccountReferenceNumber"]] = r

    out = []
    for bn in sorted(ident.keys() | listed.keys()):
        i, l = ident.get(bn), listed.get(bn)
        urls, url_year = web.get(bn) or ident_web.get(bn) or ([], "")
        i = i or {}
        out.append({
            "registration_number": bn,
            "name": (l or {}).get("orgName") or col(i, "legalname", "name"),
            "account_name": col(i, "accountname"),
            "status": (l or {}).get("status", {}).get("englishText", ""),
            "status_effective_date": ((l or {}).get("statusEffectiveDate") or "")[:10],
            "website": "; ".join(urls),
            "website_source_year": url_year,
            "designation": col(i, "designation"),
            "category": col(i, "category"),
            "address_line_1": col(i, "addressline1"),
            "address_line_2": col(i, "addressline2"),
            "city": (l or {}).get("city") or col(i, "city"),
            "province": (l or {}).get("provinceStateCode") or col(i, "province"),
            "postal_code": col(i, "postalcode"),
            "country": col(i, "country"),
            "latest_open_data_year": i.get("_year", ""),
            "in_search_list": "yes" if l else "no",
            "in_open_data": "yes" if i else "no",
        })

    tmp = out_path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    os.replace(tmp, out_path)

    with open(out_path, newline="", encoding="utf-8-sig") as f:
        back = list(csv.DictReader(f))
    ids = [r["registration_number"] for r in back]
    print(f"open data files read: {len(paths) - len(skipped)}, skipped: {skipped}")
    print(f"list pages read: {pages}, list records: {len(listed)}")
    print(f"rows: {len(back)}, unique ids: {len(set(ids))}")
    print("well-formed ids:", sum(1 for x in ids if re.fullmatch(r"\d{9}[A-Z]{2}\d{4}", x)))
    print("in both / open data only / list only:",
          sum(r["in_search_list"] == "yes" and r["in_open_data"] == "yes" for r in back),
          sum(r["in_search_list"] == "no" for r in back),
          sum(r["in_open_data"] == "no" for r in back))
    for field in FIELDS:
        print(f"  filled {field}: {sum(1 for r in back if r[field])}")
    print("website by source year:", sorted(collections.Counter(r["website_source_year"] for r in back if r["website"]).items()))
    print("status:", collections.Counter(r["status"] or "(unknown)" for r in back).most_common(12))
    print("sample:", back[len(back) // 2])


if __name__ == "__main__":
    main(*sys.argv[1:4])
