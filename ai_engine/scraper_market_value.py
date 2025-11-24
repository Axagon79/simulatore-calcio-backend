import requests
from bs4 import BeautifulSoup
import pymongo
import os
import time
from dotenv import load_dotenv
from fake_useragent import UserAgent
import random

# --- CONFIGURAZIONE ---
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', '.env') # O il percorso corretto del tuo .env
load_dotenv(env_path)

MONGO_URI = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
if not MONGO_URI:
    print("❌ ERRORE: Variabile MONGO_URI non trovata nel file .env")
    # Fallback per test rapido se serve
    # MONGO_URI = "mongodb+srv://..." 
    exit()

client = pymongo.MongoClient(MONGO_URI)
db = client.get_database()
teams_collection = db['teams']

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

def smart_find_team(tm_name):
    """
    Cerca la squadra nel DB pulito usando Nome Esatto, Regex o Alias.
    Evita di creare duplicati.
    """
    # 1. Cerca nome esatto
    t = teams_collection.find_one({"name": tm_name})
    if t: return t
    
    # 2. Cerca parziale (case insensitive)
    t = teams_collection.find_one({"name": {"$regex": f"^{tm_name}$", "$options": "i"}})
    if t: return t
    
    # 3. Cerca negli alias (la parte più importante!)
    t = teams_collection.find_one({"aliases": tm_name})
    if t: return t
    
    return None

def scrape_league(league_conf):
    url = league_conf['url']
    league_name = league_conf['name']
    
    print(f"\n🌍 {league_name}: Scarico Valori di Mercato...")
    
    ua = UserAgent()
    headers = {'User-Agent': ua.random}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"❌ Errore HTTP {r.status_code}")
            return

        soup = BeautifulSoup(r.content, 'html.parser')
        table = soup.find('table', class_='items')
        
        if not table:
            print(f"❌ Tabella non trovata!")
            return

        rows = table.find('tbody').find_all('tr', recursive=False)
        updated_count = 0
        
        for row in rows:
            name_tag = row.find('td', class_='hauptlink')
            if not name_tag: continue
            
            # Nome usato da Transfermarkt
            tm_name = name_tag.text.strip().replace('\n', '')

            # Estrazione Valore
            value_cells = row.find_all('td', class_='rechts')
            market_value = 0
            raw_val = "0"
            
            for cell in reversed(value_cells):
                txt = cell.text.strip()
                if '€' in txt:
                    market_value = clean_money_value(txt)
                    raw_val = txt
                    break

            # --- INTEGRAZIONE INTELLIGENTE ---
            # Invece di fare upsert brutale, cerchiamo la squadra esistente
            db_team = smart_find_team(tm_name)

            if db_team:
                # Aggiorniamo solo il valore di mercato della squadra esistente
                teams_collection.update_one(
                    {"_id": db_team["_id"]},
                    {
                        "$set": {
                            "marketValue": market_value, # Salvo direttamente alla radice o in stats
                            "stats.marketValue": market_value,
                            "lastUpdateValue": time.strftime("%Y-%m-%d")
                        },
                        # Aggiungiamo il nome TM agli alias se non c'è, così la prossima volta la trova subito
                        "$addToSet": {"aliases": tm_name} 
                    }
                )
                print(f"   💰 {db_team['name']:20} <- Aggiornato valore: {raw_val}")
                updated_count += 1
            else:
                print(f"   ⚠️  Saltato: '{tm_name}' non trovato nel DB (Nessun match con alias).")

        print(f"✨ Aggiornati valori per {updated_count} squadre in {league_name}.")

    except Exception as e:
        print(f"❌ Errore critico: {e}")

if __name__ == "__main__":
    print(f"🚀 START SCRAPER VALORI (TRANSFERMARKT)")
    
    for league in LEAGUES_CONFIG:
        scrape_league(league)
        time.sleep(3) # Pausa etica
        
    print("\n🏁 Finito. I valori di mercato sono stati integrati nel DB.")
