"""
TEST - VERIFICA SQUADRE MANCANTI IN MONGO (CLUSTER ONLINE)
Confronta:
- squadre lette da Transfermarkt (startseite)
- squadre presenti in players_availability_tm (football_simulator_db)
e stampa quelle che mancano per ogni campionato.
"""

import re
import random
import time
import sys
sys.path.append('..')  # Aggiunge ai_engine al PATH
from config import db
import cloudscraper
from bs4 import BeautifulSoup

BASE_DOMAIN_IT = "https://www.transfermarkt.it"
BASE_DOMAIN_COM = "https://www.transfermarkt.com"

COMPETITIONS = [
    # Italia
    {"name": "Serie A", "league_code": "ITA1", "startseite_url": "https://www.transfermarkt.it/serie-a/startseite/wettbewerb/IT1", "base_domain": BASE_DOMAIN_IT},
    {"name": "Serie B", "league_code": "ITA2", "startseite_url": "https://www.transfermarkt.it/serie-b/startseite/wettbewerb/IT2", "base_domain": BASE_DOMAIN_IT},
    {"name": "Serie C - Girone A", "league_code": "ITA3A", "startseite_url": "https://www.transfermarkt.it/serie-c-girone-a/startseite/wettbewerb/IT3A", "base_domain": BASE_DOMAIN_IT},
    {"name": "Serie C - Girone B", "league_code": "ITA3B", "startseite_url": "https://www.transfermarkt.it/serie-c-girone-b/startseite/wettbewerb/IT3B", "base_domain": BASE_DOMAIN_IT},
    {"name": "Serie C - Girone C", "league_code": "ITA3C", "startseite_url": "https://www.transfermarkt.it/serie-c-girone-c/startseite/wettbewerb/IT3C", "base_domain": BASE_DOMAIN_IT},
    # Estero
    {"name": "Premier League", "league_code": "GB1", "startseite_url": "https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1", "base_domain": BASE_DOMAIN_COM},
    {"name": "La Liga", "league_code": "ES1", "startseite_url": "https://www.transfermarkt.com/la-liga/startseite/wettbewerb/ES1", "base_domain": BASE_DOMAIN_COM},
    {"name": "Eredivisie", "league_code": "NL1", "startseite_url": "https://www.transfermarkt.com/eredivisie/startseite/wettbewerb/NL1", "base_domain": BASE_DOMAIN_COM},
    {"name": "Bundesliga", "league_code": "DE1", "startseite_url": "https://www.transfermarkt.com/bundesliga/startseite/wettbewerb/L1", "base_domain": BASE_DOMAIN_COM},
    {"name": "Ligue 1", "league_code": "FR1", "startseite_url": "https://www.transfermarkt.com/ligue-1/startseite/wettbewerb/FR1", "base_domain": BASE_DOMAIN_COM},
    {"name": "Primeira Liga", "league_code": "PT1", "startseite_url": "https://www.transfermarkt.com/liga-nos/startseite/wettbewerb/PO1", "base_domain": BASE_DOMAIN_COM},
]

def create_scraper():
    s = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True}
    )
    s.headers.update({
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    })
    return s

def get_mongo_collection():
    return db["players_availability_tm"]

def get_teams_from_startseite(scraper, comp):
    """Ritorna dict team_id -> team_name per il campionato."""
    url = comp["startseite_url"]
    print(f"   🔎 Leggo startseite: {url}")
    try:
        resp = scraper.get(url, timeout=30)
    except Exception as e:
        print(f"   ❌ Errore richiesta: {e}")
        return {}

    if resp.status_code != 200:
        print(f"   ⚠️ Status {resp.status_code}")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="items")
    if not table:
        print("   ⚠️ Tabella 'items' non trovata")
        return {}

    teams = {}
    for row in table.find_all("tr"):
        cell = row.find("td", class_="hauptlink")
        if not cell:
            continue
        a = cell.find("a")
        if not a or not a.get("href"):
            continue
        name = a.get_text(strip=True)
        href = a["href"]
        m = re.match(r"^/([^/]+)/startseite/verein/(\d+)", href)
        if not m:
            continue
        team_id = int(m.group(2))
        teams[team_id] = name

    print(f"   ✅ Squadre trovate su TM: {len(teams)}")
    return teams

def get_teams_from_mongo(coll, league_code):
    """Ritorna dict team_id -> nome (da Mongo) per la lega."""
    pipeline = [
        {"$match": {"league_code": league_code}},
        {"$group": {"_id": "$team_id", "team_name": {"$first": "$team_name"}}}
    ]
    res = coll.aggregate(pipeline)
    teams = {}
    for doc in res:
        tid = doc["_id"]
        name = doc.get("team_name", "")
        teams[tid] = name
    print(f"   ✅ Squadre presenti in Mongo: {len(teams)}")
    return teams

def main():
    scraper = create_scraper()
    coll = get_mongo_collection()

    for comp in COMPETITIONS:
        print("\n" + "="*80)
        print(f"🏆 TEST CAMPIONATO: {comp['name']} ({comp['league_code']})")
        print("="*80)

        tm_teams = get_teams_from_startseite(scraper, comp)
        time.sleep(random.uniform(1, 3))
        mongo_teams = get_teams_from_mongo(coll, comp["league_code"])

        tm_ids = set(tm_teams.keys())
        mongo_ids = set(mongo_teams.keys())

        missing_ids = tm_ids - mongo_ids  # esistono su TM ma non in Mongo
        extra_ids = mongo_ids - tm_ids    # esistono in Mongo ma non più su TM (raro)

        if not missing_ids and not extra_ids:
            print("   ✅ Nessuna differenza: tutte le squadre combaciano.\n")
            continue

        if missing_ids:
            print("   ❗ Squadre MANCANTI in Mongo (da recuperare):")
            for tid in sorted(missing_ids):
                print(f"      - {tid}: {tm_teams.get(tid)}")

        if extra_ids:
            print("\n   ⚠️ Squadre presenti in Mongo ma NON su TM (controllare):")
            for tid in sorted(extra_ids):
                print(f"      - {tid}: {mongo_teams.get(tid)}")

        print()

    print("\n✅ Test completato.\n")

if __name__ == "__main__":
    main()
