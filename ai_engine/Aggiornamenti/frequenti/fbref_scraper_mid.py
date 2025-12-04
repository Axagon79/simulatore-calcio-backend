import os
import sys
import os
import sys

# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db


"""
SCRAPER CENTROCAMPISTI FBREF - TUTTE LE LEGHE SCELTE
Stagione: 2025-2026

Campionati inclusi (tutti tranne Serie C):
- Serie A        (comp 11)  -> ITA1
- Serie B        (comp 18)  -> ITA2
- Premier League (comp 9)   -> ENG1
- La Liga        (comp 12)  -> ESP1
- Bundesliga     (comp 20)  -> GER1
- Ligue 1        (comp 13)  -> FRA1
- Eredivisie     (comp 23)  -> NED1
- Liga Portugal  (comp 32)  -> POR1

Collection Mongo: players_stats_fbref_mid

Metriche estratte (6):
1. G-PK/90 (gol non su rigore per 90)   - peso 13%
2. Ast/90 (assist per 90)              - peso 18%
3. Cmp% (percentuale passaggi)         - peso 29%
4. TklW/90 (tackle vinti per 90)       - peso 12%
5. Rec/90 (recuperi palla per 90)      - peso 18%
6. Aerials Won% (duelli aerei vinti %) - peso 10%
"""

import re
import time
from typing import Dict, Any

import cloudscraper
from bs4 import BeautifulSoup, Comment
from pymongo import UpdateOne


# ================== CONFIGURAZIONE ==================

SEASON = "2025-2026"

# CONFIGURAZIONE MONGO CLUSTER (UGUALE AL RESTO DEL PROGETTO)
MONGO_COLLECTION_NAME = "players_stats_fbref_mid"

LEAGUES = [
    {
        "name": "Serie A",
        "code": "ITA1",
        "comp_id": 11,
        "standard_url": "https://fbref.com/en/comps/11/stats/Serie-A-Stats",
        "passing_url": "https://fbref.com/en/comps/11/passing/Serie-A-Stats",
        "defense_url": "https://fbref.com/en/comps/11/defense/Serie-A-Stats",
        "misc_url": "https://fbref.com/en/comps/11/misc/Serie-A-Stats",
    },
    {
        "name": "Serie B",
        "code": "ITA2",
        "comp_id": 18,
        "standard_url": "https://fbref.com/en/comps/18/stats/Serie-B-Stats",
        "passing_url": "https://fbref.com/en/comps/18/passing/Serie-B-Stats",
        "defense_url": "https://fbref.com/en/comps/18/defense/Serie-B-Stats",
        "misc_url": "https://fbref.com/en/comps/18/misc/Serie-B-Stats",
    },
    {
        "name": "Premier League",
        "code": "ENG1",
        "comp_id": 9,
        "standard_url": "https://fbref.com/en/comps/9/stats/Premier-League-Stats",
        "passing_url": "https://fbref.com/en/comps/9/passing/Premier-League-Stats",
        "defense_url": "https://fbref.com/en/comps/9/defense/Premier-League-Stats",
        "misc_url": "https://fbref.com/en/comps/9/misc/Premier-League-Stats",
    },
    {
        "name": "La Liga",
        "code": "ESP1",
        "comp_id": 12,
        "standard_url": "https://fbref.com/en/comps/12/stats/La-Liga-Stats",
        "passing_url": "https://fbref.com/en/comps/12/passing/La-Liga-Stats",
        "defense_url": "https://fbref.com/en/comps/12/defense/La-Liga-Stats",
        "misc_url": "https://fbref.com/en/comps/12/misc/La-Liga-Stats",
    },
    {
        "name": "Bundesliga",
        "code": "GER1",
        "comp_id": 20,
        "standard_url": "https://fbref.com/en/comps/20/stats/Bundesliga-Stats",
        "passing_url": "https://fbref.com/en/comps/20/passing/Bundesliga-Stats",
        "defense_url": "https://fbref.com/en/comps/20/defense/Bundesliga-Stats",
        "misc_url": "https://fbref.com/en/comps/20/misc/Bundesliga-Stats",
    },
    {
        "name": "Ligue 1",
        "code": "FRA1",
        "comp_id": 13,
        "standard_url": "https://fbref.com/en/comps/13/stats/Ligue-1-Stats",
        "passing_url": "https://fbref.com/en/comps/13/passing/Ligue-1-Stats",
        "defense_url": "https://fbref.com/en/comps/13/defense/Ligue-1-Stats",
        "misc_url": "https://fbref.com/en/comps/13/misc/Ligue-1-Stats",
    },
    {
        "name": "Eredivisie",
        "code": "NED1",
        "comp_id": 23,
        "standard_url": "https://fbref.com/en/comps/23/stats/Eredivisie-Stats",
        "passing_url": "https://fbref.com/en/comps/23/passing/Eredivisie-Stats",
        "defense_url": "https://fbref.com/en/comps/23/defense/Eredivisie-Stats",
        "misc_url": "https://fbref.com/en/comps/23/misc/Eredivisie-Stats",
    },
    {
        "name": "Liga Portugal",
        "code": "POR1",
        "comp_id": 32,
        "standard_url": "https://fbref.com/en/comps/32/stats/Primeira-Liga-Stats",
        "passing_url": "https://fbref.com/en/comps/32/passing/Primeira-Liga-Stats",
        "defense_url": "https://fbref.com/en/comps/32/defense/Primeira-Liga-Stats",
        "misc_url": "https://fbref.com/en/comps/32/misc/Primeira-Liga-Stats",
    },
]


