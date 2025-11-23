import requests
from bs4 import BeautifulSoup
import pymongo
import os
import time
import random
from dotenv import load_dotenv

# 1. CONFIGURAZIONE BASE
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', '.env')
load_dotenv(env_path)

MONGO_URI = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
if not MONGO_URI:
    print("❌ ERRORE: Variabile MONGO_URI non trovata.")
    exit()

client = pymongo.MongoClient(MONGO_URI)
db = client.get_database()
teams_collection = db['teams']

# 2. URL SOCCERSTATS PER SERIE C
# italy3 = Serie C Group A, italy4 = Group B, italy5 = Group C
SOCCERSTATS_LEAGUES = [
    {
        "name": "Serie C - Girone A",
        "code": "italy3",
        "url": "https://www.soccerstats.com/latest.asp?league=italy3"
    },
    {
        "name": "Serie C - Girone B",
        "code": "italy4",
        "url": "https://www.soccerstats.com/latest.asp?league=italy4"
    },
    {
        "name": "Serie C - Girone C",
        "code": "italy5",
        "url": "https://www.soccerstats.com/latest.asp?league=italy5"
    },
]

def scrape_soccerstats_c():
    print("🚀 AVVIO SCRAPER CLASSIFICHE SERIE C DA SOCCERSTATS")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }

    for league in SOCCERSTATS_LEAGUES:
        name = league["name"]
        url = league["url"]

        print(f"\n🌍 Serie C: {name}")
        print(f"   URL: {url}")

        try:
            # Pausa gentile per non dare nell'occhio
            wait = random.uniform(3, 6)
            print(f"   ⏳ Attendo {wait:.1f}s...")
            time.sleep(wait)

            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                print(f"   ❌ HTTP {resp.status_code} su {name}")
                continue

            soup = BeautifulSoup(resp.content, "html.parser")

            # SoccerStats ha una tabella "Table" con header GP, W, D, L, GF, GA, GD, Pts, Form...
            # Nel dump testuale la vediamo dopo il titolo "## Table"
            table = soup.find("table")
            # Se ce ne sono più di una, prendiamo quella con intestazioni tipiche
            tables = soup.find_all("table")
            target_table = None

            for t in tables:
                header_row = t.find("tr")
                if not header_row:
                    continue
                headers_cells = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
                if "GP" in headers_cells and "W" in headers_cells and "Pts" in headers_cells:
                    target_table = t
                    break

            if not target_table:
                print("   ❌ Tabella classifica non trovata.")
                continue

            rows = target_table.find_all("tr")[1:]  # salta header
            updated_count = 0

            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 8:
                    continue

                try:
                    # Struttura tipica:
                    # 0: posizione
                    # 1: nome squadra
                    # 2: GP
                    # 3: W
                    # 4: D
                    # 5: L
                    # 6: GF
                    # 7: GA
                    # 8: GD
                    # 9: Pts
                    pos_text = cells[0].get_text(strip=True)
                    team_name = cells[1].get_text(strip=True)
                    gp_text = cells[2].get_text(strip=True)
                    w_text = cells[3].get_text(strip=True)
                    d_text = cells[4].get_text(strip=True)
                    l_text = cells[5].get_text(strip=True)
                    gf_text = cells[6].get_text(strip=True)
                    ga_text = cells[7].get_text(strip=True)
                    # In alcuni dump GD/Pts possono variare di indice, quindi controlliamo lunghezza
                    pts_text = None
                    if len(cells) >= 9:
                        pts_text = cells[8].get_text(strip=True)

                    def to_int(v):
                        try:
                            return int(v)
                        except:
                            return 0

                    ranking_data = {
                        "position": to_int(pos_text),
                        "played": to_int(gp_text),
                        "wins": to_int(w_text),
                        "draws": to_int(d_text),
                        "losses": to_int(l_text),
                        "goalsFor": to_int(gf_text),
                        "goalsAgainst": to_int(ga_text),
                        "points": to_int(pts_text) if pts_text is not None else 0,
                        "league": name,
                        "source": "soccerstats",
                        "lastUpdated": time.strftime("%Y-%m-%d")
                    }

                    # Aggiornamento documento squadra in 'teams'
                    # Attenzione: il nome deve combaciare con quello usato per Transfermarkt/FBRef.
                    # Se non coincide, in futuro potremo creare una mappa di alias.
                    result = teams_collection.update_one(
                        {"name": team_name},
                        {
                            "$set": {
                                "league": name,
                                "stats.ranking_c": ranking_data
                            }
                        },
                        upsert=True
                    )
                    updated_count += 1

                except Exception as e:
                    # Non bloccare tutto su una riga strana
                    continue

            print(f"   ✅ Aggiornate {updated_count} squadre per {name}")

        except Exception as e:
            print(f"   ❌ Errore su {name}: {e}")

    print("\n🏁 SCRAPER SOCCERSTATS SERIE C COMPLETATO.")

if __name__ == "__main__":
    scrape_soccerstats_c()
