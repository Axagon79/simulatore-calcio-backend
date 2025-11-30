import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

"""
SCRAPER DIFENSORI FBREF - TUTTE LE LEGHE SCELTE
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

Collection Mongo: players_stats_fbref_def

Metriche estratte (6):
1. Contrasti (Def 3rd)/90   - peso 25%
2. Tkl+Int/90               - peso 29%
3. TklW/90                  - peso 15%
4. Aerials Won/90           - peso 16%
5. onGA/90 (gol subiti)     - peso 10% (MENO è MEGLIO)
6. Clr/90                   - peso 5%
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
MONGO_COLLECTION_NAME = "players_stats_fbref_def"

LEAGUES = [
    {
        "name": "Serie A",
        "code": "ITA1",
        "comp_id": 11,
        "defense_url": "https://fbref.com/en/comps/11/defense/Serie-A-Stats",
        "misc_url": "https://fbref.com/en/comps/11/misc/Serie-A-Stats",
        "playingtime_url": "https://fbref.com/en/comps/11/playingtime/Serie-A-Stats",
    },
    {
        "name": "Serie B",
        "code": "ITA2",
        "comp_id": 18,
        "defense_url": "https://fbref.com/en/comps/18/defense/Serie-B-Stats",
        "misc_url": "https://fbref.com/en/comps/18/misc/Serie-B-Stats",
        "playingtime_url": "https://fbref.com/en/comps/18/playingtime/Serie-B-Stats",
    },
    {
        "name": "Premier League",
        "code": "ENG1",
        "comp_id": 9,
        "defense_url": "https://fbref.com/en/comps/9/defense/Premier-League-Stats",
        "misc_url": "https://fbref.com/en/comps/9/misc/Premier-League-Stats",
        "playingtime_url": "https://fbref.com/en/comps/9/playingtime/Premier-League-Stats",
    },
    {
        "name": "La Liga",
        "code": "ESP1",
        "comp_id": 12,
        "defense_url": "https://fbref.com/en/comps/12/defense/La-Liga-Stats",
        "misc_url": "https://fbref.com/en/comps/12/misc/La-Liga-Stats",
        "playingtime_url": "https://fbref.com/en/comps/12/playingtime/La-Liga-Stats",
    },
    {
        "name": "Bundesliga",
        "code": "GER1",
        "comp_id": 20,
        "defense_url": "https://fbref.com/en/comps/20/defense/Bundesliga-Stats",
        "misc_url": "https://fbref.com/en/comps/20/misc/Bundesliga-Stats",
        "playingtime_url": "https://fbref.com/en/comps/20/playingtime/Bundesliga-Stats",
    },
    {
        "name": "Ligue 1",
        "code": "FRA1",
        "comp_id": 13,
        "defense_url": "https://fbref.com/en/comps/13/defense/Ligue-1-Stats",
        "misc_url": "https://fbref.com/en/comps/13/misc/Ligue-1-Stats",
        "playingtime_url": "https://fbref.com/en/comps/13/playingtime/Ligue-1-Stats",
    },
    {
        "name": "Eredivisie",
        "code": "NED1",
        "comp_id": 23,
        "defense_url": "https://fbref.com/en/comps/23/defense/Eredivisie-Stats",
        "misc_url": "https://fbref.com/en/comps/23/misc/Eredivisie-Stats",
        "playingtime_url": "https://fbref.com/en/comps/23/playingtime/Eredivisie-Stats",
    },
    {
        "name": "Liga Portugal",
        "code": "POR1",
        "comp_id": 32,
        "defense_url": "https://fbref.com/en/comps/32/defense/Primeira-Liga-Stats",
        "misc_url": "https://fbref.com/en/comps/32/misc/Primeira-Liga-Stats",
        "playingtime_url": "https://fbref.com/en/comps/32/playingtime/Primeira-Liga-Stats",
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


def compute_def_rating(
    tkl_def3rd_per90: float | None,
    tkl_int_per90: float | None,
    tklw_per90: float | None,
    aerials_won_per90: float | None,
    on_ga_per90: float | None,
    clr_per90: float | None,
) -> float:
    """
    Calcola rating DIF puro scala 4-10.
    Pesi: Tkl Def3rd 25%, Tkl+Int 29%, TklW 15%, Aerials 16%, onGA 10% (inv), Clr 5%
    """
    t3_norm  = normalize_0_1(tkl_def3rd_per90,  min_val=0.0, max_val=2.0)
    ti_norm  = normalize_0_1(tkl_int_per90,     min_val=0.0, max_val=5.0)
    tw_norm  = normalize_0_1(tklw_per90,        min_val=0.0, max_val=2.0)
    aw_norm  = normalize_0_1(aerials_won_per90, min_val=0.0, max_val=5.0)
    clr_norm = normalize_0_1(clr_per90,         min_val=0.0, max_val=6.0)

    # onGA: MENO gol subiti = MEGLIO → inverti
    if on_ga_per90 is None:
        ga_norm = 0.5
    else:
        ga_norm = 1.0 - normalize_0_1(on_ga_per90, min_val=0.5, max_val=2.5)

    q = (
        0.25 * t3_norm +
        0.29 * ti_norm +
        0.15 * tw_norm +
        0.16 * aw_norm +
        0.10 * ga_norm +
        0.05 * clr_norm
    )

    rating_puro = 4.0 + 6.0 * q
    return rating_puro


# ================== SCRAPING 3 TABELLE ==================

def scrape_defense_defs(scraper, url: str) -> Dict[tuple, Dict[str, Any]]:
    """Estrae difensori dalla tabella DEFENSE."""
    resp = scraper.get(url, timeout=40)
    if resp.status_code != 200:
        return {}

    table = extract_table_from_comments_or_dom(resp.text, r"stats_defense")
    if not table:
        return {}

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")

    defs: Dict[tuple, Dict[str, Any]] = {}

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
        if role != "DIF":
            continue

        cell_min = r.find("td", {"data-stat": "minutes_90s"})
        minutes_90s = parse_float_safe(cell_min.get_text(strip=True)) if cell_min else None

        cell_tkl_def3rd = r.find("td", {"data-stat": "tackles_def_3rd"})
        cell_tkl_int    = r.find("td", {"data-stat": "tackles_interceptions"})
        cell_clr        = r.find("td", {"data-stat": "clearances"})

        tkl_def3rd = parse_float_safe(cell_tkl_def3rd.get_text(strip=True)) if cell_tkl_def3rd else None
        tkl_int    = parse_float_safe(cell_tkl_int.get_text(strip=True)) if cell_tkl_int else None
        clr        = parse_float_safe(cell_clr.get_text(strip=True)) if cell_clr else None

        if not minutes_90s or minutes_90s == 0:
            tkl_def3rd_per90 = None
            tkl_int_per90    = None
            clr_per90        = None
        else:
            tkl_def3rd_per90 = tkl_def3rd / minutes_90s if tkl_def3rd is not None else None
            tkl_int_per90    = tkl_int / minutes_90s if tkl_int is not None else None
            clr_per90        = clr / minutes_90s if clr is not None else None

        key = (player_name, team_name)
        defs[key] = {
            "player_name": player_name,
            "team_name": team_name,
            "pos_raw": pos_raw,
            "role": role,
            "minutes_90s": minutes_90s,
            "tkl_def3rd_per90": tkl_def3rd_per90,
            "tkl_int_per90": tkl_int_per90,
            "clr_per90": clr_per90,
        }

    return defs


def scrape_misc(scraper, url: str, defs: Dict[tuple, Dict[str, Any]]) -> None:
    """Aggiunge TklW/90 e Aerials Won/90."""
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
        if key not in defs:
            continue

        minutes_90s = defs[key].get("minutes_90s")

        cell_tklw = r.find("td", {"data-stat": "tackles_won"})
        cell_aer  = r.find("td", {"data-stat": "aerials_won"})

        tklw = parse_float_safe(cell_tklw.get_text(strip=True)) if cell_tklw else None
        aer  = parse_float_safe(cell_aer.get_text(strip=True)) if cell_aer else None

        if not minutes_90s or minutes_90s == 0:
            tklw_per90 = None
            aerials_won_per90 = None
        else:
            tklw_per90 = tklw / minutes_90s if tklw is not None else None
            aerials_won_per90 = aer / minutes_90s if aer is not None else None

        defs[key]["tklw_per90"] = tklw_per90
        defs[key]["aerials_won_per90"] = aerials_won_per90


def scrape_playingtime(scraper, url: str, defs: Dict[tuple, Dict[str, Any]]) -> None:
    """Aggiunge onGA/90 (gol subiti mentre in campo)."""
    resp = scraper.get(url, timeout=40)
    if resp.status_code != 200:
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_playing_time")
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
        if key not in defs:
            continue

        minutes_90s = defs[key].get("minutes_90s")

        cell_on_ga = r.find("td", {"data-stat": "on_goals_against"})
        on_ga = parse_float_safe(cell_on_ga.get_text(strip=True)) if cell_on_ga else None

        if not minutes_90s or minutes_90s == 0 or on_ga is None:
            on_ga_per90 = None
        else:
            on_ga_per90 = on_ga / minutes_90s

        defs[key]["on_ga_per90"] = on_ga_per90


# ================== MAIN SCRAPER ==================

def main():
    collection = db[MONGO_COLLECTION_NAME]
    scraper = create_scraper()

    for lg in LEAGUES:
        print("\n" + "=" * 40)
        print(f"🏆 LEGA: {lg['name']} ({lg['code']})")
        print("=" * 40)

        # --- DEFENSE ---
        print(f"➡️  Scarico DEFENSE: {lg['defense_url']}")
        defs = scrape_defense_defs(scraper, lg["defense_url"])
        print(f"   ➜ Difensori trovati in DEFENSE: {len(defs)}")
        if not defs:
            print("   ⚠️ Nessun difensore, salto lega.")
            continue

        time.sleep(10)

        # --- MISC ---
        print(f"➡️  Scarico MISC: {lg['misc_url']}")
        scrape_misc(scraper, lg["misc_url"], defs)
        print(f"   ➜ Dati MISC aggiunti")

        time.sleep(10)

        # --- PLAYINGTIME ---
        print(f"➡️  Scarico PLAYINGTIME: {lg['playingtime_url']}")
        scrape_playingtime(scraper, lg["playingtime_url"], defs)
        print(f"   ➜ Dati PLAYINGTIME aggiunti")

        # --- Merge + calcolo rating + upsert Mongo ---
        bulk_ops = []

        for (player_name, team_name), data in defs.items():
            tkl_def3rd_per90  = data.get("tkl_def3rd_per90")
            tkl_int_per90     = data.get("tkl_int_per90")
            tklw_per90        = data.get("tklw_per90")
            aerials_won_per90 = data.get("aerials_won_per90")
            on_ga_per90       = data.get("on_ga_per90")
            clr_per90         = data.get("clr_per90")

            rating_puro = compute_def_rating(
                tkl_def3rd_per90,
                tkl_int_per90,
                tklw_per90,
                aerials_won_per90,
                on_ga_per90,
                clr_per90,
            )

            doc_filter = {
                "season": SEASON,
                "league_code": lg["code"],
                "team_name_fbref": team_name,
                "player_name_fbref": player_name,
            }

            def_stats = {
                "tkl_def3rd_per90": tkl_def3rd_per90,
                "tkl_int_per90": tkl_int_per90,
                "tklw_per90": tklw_per90,
                "aerials_won_per90": aerials_won_per90,
                "on_ga_per90": on_ga_per90,
                "clr_per90": clr_per90,
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
                    "def_stats": def_stats,
                    "def_rating": {
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
            print("   ⚠️ Nessun difensore da scrivere per questa lega.")

        # Pausa tra leghe
        time.sleep(10)

    print("\n✅ SCRAPER DIFENSORI FBREF COMPLETATO.")


if __name__ == "__main__":
    main()