# ================== UTILS FBREF ==================

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


def parse_float_safe(val: str | None):
    if val is None:
        return None
    txt = val.strip().replace(",", "").replace("+", "").replace("%", "")
    if txt == "" or txt == "-":
        return None
    try:
        return float(txt)
    except Exception:
        return None


def classify_role(pos_raw: str) -> str:
    """
    Classifica il ruolo del giocatore.
    Rimuove spazi: 'MF, DF' -> 'MF,DF'.
    """
    if pos_raw is None:
        return "UNKNOWN"

    pos = pos_raw.replace(" ", "").strip()

    if "GK" in pos:
        return "GK"

    mapping = {
        "FW": "ATT",
        "FW,MF": "ATT",
        "MF,FW": "ATT",
        "FW,DF": "ATT",
        "DF,FW": "DIF",
        "MF": "MID",
        "MF,DF": "MID",
        "DF,MF": "DIF",
        "DF": "DIF",
    }

    return mapping.get(pos, "UNKNOWN")


def normalize_0_1(value: float | None, min_val: float, max_val: float) -> float:
    if value is None:
        return 0.5
    if max_val == min_val:
        return 0.5
    x = (value - min_val) / (max_val - min_val)
    if x < 0:
        x = 0.0
    if x > 1:
        x = 1.0
    return x


def compute_mid_rating(
    g_pk_per90: float | None,
    ast_per90: float | None,
    cmp_pct: float | None,
    tklw_per90: float | None,
    rec_per90: float | None,
    aerials_won_pct: float | None,
) -> float:
    """
    Calcola rating MID puro scala 4-10.
    Pesi: G-PK/90 13%, Ast/90 18%, Cmp% 29%, TklW/90 12%, Rec/90 18%, Aerials% 10%
    """
    g_norm = normalize_0_1(g_pk_per90,       min_val=0.0,  max_val=0.50)
    a_norm = normalize_0_1(ast_per90,       min_val=0.0,  max_val=0.30)
    p_norm = normalize_0_1(cmp_pct,         min_val=70.0, max_val=95.0)
    t_norm = normalize_0_1(tklw_per90,      min_val=0.0,  max_val=2.50)
    r_norm = normalize_0_1(rec_per90,       min_val=0.0,  max_val=5.00)
    d_norm = normalize_0_1(aerials_won_pct, min_val=30.0, max_val=70.0)

    q = (
        0.13 * g_norm +
        0.18 * a_norm +
        0.29 * p_norm +
        0.12 * t_norm +
        0.18 * r_norm +
        0.10 * d_norm
    )

    rating_puro = 4.0 + 6.0 * q
    return rating_puro


# ================== SCRAPING 4 TABELLE ==================

