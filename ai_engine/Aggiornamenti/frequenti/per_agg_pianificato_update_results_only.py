import os
import sys
import time
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from config import db
    print(f"✅ DB Connesso: {db.name}")
except ImportError:
    print("❌ Errore Import Config")
    sys.exit(1)

# --- CONFIGURAZIONE ---
COLLECTION_NAME = "h2h_by_round"
TARGET_SEASON = "2025"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}

# Lista Campionati
LEAGUES_TM = [
    {"name": "Serie A", "url": f"https://www.transfermarkt.it/serie-a/gesamtspielplan/wettbewerb/IT1/saison_id/{TARGET_SEASON}"},
    {"name": "Serie B", "url": f"https://www.transfermarkt.it/serie-b/gesamtspielplan/wettbewerb/IT2/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone A", "url": f"https://www.transfermarkt.it/serie-c-girone-a/gesamtspielplan/wettbewerb/IT3A/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone B", "url": f"https://www.transfermarkt.it/serie-c-girone-b/gesamtspielplan/wettbewerb/IT3B/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone C", "url": f"https://www.transfermarkt.it/serie-c-girone-c/gesamtspielplan/wettbewerb/IT3C/saison_id/{TARGET_SEASON}"},
    {"name": "Premier League", "url": f"https://www.transfermarkt.it/premier-league/gesamtspielplan/wettbewerb/GB1/saison_id/{TARGET_SEASON}"},
    {"name": "La Liga", "url": f"https://www.transfermarkt.it/laliga/gesamtspielplan/wettbewerb/ES1/saison_id/{TARGET_SEASON}"},
    {"name": "Bundesliga", "url": f"https://www.transfermarkt.it/bundesliga/gesamtspielplan/wettbewerb/L1/saison_id/{TARGET_SEASON}"},
    {"name": "Ligue 1", "url": f"https://www.transfermarkt.it/ligue-1/gesamtspielplan/wettbewerb/FR1/saison_id/{TARGET_SEASON}"},
    {"name": "Eredivisie", "url": f"https://www.transfermarkt.it/eredivisie/gesamtspielplan/wettbewerb/NL1/saison_id/{TARGET_SEASON}"},
    {"name": "Liga Portugal", "url": f"https://www.transfermarkt.it/liga-nos/gesamtspielplan/wettbewerb/PO1/saison_id/{TARGET_SEASON}"}
]

def normalize_key(name):
    if not name:
        return ""
    return name.lower().strip().replace(" ", "").replace("-", "")

def process_league(col, league):
    print(f"\n🌍 Elaborazione: {league['name']}...")
    updated_count = 0

    try:
        resp = requests.get(league['url'], headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.content, "html.parser")

        headers = soup.find_all("div", class_="content-box-headline")

        for header in headers:
            round_name_tm = header.get_text(strip=True)
            if "Giornata" not in round_name_tm and "Turno" not in round_name_tm:
                continue

            safe_round = round_name_tm.replace(".", "").replace(" ", "")
            safe_league = league['name'].replace(" ", "")
            doc_id = f"{safe_league}_{safe_round}"

            # Recupero documento esistente
            db_doc = col.find_one({"_id": doc_id})
            if not db_doc:
                continue

            db_matches = db_doc.get("matches", [])
            modified_doc = False

            table = header.find_next("table")
            if not table:
                continue

            rows = table.find_all("tr")

            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue

                res_link = row.find("a", class_="ergebnis-link")
                if not res_link:
                    continue

                score_text = res_link.get_text(strip=True)
                if ":" not in score_text:
                    continue

                team_links = [
                    a.get_text(strip=True)
                    for a in row.find_all("a")
                    if a.get("title") and "spielbericht" not in a.get("href", "")
                ]

                if len(team_links) < 2:
                    continue

                home_tm = team_links[0]
                away_tm = team_links[-1]

                for m in db_matches:
                    h_db = normalize_key(m['home'])
                    a_db = normalize_key(m['away'])
                    h_tm = normalize_key(home_tm)
                    a_tm = normalize_key(away_tm)

                    if (h_tm in h_db or h_db in h_tm) and (a_tm in a_db or a_db in a_tm):
                        if m.get('real_score') != score_text:
                            m['real_score'] = score_text
                            m['status'] = "Finished"
                            modified_doc = True
                            updated_count += 1
                            print(f"   ✅ {m['home']} - {m['away']} -> {score_text}")
                        break

            if modified_doc:
                col.update_one(
                    {"_id": doc_id},
                    {"$set": {"matches": db_matches, "last_updated": datetime.now()}}
                )

    except Exception as e:
        print(f"   ❌ Errore: {e}")

    return updated_count

def run_auto_update():
    print("\n🚀 AGGIORNAMENTO AUTOMATICO – TUTTI I CAMPIONATI")
    col = db[COLLECTION_NAME]

    total = 0
    for league in LEAGUES_TM:
        total += process_league(col, league)

    print(f"\n🏁 FINE AGGIORNAMENTO AUTOMATICO")
    print(f"📊 Totale Partite Aggiornate: {total}")

if __name__ == "__main__":
    run_auto_update()
