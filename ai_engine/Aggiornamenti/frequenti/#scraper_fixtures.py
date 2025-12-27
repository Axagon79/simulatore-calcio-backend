import os
import sys
import os
import sys

# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db


import cloudscraper
import requests
from bs4 import BeautifulSoup
import os
import time
import random
from datetime import datetime
from dotenv import load_dotenv

# 1. CONFIGURAZIONE
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', '.env')
load_dotenv(env_path)

MONGO_URI = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
fixtures_collection = db['fixtures']

# Pulizia: Rimuoviamo TUTTO il calendario per riscaricarlo fresco
# (In produzione potremmo fare un aggiornamento delta, ma ora è più sicuro pulire)
fixtures_collection.delete_many({})
print("🗑️  Calendario pulito. Inizio download...")

# --- A. FBREF (BIG LEAGUES) ---
FBREF_URLS = [
    {"name": "Serie A", "url": "https://fbref.com/en/comps/11/schedule/Serie-A-Scores-and-Fixtures"},
    {"name": "Serie B", "url": "https://fbref.com/en/comps/18/schedule/Serie-B-Scores-and-Fixtures"},
    {"name": "Premier League", "url": "https://fbref.com/en/comps/9/schedule/Premier-League-Scores-and-Fixtures"},
    {"name": "La Liga", "url": "https://fbref.com/en/comps/12/schedule/La-Liga-Scores-and-Fixtures"},
    {"name": "Bundesliga", "url": "https://fbref.com/en/comps/20/schedule/Bundesliga-Scores-and-Fixtures"},
    {"name": "Ligue 1", "url": "https://fbref.com/en/comps/13/schedule/Ligue-1-Scores-and-Fixtures"},
    {"name": "Eredivisie", "url": "https://fbref.com/en/comps/23/schedule/Eredivisie-Scores-and-Fixtures"},
    {"name": "Liga Portugal", "url": "https://fbref.com/en/comps/32/schedule/Primeira-Liga-Scores-and-Fixtures"}
]

def scrape_fbref_fixtures():
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    
    for league in FBREF_URLS:
        print(f"\n🌍 [FBRef] Scarico: {league['name']}")
        try:
            time.sleep(random.uniform(3, 6))
            resp = scraper.get(league['url'])
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            # Cerca tabella Scores & Fixtures
            target_table = None
            tables = soup.find_all('table')
            for t in tables:
                if "score" in str(t) or "Fixtures" in str(t): # Euristica semplice
                    target_table = t
                    break
            if not target_table and tables: target_table = tables[0]

            if not target_table: continue

            rows = target_table.find('tbody').find_all('tr')
            count = 0
            
            for row in rows:
                # Ignora righe intestazione o vuote
                if 'class' in row.attrs and 'thead' in row.attrs['class']: continue
                
                # Se ha un punteggio (cella non vuota), è PASSATA -> Ignoriamo?
                # No, salviamo solo le FUTURE (dove score è vuoto o c'è orario)
                score_cell = row.find('td', {'data-stat': 'score'})
                
                is_future = False
                if score_cell:
                    score_text = score_cell.text.strip()
                    if score_text == "": 
                        is_future = True
                
                if not is_future: continue

                date_cell = row.find('td', {'data-stat': 'date'})
                home_cell = row.find('td', {'data-stat': 'home_team'})
                away_cell = row.find('td', {'data-stat': 'away_team'})

                if not (date_cell and home_cell and away_cell): continue

                fixture = {
                    "league": league['name'],
                    "date": date_cell.text.strip(),
                    "homeTeam": home_cell.text.strip(),
                    "awayTeam": away_cell.text.strip(),
                    "status": "Scheduled",
                    "source": "fbref"
                }
                fixtures_collection.insert_one(fixture)
                count += 1
            
            print(f"   ✅ Aggiunte {count} partite future.")

        except Exception as e:
            print(f"   ❌ Errore {league['name']}: {e}")

# --- B. SOCCERSTATS (SERIE C & PORTUGAL IF NEEDED) ---
# Usiamo il link "bydate" che mi hai dato tu
SOCCERSTATS_URLS = [
    {"name": "Serie C - Girone A", "url": "https://www.soccerstats.com/results.asp?league=italy3&pmtype=bydate"},
    {"name": "Serie C - Girone B", "url": "https://www.soccerstats.com/results.asp?league=italy4&pmtype=bydate"},
    {"name": "Serie C - Girone C", "url": "https://www.soccerstats.com/results.asp?league=italy5&pmtype=bydate"}
]

def scrape_soccerstats_fixtures():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for league in SOCCERSTATS_URLS:
        print(f"\n🌍 [SoccerStats] Scarico: {league['name']}")
        try:
            time.sleep(random.uniform(3, 6))
            resp = requests.get(league['url'], headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            # SoccerStats "bydate" è una tabella semplice.
            # Le righe future non hanno il risultato (cella vuota o "-")
            
            table = soup.find('table', id='btable') # Spesso id='btable'
            if not table:
                tables = soup.find_all('table')
                # Cerchiamo una tabella lunga
                for t in tables:
                    if len(t.find_all('tr')) > 20: 
                        table = t
                        break
            
            if not table: 
                print("   ❌ Tabella non trovata.")
                continue

            rows = table.find_all('tr')
            count = 0
            current_date = "Unknown"
            
            for row in rows:
                cells = row.find_all('td')
                if not cells: 
                    # A volte la data è in una riga header (th o td con colspan)
                    # Su SoccerStats bydate la data è spesso nella prima colonna
                    continue
                
                # Analisi celle
                # SoccerStats bydate format: Date | Home | Result | Away | Stats
                if len(cells) >= 4:
                    date_text = cells[0].get_text(strip=True)
                    home_text = cells[1].get_text(strip=True)
                    score_text = cells[2].get_text(strip=True)
                    away_text = cells[3].get_text(strip=True)
                    
                    # Gestione data (spesso è solo "24 Oct" o vuota se è lo stesso giorno)
                    if date_text and len(date_text) > 2:
                        current_date = date_text # Aggiorna data corrente
                    
                    # È futura? Se score_text è "-" o vuoto o contiene ":" (orario)
                    is_future = False
                    if "-" in score_text and not any(c.isdigit() for c in score_text.replace("-","")): # Solo trattino
                        is_future = True
                    elif ":" in score_text: # Orario es "14:30"
                        is_future = True
                    elif score_text == "" or score_text == "?":
                        is_future = True
                        
                    # Se c'è un numero tipo "1-0", non è futura.
                    if any(char.isdigit() for char in score_text) and ":" not in score_text:
                        is_future = False

                    if is_future and home_text and away_text:
                        fixture = {
                            "league": league['name'],
                            "date": current_date, # Nota: Manca l'anno, andrà gestito poi
                            "homeTeam": home_text,
                            "awayTeam": away_text,
                            "status": "Scheduled",
                            "source": "soccerstats"
                        }
                        fixtures_collection.insert_one(fixture)
                        count += 1

            print(f"   ✅ Aggiunte {count} partite future (Serie C).")

        except Exception as e:
            print(f"   ❌ Errore {league['name']}: {e}")

if __name__ == "__main__":
    scrape_fbref_fixtures()      # Big Leagues
    scrape_soccerstats_fixtures() # Serie C
    print("\n🏁 CALENDARIO COMPLETATO.")