def scrape_standard_mids(scraper, url: str) -> Dict[tuple, Dict[str, Any]]:
    """Estrae centrocampisti dalla tabella STANDARD."""
    resp = scraper.get(url, timeout=40)
    if resp.status_code != 200:
        return {}

    table = extract_table_from_comments_or_dom(resp.text, r"stats_standard")
    if not table:
        return {}

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")

    mids: Dict[tuple, Dict[str, Any]] = {}

    for r in rows:
        if "class" in r.attrs and ("thead" in " ".join(r["class"]) or "spacer" in " ".join(r["class"])):
            continue

        player_cell = r.find(["th", "td"], {"data-stat": "player"})
        team_cell   = r.find("td", {"data-stat": "team"}) or r.find("td", {"data-stat": "squad"})
        pos_cell    = r.find("td", {"data-stat": "position"})

        if not player_cell or not team_cell or not pos_cell:
            continue

        player_name = player_cell.get_text(strip=True)
        team_name   = team_cell.get_text(strip=True)
        pos_raw     = pos_cell.get_text(strip=True)

        role = classify_role(pos_raw)
        if role != "MID":
            continue

        cell_min = r.find("td", {"data-stat": "minutes_90s"})
        minutes_90s = parse_float_safe(cell_min.get_text(strip=True)) if cell_min else None

        cell_goals     = r.find("td", {"data-stat": "goals"})
        cell_pens_made = r.find("td", {"data-stat": "pens_made"})
        cell_assists   = r.find("td", {"data-stat": "assists"})

        goals     = parse_float_safe(cell_goals.get_text(strip=True)) if cell_goals else None
        pens_made = parse_float_safe(cell_pens_made.get_text(strip=True)) if cell_pens_made else None
        assists   = parse_float_safe(cell_assists.get_text(strip=True)) if cell_assists else None

        if not minutes_90s or minutes_90s == 0:
            g_pk_per90 = None
            ast_per90  = None
        else:
            goals     = goals or 0.0
            pens_made = pens_made or 0.0
            assists   = assists or 0.0

            g_pk_total = goals - pens_made
            if g_pk_total < 0:
                g_pk_total = 0.0

            g_pk_per90 = g_pk_total / minutes_90s
            ast_per90  = assists / minutes_90s

        key = (player_name, team_name)
        mids[key] = {
            "player_name": player_name,
            "team_name": team_name,
            "pos_raw": pos_raw,
            "role": role,
            "minutes_90s": minutes_90s,
            "g_pk_per90": g_pk_per90,
            "ast_per90": ast_per90,
        }

    return mids


def scrape_passing(scraper, url: str, mids: Dict[tuple, Dict[str, Any]]) -> None:
    """Aggiunge Cmp% (passes_pct)."""
    resp = scraper.get(url, timeout=40)
    if resp.status_code != 200:
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_passing")
    if not table:
        return

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")

    for r in rows:
        if "class" in r.attrs and ("thead" in " ".join(r["class"]) or "spacer" in " ".join(r["class"])):
            continue

        player_cell = r.find(["th", "td"], {"data-stat": "player"})
        team_cell   = r.find("td", {"data-stat": "team"}) or r.find("td", {"data-stat": "squad"})
        if not player_cell or not team_cell:
            continue

        player_name = player_cell.get_text(strip=True)
        team_name   = team_cell.get_text(strip=True)
        key = (player_name, team_name)
        if key not in mids:
            continue

        cell_cmp = r.find("td", {"data-stat": "passes_pct"})
        cmp_pct = parse_float_safe(cell_cmp.get_text(strip=True)) if cell_cmp else None
        mids[key]["cmp_pct"] = cmp_pct


def scrape_defense(scraper, url: str, mids: Dict[tuple, Dict[str, Any]]) -> None:
    """Aggiunge TklW/90."""
    resp = scraper.get(url, timeout=40)
    if resp.status_code != 200:
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_defense")
    if not table:
        return

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")

    for r in rows:
        if "class" in r.attrs and ("thead" in " ".join(r["class"]) or "spacer" in " ".join(r["class"])):
            continue

        player_cell = r.find(["th", "td"], {"data-stat": "player"})
        team_cell   = r.find("td", {"data-stat": "team"}) or r.find("td", {"data-stat": "squad"})
        if not player_cell or not team_cell:
            continue

        player_name = player_cell.get_text(strip=True)
        team_name   = team_cell.get_text(strip=True)
        key = (player_name, team_name)
        if key not in mids:
            continue

        minutes_90s = mids[key].get("minutes_90s")

        cell_tkl = r.find("td", {"data-stat": "tackles_won"})
        tackles_won = parse_float_safe(cell_tkl.get_text(strip=True)) if cell_tkl else None

        if not minutes_90s or minutes_90s == 0 or tackles_won is None:
            tklw_per90 = None
        else:
            tklw_per90 = tackles_won / minutes_90s

        mids[key]["tklw_per90"] = tklw_per90


