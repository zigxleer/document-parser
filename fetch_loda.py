"""
Fetch the consolidated (legiPart) version of a French legal document and save as CSV.
Use this for older documents where jorfPart returns no articles.

Usage:
  # Whole text
  python fetch_loda_to_csv.py LEGITEXT000006074220

  # Specific section only
  python fetch_loda_to_csv.py LEGITEXT000006074220 --section LEGISCTA000018488409

  # Multiple whole texts
  python fetch_loda_to_csv.py JORFTEXT000000643230 JORFTEXT000000866441
"""

import csv
import json
import re
import sys
from datetime import date
import requests

TOKEN_URL     = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
LODA_URL      = "https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app/consult/legiPart"
CLIENT_ID     = "d24864d7-f5d3-4305-a5fc-fa2a70556816"
CLIENT_SECRET = "88eb0f16-78a2-4dda-84b7-df9228fb2544"


def get_token():
    resp = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "openid",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_loda(token, text_id):
    body = {"textId": text_id, "date": date.today().strftime("%Y-%m-%d")}
    resp = requests.post(
        LODA_URL,
        headers={
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        json=body,
    )
    resp.raise_for_status()
    return resp.json()


def filter_by_section(data, section_id):
    """Return a copy of data with only articles whose path contains the section_id."""
    def _filter(sections, articles):
        filtered_sections = []
        for s in sections:
            child_sections, child_articles = _filter(s.get("sections", []), s.get("articles", []))
            if s.get("cid") == section_id or s.get("id", "").startswith(section_id):
                # Include entire subtree under this section
                filtered_sections.append(s)
            elif child_sections or child_articles:
                sc = dict(s)
                sc["sections"] = child_sections
                sc["articles"] = child_articles
                filtered_sections.append(sc)

        filtered_articles = [
            a for a in articles
            if section_id in (a.get("path") or "")
        ]
        return filtered_sections, filtered_articles

    filtered_sections, filtered_articles = _filter(data.get("sections", []), data.get("articles", []))
    result = dict(data)
    result["sections"] = filtered_sections
    result["articles"] = filtered_articles
    return result


def html_to_text(html):
    if not html:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
    text = text.replace("&laquo;", "«").replace("&raquo;", "»")
    text = text.replace("&eacute;", "é").replace("&egrave;", "è")
    text = text.replace("&agrave;", "à").replace("&ccedil;", "ç")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return text.strip()


def collect_articles(sections, articles):
    items = (
        [(s.get("intOrdre", 0), "section", s) for s in sections] +
        [(a.get("intOrdre", 0), "article", a) for a in articles]
    )
    for _, kind, item in sorted(items, key=lambda x: x[0]):
        if kind == "section":
            yield from collect_articles(item.get("sections", []), item.get("articles", []))
        else:
            yield item


def clean(text):
    if not text:
        return text
    return " ".join(text.replace("\r\n", " ").replace("\r", " ").split())


def find_section_title(sections, section_id):
    """Return the title of the section with the given CID."""
    for s in sections:
        if s.get("cid") == section_id:
            return s.get("title", "")
        found = find_section_title(s.get("sections", []), section_id)
        if found is not None:
            return found
    return None


def to_csv(data, out_path, section_id=None):
    # Compute how many pathTitle entries to skip when filtering to a section
    offset = 0
    if section_id:
        sec_title = find_section_title(data.get("sections", []), section_id)
        if sec_title:
            # Find its position in the first article's pathTitle
            for art in collect_articles(data.get("sections", []), data.get("articles", [])):
                path = art.get("pathTitle") or []
                for i, title in enumerate(path):
                    if title == sec_title:
                        offset = i + 1  # skip section itself and all its ancestors
                        break
                break

    rows = []
    for art in collect_articles(data.get("sections", []), data.get("articles", [])):
        path = (art.get("pathTitle") or [])[offset:]
        rows.append({
            "Level 1 Header": clean(path[0]) if len(path) > 0 else "",
            "Level 2 Header": clean(path[1]) if len(path) > 1 else "",
            "Level 3 Header": clean(path[2]) if len(path) > 2 else "",
            "Section": art.get("num", ""),
            "Notes": html_to_text(art.get("content", "")),
        })
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Level 1 Header", "Level 2 Header", "Level 3 Header", "Section", "Notes"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_loda_to_csv.py TEXT_ID [--section SECTION_ID]")
        sys.exit(1)

    # Parse args: collect text IDs, watch for --section flag
    text_ids = []
    section_id = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--section" and i + 1 < len(args):
            section_id = args[i + 1]
            i += 2
        else:
            text_ids.append(args[i])
            i += 1

    if not text_ids:
        print("ERROR: no text ID provided.")
        sys.exit(1)

    if section_id and len(text_ids) > 1:
        print("ERROR: --section can only be used with a single text ID.")
        sys.exit(1)

    print("Getting token...")
    token = get_token()

    for text_id in text_ids:
        # If a LEGISCTA ID is passed directly, auto-filter to that section
        effective_section = section_id
        if text_id.startswith("LEGISCTA"):
            effective_section = text_id

        label = f"{text_id}" + (f" section={effective_section}" if effective_section and effective_section != text_id else "")
        print(f"Fetching {label}...")
        try:
            data = fetch_loda(token, text_id)
            if effective_section:
                data = filter_by_section(data, effective_section)
        except requests.HTTPError as e:
            print(f"  ERROR: {e}")
            continue

        suffix = f"_{section_id}" if section_id else ""
        json_path = f"{text_id}{suffix}_loda.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  JSON -> {json_path}")

        out_path = f"{text_id}{suffix}_loda.csv"
        n = to_csv(data, out_path, section_id=effective_section)
        if n == 0:
            print(f"  0 rows — no digitized content found")
            print(f"  sections: {len(data.get('sections', []))}, articles: {len(data.get('articles', []))}")
        else:
            print(f"  {n} rows -> {out_path}")


if __name__ == "__main__":
    main()
