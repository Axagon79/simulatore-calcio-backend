import os
import sys
import time
import random
import re
from datetime import datetime
from bs4 import BeautifulSoup
import requests

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


COLLECTION_NAME = "h2h_by_round"
TARGET_SEASON = "2025" # Fondamentale: Puntiamo alla stagione corrente (2025/26)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

LEAGUES_TM = [
    {"name": "Serie A", "url": f"https://www.transfermarkt.it/serie-a/gesamtspielplan/wettbewerb/IT1/saison_id/{TARGET_SEASON}"},
    {"name": "Serie B", "url": f"https://www.transfermarkt.it/serie-b/gesamtspielplan/wettbewerb/IT2/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone A", "url": f"https://www.transfermarkt.it/serie-c-girone-a/gesamtspielplan/wettbewerb/IT3A/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone B", "url": f"https://www.transfermarkt.it/serie-c-girone-b/gesamtspielplan/wettbewerb/IT3B/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone C", "url": f"https://www.transfermarkt.it/serie-c-girone-c/gesamtspielplan/wettbewerb/IT3C/saison_id/{TARGET_SEASON}"},
    {"name": "Premier League", "url": f"https://www.transfermarkt.it/premier-league/gesamtspielplan/wettbewerb/GB1/saison_id/{TARGET_SEASON}"},
    {"name": "La Liga", "url": f"https://www.transfermarkt.it/laliga/gesamtspielplan/wettbewerb/ES1/saison_id/{TARGET_SEASON}"},
    {"name": "Bundesliga", "url": f"https://www.transfermarkt.it/bundesliga/gesamtspielplan/wettbewerb/L1/saison_id/{TARGET_SEASON}"},
    {"name": "Ligue 1", "url": f"https://www.transfermarkt.it/ligue-1/gesamtspielplan/wettbewerb/FR1/saison_id/{TARGET_SEASON}"},
    {"name": "Eredivisie", "url": f"https://www.transfermarkt.it/eredivisie/gesamtspielplan/wettbewerb/NL1/saison_id/{TARGET_SEASON}"},
    {"name": "Liga Portugal", "url": f"https://www.transfermarkt.it/liga-nos/gesamtspielplan/wettbewerb/PO1/saison_id/{TARGET_SEASON}"},
]

def scrape_tm_calendar_v5():
    print(f"🚀 AVVIO SCRAPER TM V5 (Smart Score Detection) - Stagione {TARGET_SEASON}")
    col = db[COLLECTION_NAME]
    
    for league in LEAGUES_TM:
        print(f"\n🌍 Lega: {league['name']}")
        try:
            time.sleep(random.uniform(4, 7))
            resp = requests.get(league['url'], headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")
            
            # 1. Trova gli Header Giornata
            # In 'Gesamtspielplan', sono 'content-box-headline'
            headers = soup.find_all("div", class_="content-box-headline")
            print(f"   Giornate trovate: {len(headers)}")
            
            saved_count = 0
            
            for header in headers:
                round_name = header.get_text(strip=True)
                if "Giornata" not in round_name and "Turno" not in round_name: continue
                
                table = header.find_next("table")
                if not table: continue
                
                matches = []
                rows = table.find_all("tr")
                
                for row in rows:
                    # Ignora righe data (colspan alto)
                    cells = row.find_all("td")
                    if len(cells) < 5: continue 
                    
                    # --- RICERCA SQUADRE ---
                    # Cerchiamo i link alle squadre
                    # Solitamente i TD hanno classe 'hauptlink' o 'no-border-links'
                    team_links = []
                    for td in cells:
                        a_tag = td.find("a")
                        if a_tag and a_tag.get("title"): 
                            # Escludiamo link che sono risultati o altro
                            if "spielbericht" in a_tag.get("href", ""): continue # Link al report partita
                            if "datum" in a_tag.get("href", ""): continue # Link alla data
                            team_links.append(a_tag.get_text(strip=True))
                    
                    # Ci aspettiamo almeno 2 squadre (Casa, Ospite)
                    # A volte trova anche i giocatori se ci sono marcatori? No, nel calendario no.
                    if len(team_links) < 2: continue
                    
                    # Prendiamo il primo e l'ultimo valido come Casa/Ospite?
                    # O usiamo le classi 'text-right' (Casa) e 'no-border-links' (Ospite)
                    
                    home = None
                    away = None
                    
                    # Casa: align right
                    home_td = row.find("td", class_="text-right")
                    if home_td: home = home_td.get_text(strip=True)
                    
                    # Ospite: no border links (ultimo)
                    # Spesso ci sono più 'no-border-links', prendiamo l'ultimo
                    no_border_tds = row.find_all("td", class_="no-border-links")
                    if no_border_tds:
                        away = no_border_tds[-1].get_text(strip=True)
                        
                    if not home or not away:
                        # Fallback sui link trovati prima
                        home = team_links[0]
                        away = team_links[-1]

                    # Pulizia nomi "(15.) Milan"
                    home = re.sub(r'\(\d+\.\)', '', home).strip()
                    away = re.sub(r'\(\d+\.\)', '', away).strip()
                    
                    # --- RICERCA RISULTATO (SMART) ---
                    score = None
                    status = "Scheduled"
                    
                    # 1. Cerca tag specifico 'ergebnis-link' (Vittoria sicura)
                    res_link = row.find("a", class_="ergebnis-link")
                    if res_link:
                        txt = res_link.get_text(strip=True)
                        if ":" in txt:
                            score = txt
                            status = "Finished"
                    
                    # 2. Se non trova link, cerca pattern "d:d" in qualsiasi cella
                    if not score:
                        for td in cells:
                            txt = td.get_text(strip=True)
                            # Regex per "1:0", "2:2", "10:1"
                            # Evita orari "15:00" (che TM formatta spesso come HH:MM)
                            # TM Risultati: Spesso grassetto o linkati.
                            # Se troviamo "2:1", assumiamo risultato.
                            # Se troviamo "15:00", assumiamo orario.
                            if re.match(r'^\d{1,2}:\d{1,2}$', txt):
                                # Distinguiamo orario da punteggio?
                                # Punteggi > 5 gol rari, orari > 12:00 comuni.
                                # Ma anche 1:0 è orario (di notte)? No.
                                # Se è linkato è risultato. Se è testo semplice...
                                # In 'Gesamtspielplan', i risultati sono QUASI SEMPRE linkati.
                                # Se è testo semplice, è orario.
                                pass 

                    # Se abbiamo trovato score
                    if score:
                        # Check rinvio
                        if "annull" in score.lower() or "post" in score.lower():
                            status = "Postponed"
                            score = None
                    
                    matches.append({
                        "home": home, 
                        "away": away, 
                        "status": status, 
                        "real_score": score,
                        "h2h_data": None
                    })

                if matches:
                    save_round(col, league['name'], round_name, matches)
                    saved_count += 1
            
            print(f"   ✅ Salvate {saved_count} giornate.")

        except Exception as e:
            print(f"   ❌ Errore: {e}")

def save_round(col, league, round_name, matches):
    safe_round = round_name.replace(".", "").replace(" ", "")
    safe_league = league.replace(" ", "")
    doc_id = f"{safe_league}_{safe_round}"
    
    col.update_one({"_id": doc_id}, {
        "$set": {
            "league": league, "round_name": round_name, "season": TARGET_SEASON,
            "matches": matches, "last_updated": datetime.now()
        }
    }, upsert=True)

if __name__ == "__main__":
    scrape_tm_calendar_v5()