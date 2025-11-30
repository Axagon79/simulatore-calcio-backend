import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

import cloudscraper
from bs4 import BeautifulSoup
import os
import time
import random
from dotenv import load_dotenv
import re

# 1. CONFIGURAZIONE BASE
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', '.env')
load_dotenv(env_path)

MONGO_URI = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
if not MONGO_URI:
    print("❌ ERRORE: Variabile MONGO_URI non trovata.")
    exit()

matches_collection = db['matches_history']

# 2. CONFIGURAZIONE URL FBREF
LEAGUES_URLS = [
    {"name": "Serie A", "url": "https://fbref.com/en/comps/11/schedule/Serie-A-Scores-and-Fixtures"},
    {"name": "Serie B", "url": "https://fbref.com/en/comps/18/schedule/Serie-B-Scores-and-Fixtures"},
    {"name": "Serie C - Girone A", "url": "https://fbref.com/en/comps/32/schedule/Serie-C-Group-A-Scores-and-Fixtures"},
    {"name": "Serie C - Girone B", "url": "https://fbref.com/en/comps/33/schedule/Serie-C-Group-B-Scores-and-Fixtures"},
    {"name": "Serie C - Girone C", "url": "https://fbref.com/en/comps/34/schedule/Serie-C-Group-C-Scores-and-Fixtures"},
    
    {"name": "Premier League", "url": "https://fbref.com/en/comps/9/schedule/Premier-League-Scores-and-Fixtures"},
    {"name": "La Liga", "url": "https://fbref.com/en/comps/12/schedule/La-Liga-Scores-and-Fixtures"},
    {"name": "Bundesliga", "url": "https://fbref.com/en/comps/20/schedule/Bundesliga-Scores-and-Fixtures"},
    {"name": "Ligue 1", "url": "https://fbref.com/en/comps/13/schedule/Ligue-1-Scores-and-Fixtures"},
    {"name": "Eredivisie", "url": "https://fbref.com/en/comps/23/schedule/Eredivisie-Scores-and-Fixtures"},
    {"name": "Liga Portugal", "url": "https://fbref.com/en/comps/32/schedule/Primeira-Liga-Scores-and-Fixtures"} 
]

def scrape_fbref_results():
    print("🚀 AVVIO SCRAPER FBREF (Modalità Anti-Cloudflare 🛡️)")
    
    # Creiamo lo scraper che simula un browser Chrome vero
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )

    for league in LEAGUES_URLS:
        league_name = league['name']
        url = league['url']
        
        print(f"\n🌍 Tentativo accesso: {league_name}")
        
        try:
            # Pausa tattica (variabile per sembrare umano)
            wait_time = random.uniform(6, 10) 
            print(f"   ⏳ Attesa stealth: {wait_time:.1f}s...")
            time.sleep(wait_time)

            # RICHIESTA TRAMITE CLOUDSCRAPER (Bye Bye 403!)
            response = scraper.get(url)
            
            if response.status_code == 403:
                print("❌ ANCORA 403! Maledizione, hanno protezioni extra.")
                continue
                
            if response.status_code != 200:
                print(f"❌ Errore HTTP {response.status_code}")
                continue

            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Cerca tabelle
            tables = soup.find_all('table')
            target_table = None
            
            for t in tables:
                # Cerca intestazione che contiene 'Score' o 'Risultato'
                if t.find('th', text=re.compile(r'Score|Risultato')):
                    target_table = t
                    break
            
            if not target_table and tables:
                target_table = tables[0] # Fallback alla prima tabella

            if not target_table:
                print("❌ Tabella non trovata nella pagina.")
                continue

            rows = target_table.find('tbody').find_all('tr')
            count = 0
            
            for row in rows:
                if 'class' in row.attrs and ('thead' in row.attrs['class'] or 'spacer' in row.attrs['class']):
                    continue
                
                # Selettori specifici FBRef
                date_cell = row.find('td', {'data-stat': 'date'})
                home_cell = row.find('td', {'data-stat': 'home_team'})
                away_cell = row.find('td', {'data-stat': 'away_team'})
                score_cell = row.find('td', {'data-stat': 'score'})
                
                # xG (se presenti)
                xg_home_cell = row.find('td', {'data-stat': 'home_xg'})
                xg_away_cell = row.find('td', {'data-stat': 'away_xg'})

                if not (date_cell and home_cell and away_cell and score_cell):
                    continue
                
                score_text = score_cell.text.strip()
                if not score_text: continue 

                try:
                    goals = re.split(r'[–-]', score_text)
                    if len(goals) != 2: continue
                    
                    home_goals = int(goals[0])
                    away_goals = int(goals[1])
                    
                    if home_goals > away_goals: result = '1'
                    elif away_goals > home_goals: result = '2'
                    else: result = 'X'

                    match_data = {
                        "league": league_name,
                        "date": date_cell.text.strip(),
                        "homeTeam": home_cell.text.strip(),
                        "awayTeam": away_cell.text.strip(),
                        "homeGoals": home_goals,
                        "awayGoals": away_goals,
                        "result": result,
                        "xg_home": float(xg_home_cell.text.strip()) if xg_home_cell and xg_home_cell.text.strip() else None,
                        "xg_away": float(xg_away_cell.text.strip()) if xg_away_cell and xg_away_cell.text.strip() else None,
                        "source": "fbref"
                    }
                    
                    unique_id = f"{match_data['date']}_{match_data['homeTeam']}_{match_data['awayTeam']}"
                    
                    matches_collection.update_one(
                        {"unique_id": unique_id},
                        {"$set": match_data},
                        upsert=True
                    )
                    count += 1
                    
                except:
                    continue

            print(f"   ✅ BOOM! {count} partite salvate per {league_name}")

        except Exception as e:
            print(f"❌ Errore durante lo scraping di {league_name}: {e}")

    print("\n🏁 MISSIONE COMPIUTA (Si spera).")

if __name__ == "__main__":
    scrape_fbref_results()