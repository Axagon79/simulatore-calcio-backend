import requests
from bs4 import BeautifulSoup
import pymongo
import time

# CONFIGURAZIONE
MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/pup_pals_db?retryWrites=true&w=majority"
client = pymongo.MongoClient(MONGO_URI)
db = client['pup_pals_db']
teams_collection = db['teams']

# LISTA URL
SOCCERSTATS_LEAGUES = [
    {"name": "Serie A", "url": "https://www.soccerstats.com/widetable.asp?league=italy"},
    {"name": "Serie B", "url": "https://www.soccerstats.com/widetable.asp?league=italy2"},
    {"name": "Serie C - Girone A", "url": "https://www.soccerstats.com/widetable.asp?league=italy3"},
    {"name": "Serie C - Girone B", "url": "https://www.soccerstats.com/widetable.asp?league=italy4"},
    {"name": "Serie C - Girone C", "url": "https://www.soccerstats.com/widetable.asp?league=italy5"},
    {"name": "Premier League", "url": "https://www.soccerstats.com/widetable.asp?league=england"},
    {"name": "La Liga", "url": "https://www.soccerstats.com/widetable.asp?league=spain"},
    {"name": "Bundesliga", "url": "https://www.soccerstats.com/widetable.asp?league=germany"},
    {"name": "Ligue 1", "url": "https://www.soccerstats.com/widetable.asp?league=france"},
    {"name": "Eredivisie", "url": "https://www.soccerstats.com/widetable.asp?league=netherlands"},
    {"name": "Liga Portugal", "url": "https://www.soccerstats.com/widetable.asp?league=portugal"},
]

def to_int(val):
    try:
        return int(val)
    except:
        return 0

def scrape_data_v4_smart():
    print("🚀 AVVIO SCRAPER V4 (SMART MATCHING)")
    headers = {"User-Agent": "Mozilla/5.0"}

    for league in SOCCERSTATS_LEAGUES:
        print(f"\n🌍 Scarico dati per: {league['name']}...")
        try:
            resp = requests.get(league['url'], headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")

            # --- LOGICA HOMEAWAY (SERIE C) ---
            if "homeaway.asp" in league['url']:
                tables = soup.find_all('table')
                valid_tables = [t for t in tables if len(t.find_all('tr')) > 10]

                if len(valid_tables) < 2: continue

                home_map = {}
                # Estrazione Home
                for r in valid_tables[0].find_all('tr'):
                    c = r.find_all('td')
                    if len(c) < 8: continue
                    try:
                        tn = c[1].get_text(strip=True)
                        pts = to_int(c[-1].get_text(strip=True))
                        home_map[tn] = pts
                    except: continue

                # Estrazione Away
                away_map = {}
                for r in valid_tables[1].find_all('tr'):
                    c = r.find_all('td')
                    if len(c) < 8: continue
                    try:
                        tn = c[1].get_text(strip=True)
                        pts = to_int(c[-1].get_text(strip=True))
                        away_map[tn] = pts
                    except: continue

                # Aggiornamento DB con Smart Matching
                cnt = 0
                for team_name, h_pts in home_map.items():
                    a_pts = away_map.get(team_name, 0)

                    # QUERY SMART: Cerca per nome, alias oggetto O alias array
                    filter_q = {
                        "$or": [
                            {"name": team_name},
                            {"aliases.soccerstats": team_name}, # Caso Object
                            {"aliases": team_name}              # Caso Array
                        ]
                    }

                    res = teams_collection.update_one(
                        filter_q,
                        {"$set": {
                            "ranking.homePoints": h_pts, 
                            "ranking.awayPoints": a_pts,
                            "ranking.league": league['name']
                        }}
                    )
                    if res.matched_count > 0: cnt += 1
                print(f"   ✅ Aggiornati {cnt} team (Serie C).")

            # --- LOGICA WIDETABLE (MAGGIORI) ---
            else:
                rows = soup.find_all("tr")
                updated = 0
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) < 29: continue
                    if not cells[0].get_text(strip=True).isdigit(): continue

                    team_name = cells[1].get_text(strip=True)

                    try:
                        # Dati Punti
                        wh = to_int(cells[13].get_text(strip=True))
                        dh = to_int(cells[14].get_text(strip=True))
                        pts_h = (wh * 3) + dh 

                        wa = to_int(cells[24].get_text(strip=True))
                        da = to_int(cells[25].get_text(strip=True))
                        pts_a = (wa * 3) + da 

                        # QUERY SMART
                        filter_q = {
                            "$or": [
                                {"name": team_name},
                                {"aliases.soccerstats": team_name}, # Caso Object
                                {"aliases": team_name}              # Caso Array
                            ]
                        }

                        update_doc = {
                            "ranking.homePoints": pts_h,
                            "ranking.awayPoints": pts_a,
                            "ranking.league": league['name']
                        }
                        # Aggiungiamo anche stats played se servono per il calcolo media
                        # Ma ci limitiamo ai punti come richiesto per ora

                        res = teams_collection.update_one(filter_q, {"$set": update_doc})

                        if res.matched_count > 0: updated += 1

                    except: continue

                print(f"   ✅ Aggiornate {updated} squadre.")

        except Exception as e:
            print(f"   ❌ Errore: {e}")

if __name__ == "__main__":
    scrape_data_v4_smart()