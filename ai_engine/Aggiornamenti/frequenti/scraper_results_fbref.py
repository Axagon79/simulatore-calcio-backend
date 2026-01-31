import os
import sys
import time
import random
import re
# --- LOGICA FALLBACK: Se non trovi le librerie, prova altrove ---
percorsi_da_controllare = [
    # Posto 1: La cartella del tuo ambiente virtuale
    os.path.join(os.getcwd(), ".venv", "Lib", "site-packages"),
    # Posto 2: Il Python globale di Windows (dove abbiamo installato prima)
    r"C:\Users\lollo\AppData\Local\Programs\Python\Python313\Lib\site-packages",
    # Posto 3: La cartella dove si trova lo script (per i file locali)
    os.path.dirname(os.path.abspath(__file__))
]

for p in percorsi_da_controllare:
    if p not in sys.path and os.path.exists(p):
        sys.path.append(p)
# --------------------------------------------------------------

import gestore_accessi_fbref
from bs4 import BeautifulSoup
import cloudscraper
from dotenv import load_dotenv

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path: raise FileNotFoundError("No config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# 1. DATABASE
load_dotenv()
matches_collection = db['matches_history']       # Storico Partite
stats_collection = db['team_seasonal_stats']     # Medie Stagionali (xG 2.77)

print(f"🔌 Connesso a MongoDB.")

# 2. CONFIGURAZIONE DOPPIA (Fixture + Stats)
LEAGUES_CONFIG = [
    # ITALIA
    {
        "name": "Serie A", 
        "fixtures": "https://fbref.com/en/comps/11/schedule/Serie-A-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/11/Serie-A-Stats"
    },
    {
        "name": "Serie B", 
        "fixtures": "https://fbref.com/en/comps/18/schedule/Serie-B-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/18/Serie-B-Stats"
    },
    
    # EUROPA TOP
    {
        "name": "Premier League", 
        "fixtures": "https://fbref.com/en/comps/9/schedule/Premier-League-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/9/Premier-League-Stats"
    },
    {
        "name": "La Liga", 
        "fixtures": "https://fbref.com/en/comps/12/schedule/La-Liga-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/12/La-Liga-Stats"
    },
    {
        "name": "Bundesliga", 
        "fixtures": "https://fbref.com/en/comps/20/schedule/Bundesliga-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/20/Bundesliga-Stats"
    },
    {
        "name": "Ligue 1", 
        "fixtures": "https://fbref.com/en/comps/13/schedule/Ligue-1-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/13/Ligue-1-Stats"
    },
    {
        "name": "Eredivisie", 
        "fixtures": "https://fbref.com/en/comps/23/schedule/Eredivisie-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/23/Eredivisie-Stats"
    },
    {
        "name": "Liga Portugal", 
        "fixtures": "https://fbref.com/en/comps/32/schedule/Primeira-Liga-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/32/Primeira-Liga-Stats"
    },
    
    # 🆕 EUROPA SERIE B
    {
        "name": "Championship", 
        "fixtures": "https://fbref.com/en/comps/10/schedule/Championship-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/10/Championship-Stats"
    },
    {
        "name": "LaLiga 2", 
        "fixtures": "https://fbref.com/en/comps/17/schedule/La-Liga-2-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/17/La-Liga-2-Stats"
    },
    {
        "name": "2. Bundesliga", 
        "fixtures": "https://fbref.com/en/comps/33/schedule/2-Bundesliga-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/33/2-Bundesliga-Stats"
    },
    {
        "name": "Ligue 2", 
        "fixtures": "https://fbref.com/en/comps/60/schedule/Ligue-2-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/60/Ligue-2-Stats"
    },
    
    # 🆕 EUROPA NORDICI + EXTRA
    {
        "name": "Scottish Premiership", 
        "fixtures": "https://fbref.com/en/comps/40/schedule/Scottish-Premiership-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/40/Scottish-Premiership-Stats"
    },
    {
        "name": "Allsvenskan", 
        "fixtures": "https://fbref.com/en/comps/29/schedule/Allsvenskan-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/29/Allsvenskan-Stats"
    },
    {
        "name": "Eliteserien", 
        "fixtures": "https://fbref.com/en/comps/28/schedule/Eliteserien-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/28/Eliteserien-Stats"
    },
    {
        "name": "Superligaen", 
        "fixtures": "https://fbref.com/en/comps/50/schedule/Superligaen-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/50/Superligaen-Stats"
    },
    {
        "name": "Jupiler Pro League", 
        "fixtures": "https://fbref.com/en/comps/37/schedule/Belgian-Pro-League-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/37/Belgian-Pro-League-Stats"
    },
    {
        "name": "Süper Lig", 
        "fixtures": "https://fbref.com/en/comps/26/schedule/Super-Lig-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/26/Super-Lig-Stats"
    },
    {
        "name": "League of Ireland Premier Division", 
        "fixtures": "https://fbref.com/en/comps/80/schedule/League-of-Ireland-Premier-Division-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/80/League-of-Ireland-Premier-Division-Stats"
    },
    
    # 🆕 AMERICHE
    {
        "name": "Brasileirão Serie A", 
        "fixtures": "https://fbref.com/en/comps/24/schedule/Serie-A-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/24/Serie-A-Stats"
    },
    {
        "name": "Primera División", 
        "fixtures": "https://fbref.com/en/comps/21/schedule/Primera-Division-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/21/Primera-Division-Stats"
    },
    {
        "name": "Major League Soccer", 
        "fixtures": "https://fbref.com/en/comps/22/schedule/Major-League-Soccer-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/22/Major-League-Soccer-Stats"
    },
    
    # 🆕 ASIA
    {
        "name": "J1 League", 
        "fixtures": "https://fbref.com/en/comps/25/schedule/J1-League-Scores-and-Fixtures",
        "stats": "https://fbref.com/en/comps/25/J1-League-Stats"
    }
]

def create_scraper():
    # return cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    # --- NUOVO SISTEMA DI ACCESSO (APRISCATOLE) ---
    print("🤖 Sto aprendo l'Apriscatole...")
    return gestore_accessi_fbref.crea_scraper_intelligente()
# --- PARTE 1: SCARICA LE MEDIE (IL FAMOSO 2.77) ---
def scrape_team_stats(scraper):
    print("\n📊 PARTE 1: Aggiornamento Medie Stagionali (xG/90)...")
    
    for league in LEAGUES_CONFIG:
        league_name = league['name']
        url = league.get('stats')
        if not url: continue

        print(f"   🔍 Analizzo Classifica: {league_name}")
        try:
            time.sleep(random.uniform(3, 6))
            response = scraper.get(url)
            if response.status_code != 200: continue

            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Cerca tabella "Standard Stats"
            tables = soup.find_all('table')
            target_table = None
            for t in tables:
                if 'stats_squads_standard_for' in str(t.get('id', '')):
                    target_table = t
                    break
            if not target_table and tables: target_table = tables[0]
            if not target_table: continue

            rows = target_table.find('tbody').find_all('tr')
            count = 0

            for row in rows:
                team_cell = row.find('th', {'data-stat': 'team'})
                if not team_cell: continue
                
                team_name = team_cell.text.strip()
                
                # Estrazione dati xG e xG+xAG (Volume)
                xg_cell = row.find('td', {'data-stat': 'xg_per90'})
                xg_plus_xag_cell = row.find('td', {'data-stat': 'xg_xg_assist_per90'})
                
                # Valori default
                xg_val = float(xg_cell.text.strip()) if (xg_cell and xg_cell.text.strip()) else 1.25
                total_vol_val = float(xg_plus_xag_cell.text.strip()) if (xg_plus_xag_cell and xg_plus_xag_cell.text.strip()) else 2.5
                
                # SALVA SU MONGO (Collection stats)
                stats_collection.update_one(
                    {"team": team_name, "league": league_name},
                    {"$set": {
                        "season": "2024-2025",
                        "xg_avg": xg_val,             # Potenza Attacco
                        "total_volume_avg": total_vol_val, # Volume Totale (es. 2.77)
                        "last_updated": time.strftime("%Y-%m-%d")
                    }},
                    upsert=True
                )
                count += 1
                
            print(f"      ✅ Medie salvate per {count} squadre.")

        except Exception as e:
            print(f"      ❌ Errore stats {league_name}: {e}")

# --- PARTE 2: SCARICA I RISULTATI PARTITE (QUELLO CHE FUNZIONAVA GIÀ) ---
def scrape_match_results(scraper):
    print("\n⚽ PARTE 2: Aggiornamento Risultati Partite...")
    
    for league in LEAGUES_CONFIG:
        league_name = league['name']
        url = league.get('fixtures')
        if not url: continue
        
        print(f"\n🌍 Calendario: {league_name}")
        try:
            time.sleep(random.uniform(4, 7))
            response = scraper.get(url)
            if response.status_code != 200: continue

            soup = BeautifulSoup(response.content, 'html.parser')
            
            tables = soup.find_all('table')
            target_table = None
            for t in tables:
                if t.find('th', string=re.compile(r'Score|Risultato')):
                    target_table = t
                    break
            if not target_table and tables: target_table = tables[0]
            if not target_table: continue

            rows = target_table.find('tbody').find_all('tr')
            count = 0
            
            for row in rows:
                if 'class' in row.attrs and ('thead' in row.attrs['class'] or 'spacer' in row.attrs['class']): continue
                
                date_cell = row.find('td', {'data-stat': 'date'})
                home_cell = row.find('td', {'data-stat': 'home_team'})
                away_cell = row.find('td', {'data-stat': 'away_team'})
                score_cell = row.find('td', {'data-stat': 'score'})
                xg_home_cell = row.find('td', {'data-stat': 'home_xg'})
                xg_away_cell = row.find('td', {'data-stat': 'away_xg'})

                if not (date_cell and home_cell and away_cell and score_cell): continue
                score_text = score_cell.text.strip()
                if not score_text: continue 

                try:
                    goals = re.split(r'[–-]', score_text)
                    if len(goals) != 2: continue
                    home_goals = int(goals[0]); away_goals = int(goals[1])
                    result = '1' if home_goals > away_goals else ('2' if away_goals > home_goals else 'X')

                    match_data = {
                        "league": league_name, "date": date_cell.text.strip(),
                        "homeTeam": home_cell.text.strip(), "awayTeam": away_cell.text.strip(),
                        "homeGoals": home_goals, "awayGoals": away_goals, "result": result,
                        "xg_home": float(xg_home_cell.text.strip()) if xg_home_cell and xg_home_cell.text.strip() else None,
                        "xg_away": float(xg_away_cell.text.strip()) if xg_away_cell and xg_away_cell.text.strip() else None,
                        "source": "fbref"
                    }
                    
                    matches_collection.update_one(
                        {"unique_id": f"{match_data['date']}_{match_data['homeTeam']}_{match_data['awayTeam']}"},
                        {"$set": match_data}, upsert=True
                    )
                    count += 1
                except: continue
            print(f"      ✅ Aggiornate {count} partite.")
            
        except Exception as e: print(f"      ❌ Errore {league_name}: {e}")

def main():
    print("🚀 AVVIO DOPPIO SCRAPER...")
    scraper = create_scraper()
    
    # 1. Scarica il 2.77
    scrape_team_stats(scraper)
    
    # 2. Scarica i risultati
   # scrape_match_results(scraper)
    
    print("\n🏁 TUTTO AGGIORNATO.")

if __name__ == "__main__":
    main()
