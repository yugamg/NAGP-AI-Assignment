from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from app.config import ROOT_DIR

RAW_OUT_DIR = ROOT_DIR / "data" / "knowledge_base_raw"

SOURCES = [
    {
        "title": "Singapore Travel Guide - Wikivoyage",
        "url": "https://en.wikivoyage.org/wiki/Singapore",
        "filename": "wikivoyage_singapore.md",
        "main_selector": "#mw-content-text",
    },
    {
        "title": "Essential Singapore Travel Information - Visit Singapore",
        "url": "https://www.visitsingapore.com/travel-tips/essential-travel-information/",
        "filename": "visitsingapore_essential_info.md",
        "main_selector": "main",
    },
    {
        "title": "Enjoy Singapore in 7 Days - Visit Singapore Sample Itinerary",
        "url": "https://www.visitsingapore.com/travel-tips/travelling-to-singapore/itineraries/7-days-in-singapore/",
        "filename": "visitsingapore_sample_itinerary.md",
        "main_selector": "main",
    },
    {
        "title": "Top Things To Do - Visit Singapore",
        "url": "https://www.visitsingapore.com/things-to-do/top-things-to-do/",
        "filename": "visitsingapore_things_to_do.md",
        "main_selector": "main",
    },
    {
        "title": "Local Food & Drinks - Visit Singapore",
        "url": "https://www.visitsingapore.com/things-to-do/dining/local-food-and-drinks/",
        "filename": "visitsingapore_food_drinks.md",
        "main_selector": "main",
    },
]


def extract_text(html: str, selector: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    node = soup.select_one(selector) or soup
    lines = [line.strip() for line in node.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line)


def fetch_all() -> None:
    RAW_OUT_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=20.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for source in SOURCES:
            try:
                resp = client.get(source["url"])
                resp.raise_for_status()
                body = extract_text(resp.text, source["main_selector"])
            except httpx.HTTPError as exc:
                print(f"SKIP {source['url']}: {exc}")
                continue

            out_path = RAW_OUT_DIR / source["filename"]
            out_path.write_text(
                f"---\ntitle: \"{source['title']}\"\nsource_url: \"{source['url']}\"\n---\n\n{body}\n",
                encoding="utf-8",
            )
            print(f"Fetched {source['url']} -> {out_path}")

    print(f"\nRaw fetch complete. Compare against the curated files in data/knowledge_base/ "
          f"before using these for ingestion — site navigation/JS-rendered tabs may need manual cleanup.")


if __name__ == "__main__":
    fetch_all()
