import os
import sys
import cloudscraper
from bs4 import BeautifulSoup
import time
import random
from datetime import datetime
import pymongo # Aggiunto import mancante

# --- FIX PERCORSI ---
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


fixtures_collection = db['fixtures']

# LISTA URL ODDSMATH
ODDSMATH_URLS = [
    {"name": "Serie A", "url": "https://www.oddsmath.com/football/italy/serie-a-1315/"},
    {"name": "Serie B", "url": "https://www.oddsmath.com/football/italy/serie-b-1317/"},
    {"name": "Serie C (Lega Pro)", "url": "https://www.oddsmath.com/football/italy/lega-pro-7464/"},
    {"name": "Premier League", "url": "https://www.oddsmath.com/football/england/premier-league-1281/"},
    {"name": "La Liga", "url": "https://www.oddsmath.com/football/spain/laliga-1122/"},
    {"name": "Bundesliga", "url": "https://www.oddsmath.com/football/germany/bundesliga-1219/"},
    {"name": "Ligue 1", "url": "https://www.oddsmath.com/football/france/ligue-1-1083/"},
    {"name": "Eredivisie", "url": "https://www.oddsmath.com/football/netherlands/eredivisie-2016/"},
    {"name": "Liga Portugal", "url": "https://www.oddsmath.com/football/portugal/primeira-liga-1142/"}
]

def scrape_oddsmath():
    print("💰 AVVIO SCRAPER ODDSMATH (FIXED & CONNECTED)...")
    
    # Cloudscraper setup
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    
    total_found = 0

    for league in ODDSMATH_URLS:
        print(f"\n🌍 {league['name']}")
        try:
            time.sleep(random.uniform(3, 6))
            resp = scraper.get(league['url'])
            
            if resp.status_code != 200:
                print(f"   ❌ Errore HTTP {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.content, 'html.parser')
            
            # Cerca tabella quote
            tables = soup.find_all('table')
            target_table = None
            
            # Logica euristica per trovare la tabella giusta
            for t in tables:
                if t.find('td', text='1') or "odds" in str(t) or len(t.find_all('tr')) > 10:
                    target_table = t
                    break
            if not target_table and tables: target_table = tables[0]

            if not target_table:
                print("   ❌ Nessuna tabella trovata.")
                continue

            rows = target_table.find_all('tr')
            league_count = 0
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 8: continue 
                
                try:
                    # Estrazione Nomi Squadre
                    text_cols = [c.get_text(strip=True) for c in cols]
                    
                    # Cerca indice Home Team (stringa lunga non numerica)
                    home_idx = -1
                    for i, txt in enumerate(text_cols):
                        if len(txt) > 3 and not txt[0].isdigit() and ":" not in txt:
                            # Verifica che non sia una data o orario
                            home_idx = i
                            break
                    
                    if home_idx == -1: continue
                    
                    home_team = text_cols[home_idx]
                    # Away è solitamente 2 colonne dopo (c'è il "-")
                    if home_idx + 2 < len(text_cols):
                        away_team = text_cols[home_idx+2]
                    else: continue

                    # Estrazione Quote (ignorando colonna BN)
                    odds_vals = []
                    
                    # Guardiamo le colonne successive ai nomi
                    for txt in text_cols[home_idx+3:]:
                        try:
                            val = float(txt)
                            if 1.01 <= val <= 30.0:
                                odds_vals.append(val)
                        except:
                            pass
                    
                    # Logica FIX colonne:
                    if len(odds_vals) >= 4:
                         if odds_vals[0].is_integer() and odds_vals[0] > 3 and odds_vals[1] < 4.0:
                            odds_vals.pop(0) # Rimuovi BN (Bookmaker Number)
                    elif len(odds_vals) == 3:
                        # Se ne abbiamo solo 3, e il primo sembra un ID bookmaker
                        if odds_vals[0].is_integer() and odds_vals[0] > 3 and odds_vals[1] < 4.0:
                             # Rischio: se scartiamo il primo, ne restano 2 -> Troppe poche.
                             pass 

                    if len(odds_vals) >= 3:
                        q1, qx, q2 = odds_vals[0], odds_vals[1], odds_vals[2]
                        
                        # Aggiorna DB
                        # Usa regex per trovare la squadra (es. "Juventus" in "Juventus FC")
                        res = fixtures_collection.update_one(
                            {"homeTeam": {"$regex": f"^{home_team[:5]}", "$options": "i"}},
                            {
                                "$set": {
                                    "odds": {"1": q1, "X": qx, "2": q2, "source": "oddsmath_fixed", "lastUpdated": datetime.now()}
                                }
                            }
                        )
                        if res.modified_count > 0:
                            league_count += 1
                            
                except Exception:
                    continue
            
            print(f"   ✅ Aggiornate quote per {league_count} partite.")
            total_found += league_count

        except Exception as e:
            print(f"   ⚠️ Errore durante scraping lega: {e}")
            continue

    print(f"\n🏁 FINITO. Totale quote salvate: {total_found}")

if __name__ == "__main__":
    scrape_oddsmath()