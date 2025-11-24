import requests
from bs4 import BeautifulSoup
import pymongo
import time

# CONFIGURAZIONE
MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/pup_pals_db?retryWrites=true&w=majority"
client = pymongo.MongoClient(MONGO_URI)
db = client['pup_pals_db']
teams_collection = db['teams']

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

def scrape_data_v3():
    print("🚀 AVVIO SCRAPER V3 (INDICI CALIBRATI SU DEBUG)")
    headers = {"User-Agent": "Mozilla/5.0"}

    for league in SOCCERSTATS_LEAGUES:
        print(f"\n🌍 Scarico dati per: {league['name']}...")
        try:
            resp = requests.get(league['url'], headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")
            
            rows = soup.find_all("tr")
            updated = 0

            for row in rows:
                cells = row.find_all("td")
                # La riga deve essere lunga abbastanza (almeno 29 celle per arrivare a GAa)
                if len(cells) < 29: continue
                if not cells[0].get_text(strip=True).isdigit(): continue

                team_name = cells[1].get_text(strip=True)
                
                # --- INDICI CALIBRATI SUL DEBUG ---
                # Posizione è cells[0]
                # Wh è cells[13] (46-33=13)
                
                try:
                    # CASA
                    wh = to_int(cells[13].get_text(strip=True))
                    dh = to_int(cells[14].get_text(strip=True))
                    lh = to_int(cells[15].get_text(strip=True))
                    gf_h = to_int(cells[16].get_text(strip=True))
                    ga_h = to_int(cells[17].get_text(strip=True))
                    gp_h = wh + dh + lh

                    # TRASFERTA
                    wa = to_int(cells[24].get_text(strip=True))
                    da = to_int(cells[25].get_text(strip=True))
                    la = to_int(cells[26].get_text(strip=True))
                    gf_a = to_int(cells[27].get_text(strip=True))
                    ga_a = to_int(cells[28].get_text(strip=True))
                    gp_a = wa + da + la
                    
                    # DEBUG: Controllo Roma
                    if "Roma" in team_name and updated == 0:
                         print(f"   👀 VERIFICA ROMA: Casa[{wh}+{dh}+{lh}={gp_h}] Trasferta[{wa}+{da}+{la}={gp_a}]")

                    # AGGIORNAMENTO DB
                    res = teams_collection.update_one(
                        {"name": team_name},
                        {"$set": {
                            "ranking": {
                                "league": league['name'],
                                "homeStats": {"played": gp_h, "goalsFor": gf_h, "goalsAgainst": ga_h},
                                "awayStats": {"played": gp_a, "goalsFor": gf_a, "goalsAgainst": ga_a}
                            }
                        }}
                    )
                    
                    if res.matched_count > 0:
                        updated += 1
                    else:
                        # Fallback alias
                        teams_collection.update_one(
                            {"aliases.soccerstats": team_name},
                            {"$set": {
                                "ranking": {
                                    "league": league['name'],
                                    "homeStats": {"played": gp_h, "goalsFor": gf_h, "goalsAgainst": ga_h},
                                    "awayStats": {"played": gp_a, "goalsFor": gf_a, "goalsAgainst": ga_a}
                                }
                            }}
                        )
                        updated += 1

                except Exception as e:
                    # print(f"Err: {e}")
                    continue

            print(f"   ✅ Aggiornate {updated} squadre.")

        except Exception as e:
            print(f"   ❌ Errore: {e}")

if __name__ == "__main__":
    scrape_data_v3()
