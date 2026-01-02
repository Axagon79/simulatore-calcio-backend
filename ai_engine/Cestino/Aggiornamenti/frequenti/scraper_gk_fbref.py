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
SCRAPER PORTIERI FBREF - TUTTE LE LEGHE SCELTE
Stagione: 2025-2026
VERSIONE AGGIORNATA: con minutes_90s
"""

import re
import time
from typing import Dict, Any

import cloudscraper
from bs4 import BeautifulSoup, Comment
from pymongo import UpdateOne


# ================== CONFIGURAZIONE ==================

SEASON = "2025-2026"

MONGO_COLLECTION_NAME = "players_stats_fbref_gk"

LEAGUES = [
    {
        "name": "Serie A",
        "code": "ITA1",
        "comp_id": 11,
        "keepers_url": "https://fbref.com/en/comps/11/keepers/Serie-A-Stats",
        "keepersadv_url": "https://fbref.com/en/comps/11/keepersadv/Serie-A-Stats",
    },
    {
        "name": "Serie B",
        "code": "ITA2",
        "comp_id": 18,
        "keepers_url": "https://fbref.com/en/comps/18/keepers/Serie-B-Stats",
        "keepersadv_url": "https://fbref.com/en/comps/18/keepersadv/Serie-B-Stats",
    },
    {
        "name": "Premier League",
        "code": "ENG1",
        "comp_id": 9,
        "keepers_url": "https://fbref.com/en/comps/9/keepers/Premier-League-Stats",
        "keepersadv_url": "https://fbref.com/en/comps/9/keepersadv/Premier-League-Stats",
    },
    {
        "name": "La Liga",
        "code": "ESP1",
        "comp_id": 12,
        "keepers_url": "https://fbref.com/en/comps/12/keepers/La-Liga-Stats",
        "keepersadv_url": "https://fbref.com/en/comps/12/keepersadv/La-Liga-Stats",
    },
    {
        "name": "Bundesliga",
        "code": "GER1",
        "comp_id": 20,
        "keepers_url": "https://fbref.com/en/comps/20/keepers/Bundesliga-Stats",
        "keepersadv_url": "https://fbref.com/en/comps/20/keepersadv/Bundesliga-Stats",
    },
    {
        "name": "Ligue 1",
        "code": "FRA1",
        "comp_id": 13,
        "keepers_url": "https://fbref.com/en/comps/13/keepers/Ligue-1-Stats",
        "keepersadv_url": "https://fbref.com/en/comps/13/keepersadv/Ligue-1-Stats",
    },
    {
        "name": "Eredivisie",
        "code": "NED1",
        "comp_id": 23,
        "keepers_url": "https://fbref.com/en/comps/23/keepers/Eredivisie-Stats",
        "keepersadv_url": "https://fbref.com/en/comps/23/keepersadv/Eredivisie-Stats",
    },
    {
        "name": "Liga Portugal",
        "code": "POR1",
        "comp_id": 32,
        "keepers_url": "https://fbref.com/en/comps/32/keepers/Primeira-Liga-Stats",
        "keepersadv_url": "https://fbref.com/en/comps/32/keepersadv/Primeira-Liga-Stats",
    },
]


# ================== UTILS FBREF ==================

def create_scraper():
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "desktop": True,
        }
    )
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
    txt = val.strip().replace(",", "").replace("+", "")
    if txt == "":
        return None
    try:
        return float(txt)
    except Exception:
        return None


def compute_gk_rating(
    save_pct_all: float | None,
    save_pct_pk: float | None,
    psxg_ga_per90: float | None,
    cross_stop_pct: float | None,
) -> float:
    """
    Rating puro GK su scala ~4-10.
    """
    def norm_pct(x):
        if x is None:
            return 0.5
        return max(0.0, min(1.0, x / 100.0))

    s = norm_pct(save_pct_all)
    r = norm_pct(save_pct_pk)
    c = norm_pct(cross_stop_pct)

    if psxg_ga_per90 is None:
        p = 0.5
    else:
        p = (psxg_ga_per90 + 0.3) / 0.6
        p = max(0.0, min(1.0, p))

    q = 0.35 * s + 0.35 * p + 0.20 * c + 0.10 * r

    rating_puro = 4.0 + 6.0 * q
    return rating_puro


def scrape_keepers_table(table) -> Dict[tuple, Dict[str, Any]]:
    """
    Restituisce un dict:
      key = (player_name, team_name)
      value = dict con tutte le colonne della tabella keepers
    """
    result: Dict[tuple, Dict[str, Any]] = {}

    if not table:
        return result

    tbody = table.find("tbody")
    if not tbody:
        return result

    rows = tbody.find_all("tr")

    for r in rows:
        if "class" in r.attrs and ("thead" in " ".join(r["class"]) or "spacer" in " ".join(r["class"])):
            continue

        player_cell = r.find("td", {"data-stat": "player"})
        team_cell = r.find("td", {"data-stat": "team"})
        if not player_cell or not team_cell:
            continue

        player_name = player_cell.get_text(strip=True)
        team_name = team_cell.get_text(strip=True)

        data = {}
        for cell in r.find_all(["th", "td"]):
            stat = cell.get("data-stat")
            if not stat:
                continue
            data[stat] = cell.get_text(strip=True)

        key = (player_name, team_name)
        result[key] = data

    return result


def scrape_keepersadv_table(table) -> Dict[tuple, Dict[str, Any]]:
    """
    Restituisce un dict:
      key = (player_name, team_name)
      value = dict con tutte le colonne della tabella keepersadv
    """
    result: Dict[tuple, Dict[str, Any]] = {}

    if not table:
        return result

    tbody = table.find("tbody")
    if not tbody:
        return result

    rows = tbody.find_all("tr")

    for r in rows:
        if "class" in r.attrs and ("thead" in " ".join(r["class"]) or "spacer" in " ".join(r["class"])):
            continue

        player_cell = r.find("td", {"data-stat": "player"})
        team_cell = r.find("td", {"data-stat": "team"})
        if not player_cell or not team_cell:
            continue

        player_name = player_cell.get_text(strip=True)
        team_name = team_cell.get_text(strip=True)

        data = {}
        for cell in r.find_all(["th", "td"]):
            stat = cell.get("data-stat")
            if not stat:
                continue
            data[stat] = cell.get_text(strip=True)

        key = (player_name, team_name)
        result[key] = data

    return result


# ================== MAIN SCRAPER ==================

def main():
    collection = db[MONGO_COLLECTION_NAME]
    scraper = create_scraper()

    for lg in LEAGUES:
        print("\n" + "=" * 40)
        print(f"🏆 LEGA: {lg['name']} ({lg['code']})")
        print("=" * 40)

        # --- KEEPERS ---
        print(f"➡️  Scarico KEEPERS: {lg['keepers_url']}")
        resp_k = scraper.get(lg["keepers_url"], timeout=40)
        print(f"   Status keepers: {resp_k.status_code}")
        if resp_k.status_code != 200:
            print("   ⚠️ Keepers non 200, salto lega.")
            continue

        table_k = extract_table_from_comments_or_dom(resp_k.text, r"stats_keeper")
        if not table_k:
            print("   ❌ Tabella stats_keeper non trovata, salto lega.")
            continue

        keepers_data = scrape_keepers_table(table_k)
        print(f"   ➜ Portieri trovati in KEEPERS: {len(keepers_data)}")

        # --- KEEPERSADV ---
        print(f"➡️  Scarico KEEPERSADV: {lg['keepersadv_url']}")
        resp_ka = scraper.get(lg["keepersadv_url"], timeout=40)
        print(f"   Status keepersadv: {resp_ka.status_code}")
        if resp_ka.status_code == 200:
            table_ka = extract_table_from_comments_or_dom(resp_ka.text, r"stats_keeper_adv")
            if not table_ka:
                print("   ⚠️ Tabella stats_keeper_adv non trovata, niente metriche avanzate.")
                keepersadv_data = {}
            else:
                keepersadv_data = scrape_keepersadv_table(table_ka)
                print(f"   ➜ Portieri trovati in KEEPERSADV: {len(keepersadv_data)}")
        else:
            print("   ⚠️ Keepersadv non 200, niente metriche avanzate.")
            keepersadv_data = {}

        # --- Merge + calcolo rating + upsert Mongo ---
        bulk_ops = []

        for (player_name, team_name), base_row in keepers_data.items():
            adv_row = keepersadv_data.get((player_name, team_name), {})

            save_pct_all = parse_float_safe(base_row.get("gk_save_pct"))
            save_pct_pk = parse_float_safe(base_row.get("gk_pens_save_pct"))
            psxg_ga_per90 = parse_float_safe(adv_row.get("gk_psxg_net_per90"))
            cross_stop_pct = parse_float_safe(adv_row.get("gk_crosses_stopped_pct"))
            
            # ⭐ NUOVO: Estrai minutes_90s
            minutes_90s = parse_float_safe(base_row.get("minutes_90s"))

            rating_puro = compute_gk_rating(
                save_pct_all,
                save_pct_pk,
                psxg_ga_per90,
                cross_stop_pct,
            )

            doc_filter = {
                "season": SEASON,
                "league_code": lg["code"],
                "team_name_fbref": team_name,
                "player_name_fbref": player_name,
            }

            gk_stats = {
                "gk_save_pct": save_pct_all,
                "gk_pens_save_pct": save_pct_pk,
                "gk_psxg_net_per90": psxg_ga_per90,
                "gk_crosses_stopped_pct": cross_stop_pct,
            }

            doc_update = {
                "$set": {
                    "season": SEASON,
                    "league_code": lg["code"],
                    "league_name": lg["name"],
                    "team_name_fbref": team_name,
                    "player_name_fbref": player_name,
                    "minutes_90s": minutes_90s,  # ⭐ NUOVO CAMPO
                    "gk_stats": gk_stats,
                    "gk_rating": {
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
            print("   ⚠️ Nessun portiere da scrivere per questa lega.")

        # Pausa
        time.sleep(10)

    print("\n✅ SCRAPER GK FBREF COMPLETATO.")


if __name__ == "__main__":
    main()