def scrape_misc(scraper, url: str, mids: Dict[tuple, Dict[str, Any]]) -> None:
    """Aggiunge Rec/90 e Aerials Won%."""
    resp = scraper.get(url, timeout=40)
    if resp.status_code != 200:
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_misc")
    if not table:
        return

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")

    for r in rows:
        if "class" in r.attrs and ("thead" in " ".join(r["class"]) or "spacer" in " ".join(r["class"])):
            continue

        player_cell = r.find(["th", "td"], {"data-stat": "player"})
        team_cell   = r.find("td", {"data-stat": "team"}) or r.find("td", {"data-stat": "squad"})
        if not player_cell or not team_cell:
            continue

        player_name = player_cell.get_text(strip=True)
        team_name   = team_cell.get_text(strip=True)
        key = (player_name, team_name)
        if key not in mids:
            continue

        minutes_90s = mids[key].get("minutes_90s")

        cell_rec = r.find("td", {"data-stat": "ball_recoveries"})
        recov = parse_float_safe(cell_rec.get_text(strip=True)) if cell_rec else None

        cell_aer = r.find("td", {"data-stat": "aerials_won_pct"})
        aerials_pct = parse_float_safe(cell_aer.get_text(strip=True)) if cell_aer else None

        if not minutes_90s or minutes_90s == 0 or recov is None:
            rec_per90 = None
        else:
            rec_per90 = recov / minutes_90s

        mids[key]["rec_per90"] = rec_per90
        mids[key]["aerials_won_pct"] = aerials_pct


# ================== MAIN SCRAPER ==================

def main():
    collection = db[MONGO_COLLECTION_NAME]
    scraper = create_scraper()

    for lg in LEAGUES:
        print("\n" + "=" * 40)
        print(f"🏆 LEGA: {lg['name']} ({lg['code']})")
        print("=" * 40)

        # --- STANDARD ---
        print(f"➡️  Scarico STANDARD: {lg['standard_url']}")
        mids = scrape_standard_mids(scraper, lg["standard_url"])
        print(f"   ➜ Centrocampisti trovati in STANDARD: {len(mids)}")
        if not mids:
            print("   ⚠️ Nessun centrocampista, salto lega.")
            continue

        time.sleep(10)

        # --- PASSING ---
        print(f"➡️  Scarico PASSING: {lg['passing_url']}")
        scrape_passing(scraper, lg["passing_url"], mids)
        print(f"   ➜ Dati PASSING aggiunti")

        time.sleep(10)

        # --- DEFENSE ---
        print(f"➡️  Scarico DEFENSE: {lg['defense_url']}")
        scrape_defense(scraper, lg["defense_url"], mids)
        print(f"   ➜ Dati DEFENSE aggiunti")

        time.sleep(10)

        # --- MISC ---
        print(f"➡️  Scarico MISC: {lg['misc_url']}")
        scrape_misc(scraper, lg["misc_url"], mids)
        print(f"   ➜ Dati MISC aggiunti")

        # --- Merge + calcolo rating + upsert Mongo ---
        bulk_ops = []

        for (player_name, team_name), data in mids.items():
            g_pk_per90      = data.get("g_pk_per90")
            ast_per90       = data.get("ast_per90")
            cmp_pct         = data.get("cmp_pct")
            tklw_per90      = data.get("tklw_per90")
            rec_per90       = data.get("rec_per90")
            aerials_won_pct = data.get("aerials_won_pct")

            rating_puro = compute_mid_rating(
                g_pk_per90,
                ast_per90,
                cmp_pct,
                tklw_per90,
                rec_per90,
                aerials_won_pct,
            )

            doc_filter = {
                "season": SEASON,
                "league_code": lg["code"],
                "team_name_fbref": team_name,
                "player_name_fbref": player_name,
            }

            mid_stats = {
                "g_pk_per90": g_pk_per90,
                "ast_per90": ast_per90,
                "cmp_pct": cmp_pct,
                "tklw_per90": tklw_per90,
                "rec_per90": rec_per90,
                "aerials_won_pct": aerials_won_pct,
            }

            doc_update = {
                "$set": {
                    "season": SEASON,
                    "league_code": lg["code"],
                    "league_name": lg["name"],
                    "team_name_fbref": team_name,
                    "player_name_fbref": player_name,
                    "pos_raw": data.get("pos_raw"),
                    "role": data.get("role"),
                    "minutes_90s": data.get("minutes_90s"),
                    "mid_stats": mid_stats,
                    "mid_rating": {
                        "rating_puro": rating_puro,
                    },
                    "source": "fbref",
                }
            }

            bulk_ops.append(UpdateOne(doc_filter, doc_update, upsert=True))

        if bulk_ops:
            print(f"   💾 Scrivo {len(bulk_ops)} documenti in Mongo...")
            result = collection.bulk_write(bulk_ops, ordered=False)
            print(
                f"   ➜ upserted: {result.upserted_count}, "
                f"modified: {result.modified_count}"
            )
        else:
            print("   ⚠️ Nessun centrocampista da scrivere per questa lega.")

        # Pausa tra leghe
        time.sleep(10)

    print("\n✅ SCRAPER CENTROCAMPISTI FBREF COMPLETATO.")


if __name__ == "__main__":
    main()