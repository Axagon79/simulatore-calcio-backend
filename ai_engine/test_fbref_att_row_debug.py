"""
DEBUG FBREF - Serie B (STANDARD, SHOOTING, POSSESSION, PASSING, MISC)

Stampa una riga campione da ciascuna tabella per vedere i data-stat esatti
delle 8 metriche attaccanti.
"""

import re
import cloudscraper
from bs4 import BeautifulSoup, Comment

URLS = [
    ("STANDARD", "https://fbref.com/en/comps/18/stats/Serie-B-Stats", r"stats_standard"),
    ("SHOOTING", "https://fbref.com/en/comps/18/shooting/Serie-B-Stats", r"stats_shooting"),
    ("POSSESSION", "https://fbref.com/en/comps/18/possession/Serie-B-Stats", r"stats_possession"),
    ("PASSING", "https://fbref.com/en/comps/18/passing/Serie-B-Stats", r"stats_passing"),
    ("MISC", "https://fbref.com/en/comps/18/misc/Serie-B-Stats", r"stats_misc"),
]


def create_scraper():
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "desktop": True,
        },
        delay=10,
    )
    scraper.headers.update({
        "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.com/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return scraper


def extract_table_from_comments_or_dom(html: str, id_regex: str):
    soup = BeautifulSoup(html, "html.parser")
    table = None

    # 1) Cerca nei commenti
    comments = soup.find_all(string=lambda t: isinstance(t, Comment))
    for c in comments:
        if "<table" not in c:
            continue
        if re.search(id_regex, c):
            inner = BeautifulSoup(c, "html.parser")
            cand = inner.find("table", id=re.compile(id_regex))
            if cand:
                table = cand
                break

    # 2) Fallback: DOM normale
    if not table:
        table = soup.find("table", id=re.compile(id_regex))

    return table


def debug_one_table(scraper, label: str, url: str, id_regex: str):
    print("\n" + "=" * 60)
    print(f"🔍 DEBUG TABELLA {label} - {url}")
    print("=" * 60)

    resp = scraper.get(url, timeout=40)
    print(f"Status {label}: {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ {label} non 200, salto.")
        return

    table = extract_table_from_comments_or_dom(resp.text, id_regex)
    if not table:
        print(f"❌ Tabella con id che matcha '{id_regex}' non trovata.")
        return

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    print(f"Righe {label} trovate: {len(rows)}")

    target_row = None
    for r in rows:
        classes = " ".join(r.get("class", []))
        if "thead" in classes or "spacer" in classes:
            continue

        player_cell = r.find(["th", "td"], {"data-stat": "player"})
        if not player_cell:
            continue
        player_name = player_cell.get_text(strip=True)
        if not player_name:
            continue

        target_row = r
        break

    if target_row is None:
        print(f"❌ Nessuna riga giocatore trovata in {label}.")
        return

    player_name = target_row.find(["th", "td"], {"data-stat": "player"}).get_text(strip=True)
    print(f"\nGiocatore nella riga campione ({label}): {player_name}\n")

    all_cells = target_row.find_all(["th", "td"])
    print("Indice | data-stat                | valore")
    print("---------------------------------------------")
    for idx, cell in enumerate(all_cells):
        stat = cell.get("data-stat")
        text = cell.get_text(strip=True)
        print(f"{idx:2d})   {stat:<24}  | '{text}'")


def main():
    scraper = create_scraper()
    for label, url, id_regex in URLS:
        debug_one_table(scraper, label, url, id_regex)


if __name__ == "__main__":
    main()
