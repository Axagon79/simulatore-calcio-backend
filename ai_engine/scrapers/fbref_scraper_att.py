import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

"""
SCRAPER ATTACCANTI FBREF - TUTTE LE LEGHE SCELTE
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

Collection Mongo: players_stats_fbref_att

Metriche estratte (8):
1. Gls/90 (gol per 90)          - peso 23%
2. G+A/90 (gol + assist per 90) - peso 22%
3. SoT/90 (tiri in porta per 90)- peso 12%
4. G/Sh (gol per tiro)          - peso 12%
5. Succ/90 (affronti riusciti)  - peso 8%
6. Fld/90 (falli subiti)        - peso 8%
7. KP/90 (passaggi chiave)      - peso 8%
8. npxG+xAG/90                  - peso 7%
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
MONGO_COLLECTION_NAME = "players_stats_fbref_att"

LEAGUES = [
    {
        "name": "Serie A",
        "code": "ITA1",
        "comp_id": 11,
        "standard_url": "https://fbref.com/en/comps/11/stats/Serie-A-Stats",
        "shooting_url": "https://fbref.com/en/comps/11/shooting/Serie-A-Stats",
        "possession_url": "https://fbref.com/en/comps/11/possession/Serie-A-Stats",
        "passing_url": "https://fbref.com/en/comps/11/passing/Serie-A-Stats",
        "misc_url": "https://fbref.com/en/comps/11/misc/Serie-A-Stats",
    },
    {
        "name": "Serie B",
        "code": "ITA2",
        "comp_id": 18,
        "standard_url": "https://fbref.com/en/comps/18/stats/Serie-B-Stats",
        "shooting_url": "https://fbref.com/en/comps/18/shooting/Serie-B-Stats",
        "possession_url": "https://fbref.com/en/comps/18/possession/Serie-B-Stats",
        "passing_url": "https://fbref.com/en/comps/18/passing/Serie-B-Stats",
        "misc_url": "https://fbref.com/en/comps/18/misc/Serie-B-Stats",
    },
    {
        "name": "Premier League",
        "code": "ENG1",
        "comp_id": 9,
        "standard_url": "https://fbref.com/en/comps/9/stats/Premier-League-Stats",
        "shooting_url": "https://fbref.com/en/comps/9/shooting/Premier-League-Stats",
        "possession_url": "https://fbref.com/en/comps/9/possession/Premier-League-Stats",
        "passing_url": "https://fbref.com/en/comps/9/passing/Premier-League-Stats",
        "misc_url": "https://fbref.com/en/comps/9/misc/Premier-League-Stats",
    },
    {
        "name": "La Liga",
        "code": "ESP1",
        "comp_id": 12,
        "standard_url": "https://fbref.com/en/comps/12/stats/La-Liga-Stats",
        "shooting_url": "https://fbref.com/en/comps/12/shooting/La-Liga-Stats",
        "possession_url": "https://fbref.com/en/comps/12/possession/La-Liga-Stats",
        "passing_url": "https://fbref.com/en/comps/12/passing/La-Liga-Stats",
        "misc_url": "https://fbref.com/en/comps/12/misc/La-Liga-Stats",
    },
    {
        "name": "Bundesliga",
        "code": "GER1",
        "comp_id": 20,
        "standard_url": "https://fbref.com/en/comps/20/stats/Bundesliga-Stats",
        "shooting_url": "https://fbref.com/en/comps/20/shooting/Bundesliga-Stats",
        "possession_url": "https://fbref.com/en/comps/20/possession/Bundesliga-Stats",
        "passing_url": "https://fbref.com/en/comps/20/passing/Bundesliga-Stats",
        "misc_url": "https://fbref.com/en/comps/20/misc/Bundesliga-Stats",
    },
    {
        "name": "Ligue 1",
        "code": "FRA1",
        "comp_id": 13,
        "standard_url": "https://fbref.com/en/comps/13/stats/Ligue-1-Stats",
        "shooting_url": "https://fbref.com/en/comps/13/shooting/Ligue-1-Stats",
        "possession_url": "https://fbref.com/en/comps/13/possession/Ligue-1-Stats",
        "passing_url": "https://fbref.com/en/comps/13/passing/Ligue-1-Stats",
        "misc_url": "https://fbref.com/en/comps/13/misc/Ligue-1-Stats",
    },
    {
        "name": "Eredivisie",
        "code": "NED1",
        "comp_id": 23,
        "standard_url": "https://fbref.com/en/comps/23/stats/Eredivisie-Stats",
        "shooting_url": "https://fbref.com/en/comps/23/shooting/Eredivisie-Stats",
        "possession_url": "https://fbref.com/en/comps/23/possession/Eredivisie-Stats",
        "passing_url": "https://fbref.com/en/comps/23/passing/Eredivisie-Stats",
        "misc_url": "https://fbref.com/en/comps/23/misc/Eredivisie-Stats",
    },
    {
        "name": "Liga Portugal",
        "code": "POR1",
        "comp_id": 32,
        "standard_url": "https://fbref.com/en/comps/32/stats/Primeira-Liga-Stats",
        "shooting_url": "https://fbref.com/en/comps/32/shooting/Primeira-Liga-Stats",
        "possession_url": "https://fbref.com/en/comps/32/possession/Primeira-Liga-Stats",
        "passing_url": "https://fbref.com/en/comps/32/passing/Primeira-Liga-Stats",
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


def compute_att_rating(
    gls_per90: float | None,
    ga_per90: float | None,
    sot_per90: float | None,
    g_per_shot: float | None,
    succ_per90: float | None,
    fld_per90: float | None,
    kp_per90: float | None,
    npxg_xag_per90: float | None,
) -> float:
    """
    Calcola rating ATT puro scala 4-10.
    Pesi: Gls 23%, G+A 22%, SoT 12%, G/Sh 12%, Succ 8%, Fld 8%, KP 8%, npxG+xAG 7%
    """
    gls_norm   = normalize_0_1(gls_per90,       min_val=0.0,  max_val=1.0)
    ga_norm    = normalize_0_1(ga_per90,        min_val=0.0,  max_val=1.2)
    sot_norm   = normalize_0_1(sot_per90,       min_val=0.0,  max_val=2.5)
    gsh_norm   = normalize_0_1(g_per_shot,      min_val=0.0,  max_val=0.30)
    succ_norm  = normalize_0_1(succ_per90,      min_val=0.0,  max_val=2.0)
    fld_norm   = normalize_0_1(fld_per90,       min_val=0.0,  max_val=3.0)
    kp_norm    = normalize_0_1(kp_per90,        min_val=0.0,  max_val=2.0)
    npxg_norm  = normalize_0_1(npxg_xag_per90,  min_val=0.0,  max_val=1.0)

    q = (
        0.23 * gls_norm +
        0.22 * ga_norm +
        0.12 * sot_norm +
        0.12 * gsh_norm +
        0.08 * succ_norm +
        0.08 * fld_norm +
        0.08 * kp_norm +
        0.07 * npxg_norm
    )

    rating_puro = 4.0 + 6.0 * q
    return rating_puro


# ================== SCRAPING 4 TABELLE ==================

def scrape_standard_atts(scraper, url: str) -> Dict[tuple, Dict[str, Any]]:
    """Estrae attaccanti dalla tabella STANDARD."""
    resp = scraper.get(url, timeout=40)
    if resp.status_code != 200:
        return {}

    table = extract_table_from_comments_or_dom(resp.text, r"stats_standard")
    if not table:
        return {}

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")

    atts: Dict[tuple, Dict[str, Any]] = {}

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
        if role != "ATT":
            continue

        cell_min = r.find("td", {"data-stat": "minutes_90s"})
        minutes_90s = parse_float_safe(cell_min.get_text(strip=True)) if cell_min else None

        cell_gls  = r.find("td", {"data-stat": "goals_per90"})
        cell_ga   = r.find("td", {"data-stat": "goals_assists_per90"})
        cell_npxg = r.find("td", {"data-stat": "npxg_xg_assist_per90"})

        gls_per90       = parse_float_safe(cell_gls.get_text(strip=True)) if cell_gls else None
        ga_per90        = parse_float_safe(cell_ga.get_text(strip=True)) if cell_ga else None
        npxg_xag_per90  = parse_float_safe(cell_npxg.get_text(strip=True)) if cell_npxg else None

        key = (player_name, team_name)
        atts[key] = {
            "player_name": player_name,
            "team_name": team_name,
            "pos_raw": pos_raw,
            "role": role,
            "minutes_90s": minutes_90s,
            "gls_per90": gls_per90,
            "ga_per90": ga_per90,
            "npxg_xag_per90": npxg_xag_per90,
        }

    return atts


def scrape_shooting(scraper, url: str, atts: Dict[tuple, Dict[str, Any]]) -> None:
    """Aggiunge SoT/90 e G/Sh."""
    resp = scraper.get(url, timeout=40)
    if resp.status_code != 200:
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_shooting")
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
        if key not in atts:
            continue

        cell_sot = r.find("td", {"data-stat": "shots_on_target_per90"})
        cell_gsh = r.find("td", {"data-stat": "goals_per_shot"})

        sot_per90  = parse_float_safe(cell_sot.get_text(strip=True)) if cell_sot else None
        g_per_shot = parse_float_safe(cell_gsh.get_text(strip=True)) if cell_gsh else None

        atts[key]["sot_per90"] = sot_per90
        atts[key]["g_per_shot"] = g_per_shot


def scrape_possession(scraper, url: str, atts: Dict[tuple, Dict[str, Any]]) -> None:
    """Aggiunge Succ/90 (affronti riusciti)."""
    resp = scraper.get(url, timeout=40)
    if resp.status_code != 200:
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_possession")
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
        if key not in atts:
            continue

        minutes_90s = atts[key].get("minutes_90s")

        cell_succ = r.find("td", {"data-stat": "take_ons_won"})
        succ = parse_float_safe(cell_succ.get_text(strip=True)) if cell_succ else None

        if not minutes_90s or minutes_90s == 0 or succ is None:
            succ_per90 = None
        else:
            succ_per90 = succ / minutes_90s

        atts[key]["succ_per90"] = succ_per90


def scrape_passing(scraper, url: str, atts: Dict[tuple, Dict[str, Any]]) -> None:
    """Aggiunge KP/90 (passaggi chiave)."""
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
        if key not in atts:
            continue

        minutes_90s = atts[key].get("minutes_90s")

        cell_kp = r.find("td", {"data-stat": "assisted_shots"})
        kp = parse_float_safe(cell_kp.get_text(strip=True)) if cell_kp else None

        if not minutes_90s or minutes_90s == 0 or kp is None:
            kp_per90 = None
        else:
            kp_per90 = kp / minutes_90s

        atts[key]["kp_per90"] = kp_per90


def scrape_misc(scraper, url: str, atts: Dict[tuple, Dict[str, Any]]) -> None:
    """Aggiunge Fld/90 (falli subiti)."""
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
        if key not in atts:
            continue

        minutes_90s = atts[key].get("minutes_90s")

        cell_fld = r.find("td", {"data-stat": "fouled"})
        fld = parse_float_safe(cell_fld.get_text(strip=True)) if cell_fld else None

        if not minutes_90s or minutes_90s == 0 or fld is None:
            fld_per90 = None
        else:
            fld_per90 = fld / minutes_90s

        atts[key]["fld_per90"] = fld_per90


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
        atts = scrape_standard_atts(scraper, lg["standard_url"])
        print(f"   ➜ Attaccanti trovati in STANDARD: {len(atts)}")
        if not atts:
            print("   ⚠️ Nessun attaccante, salto lega.")
            continue

        time.sleep(10)

        # --- SHOOTING ---
        print(f"➡️  Scarico SHOOTING: {lg['shooting_url']}")
        scrape_shooting(scraper, lg["shooting_url"], atts)
        print(f"   ➜ Dati SHOOTING aggiunti")

        time.sleep(10)

        # --- POSSESSION ---
        print(f"➡️  Scarico POSSESSION: {lg['possession_url']}")
        scrape_possession(scraper, lg["possession_url"], atts)
        print(f"   ➜ Dati POSSESSION aggiunti")

        time.sleep(10)

        # --- PASSING ---
        print(f"➡️  Scarico PASSING: {lg['passing_url']}")
        scrape_passing(scraper, lg["passing_url"], atts)
        print(f"   ➜ Dati PASSING aggiunti")

        time.sleep(10)

        # --- MISC ---
        print(f"➡️  Scarico MISC: {lg['misc_url']}")
        scrape_misc(scraper, lg["misc_url"], atts)
        print(f"   ➜ Dati MISC aggiunti")

        # --- Merge + calcolo rating + upsert Mongo ---
        bulk_ops = []

        for (player_name, team_name), data in atts.items():
            gls_per90       = data.get("gls_per90")
            ga_per90        = data.get("ga_per90")
            sot_per90       = data.get("sot_per90")
            g_per_shot      = data.get("g_per_shot")
            succ_per90      = data.get("succ_per90")
            fld_per90       = data.get("fld_per90")
            kp_per90        = data.get("kp_per90")
            npxg_xag_per90  = data.get("npxg_xag_per90")

            rating_puro = compute_att_rating(
                gls_per90,
                ga_per90,
                sot_per90,
                g_per_shot,
                succ_per90,
                fld_per90,
                kp_per90,
                npxg_xag_per90,
            )

            doc_filter = {
                "season": SEASON,
                "league_code": lg["code"],
                "team_name_fbref": team_name,
                "player_name_fbref": player_name,
            }

            att_stats = {
                "gls_per90": gls_per90,
                "ga_per90": ga_per90,
                "sot_per90": sot_per90,
                "g_per_shot": g_per_shot,
                "succ_per90": succ_per90,
                "fld_per90": fld_per90,
                "kp_per90": kp_per90,
                "npxg_xag_per90": npxg_xag_per90,
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
                    "att_stats": att_stats,
                    "att_rating": {
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
            print("   ⚠️ Nessun attaccante da scrivere per questa lega.")

        # Pausa tra leghe
        time.sleep(10)

    print("\n✅ SCRAPER ATTACCANTI FBREF COMPLETATO.")


if __name__ == "__main__":
    main()