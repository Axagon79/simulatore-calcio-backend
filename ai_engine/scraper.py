import requests
from bs4 import BeautifulSoup
import pymongo
import os
import time
from dotenv import load_dotenv
from fake_useragent import UserAgent
import random

# 1. CARICAMENTO VARIABILI
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', '.env')
load_dotenv(env_path)

MONGO_URI = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
if not MONGO_URI:
    print("❌ ERRORE: Variabile MONGO_URI non trovata nel file .env")
    exit()

client = pymongo.MongoClient(MONGO_URI)
db = client.get_database()
teams_collection = db['teams']

# --- CONFIGURAZIONE COMPLETA (CON SERIE B) ---
LEAGUES_CONFIG = [
    # --- ITALIA ---
    {
        "name": "Serie A",
        "country": "Italy",
        "url": "https://www.transfermarkt.it/serie-a/startseite/wettbewerb/IT1"
    },
    {
        "name": "Serie B",
        "country": "Italy",
        "url": "https://www.transfermarkt.it/serie-b/startseite/wettbewerb/IT2"
    },
    {
        "name": "Serie C - Girone A",
        "country": "Italy",
        "url": "https://www.transfermarkt.it/serie-c-girone-a/startseite/wettbewerb/IT3A"
    },
    {
        "name": "Serie C - Girone B",
        "country": "Italy",
        "url": "https://www.transfermarkt.it/serie-c-girone-b/startseite/wettbewerb/IT3B"
    },
    {
        "name": "Serie C - Girone C",
        "country": "Italy",
        "url": "https://www.transfermarkt.it/serie-c-girone-c/startseite/wettbewerb/IT3C"
    },
    
    # --- EUROPA TOP 5 ---
    {
        "name": "Premier League",
        "country": "England",
        "url": "https://www.transfermarkt.it/premier-league/startseite/wettbewerb/GB1"
    },
    {
        "name": "La Liga",
        "country": "Spain",
        "url": "https://www.transfermarkt.it/laliga/startseite/wettbewerb/ES1"
    },
    {
        "name": "Bundesliga",
        "country": "Germany",
        "url": "https://www.transfermarkt.it/bundesliga/startseite/wettbewerb/L1"
    },
    {
        "name": "Ligue 1",
        "country": "France",
        "url": "https://www.transfermarkt.it/ligue-1/startseite/wettbewerb/FR1"
    },

    # --- ALTRE LEGHE TECNICHE ---
    {
        "name": "Eredivisie",
        "country": "Netherlands",
        "url": "https://www.transfermarkt.it/eredivisie/startseite/wettbewerb/NL1"
    },
    {
        "name": "Liga Portugal",
        "country": "Portugal",
        "url": "https://www.transfermarkt.it/liga-portugal/startseite/wettbewerb/PO1"
    }
]

def clean_money_value(value_str):
    if not value_str: return 0
    val = value_str.replace('€', '').strip()
    
    multiplier = 1
    if 'mld' in val or 'bn' in val: 
        multiplier = 1_000_000_000
        val = val.replace('mld', '').replace('bn', '')
    elif 'mln' in val or 'm' in val: 
        multiplier = 1_000_000
        val = val.replace('mln', '').replace('m', '')
    elif 'mila' in val or 'k' in val: 
        multiplier = 1_000
        val = val.replace('mila', '').replace('k', '')
        
    try:
        val = val.replace(',', '.')
        return float(val) * multiplier
    except:
        return 0

def scrape_league(league_conf):
    url = league_conf['url']
    league_name = league_conf['name']
    country = league_conf['country']
    
    print(f"\n🌍 Inizio scraping: {league_name} ({country})")
    
    ua = UserAgent()
    headers = {'User-Agent': ua.random, 'Accept-Language': 'it-IT,it;q=0.9'}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"❌ Errore HTTP {r.status_code}")
            return

        soup = BeautifulSoup(r.content, 'html.parser')
        table = soup.find('table', class_='items')
        
        if not table:
            print(f"❌ Tabella non trovata per {league_name}!")
            return

        rows = table.find('tbody').find_all('tr', recursive=False)
        count = 0
        
        for row in rows:
            name_tag = row.find('td', class_='hauptlink')
            if not name_tag: continue
            team_name = name_tag.text.strip().replace('\n', '')

            value_cells = row.find_all('td', class_='rechts')
            market_value = 0
            raw_value = "0"

            found_val = False
            # Cerca cella con simbolo valuta
            for cell in reversed(value_cells):
                txt = cell.text.strip()
                if '€' in txt or 'mln' in txt or 'mila' in txt:
                    market_value = clean_money_value(txt)
                    raw_value = txt
                    found_val = True
                    break
            
            # Fallback ultima cella
            if not found_val and value_cells:
                last_cell = value_cells[-1]
                market_value = clean_money_value(last_cell.text.strip())
                raw_value = last_cell.text.strip()

            # SALVA NEL DB
            teams_collection.update_one(
                {"name": team_name}, 
                {"$set": {
                    "name": team_name,
                    "league": league_name,
                    "country": country,
                    "stats.marketValue": market_value,
                    "stats.lastUpdated": time.strftime("%Y-%m-%d")
                }}, 
                upsert=True
            )
            count += 1
            print(f"\r   ✅ {team_name[:20]:20} ({raw_value})", end="")
            
        print(f"\n   ✨ Completato: {count} squadre aggiornate.")

    except Exception as e:
        print(f"❌ Errore su {league_name}: {e}")

if __name__ == "__main__":
    print(f"🚀 START SCRAPER - {len(LEAGUES_CONFIG)} Campionati Selezionati")
    
    for league in LEAGUES_CONFIG:
        scrape_league(league)
        wait = random.randint(4, 7)
        print(f"⏳ Pause {wait}s...")
        time.sleep(wait)
        
    print("\n🏁 TUTTO FINITO! Database popolato.")
