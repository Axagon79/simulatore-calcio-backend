import os
import sys
import time
import requests  # <--- QUESTO MANCAVA O ERA SPOSTATO
from bs4 import BeautifulSoup

# --- FIX PERCORSI PER TROVARE CONFIG.PY ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

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

def scrape_unified_ranking():
    print("🚀 AVVIO SCRAPER CLASSIFICA UNIFICATO (SMART + GOL)")
    headers = {"User-Agent": "Mozilla/5.0"}

    for league in SOCCERSTATS_LEAGUES:
        print(f"\n🌍 Scarico dati per: {league['name']}...")
        try:
            resp = requests.get(league['url'], headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")

            # --- LOGICA 1: GESTIONE TABELLE SEPARATE (Serie C) ---
            # Alcune leghe su Soccerstats hanno tabelle separate per Casa e Trasferta
            if "homeaway.asp" in league['url'] or len(soup.find_all("tr")) < 50: 
                # Nota: a volte soccerstats cambia struttura, ma per ora manteniamo la logica widetable come principale
                # Se serve la logica specifica per homeaway, la inseriremo qui.
                # Per ora usiamo la logica Widetable che copre il 90% dei casi
                pass

            # --- LOGICA 2: WIDETABLE (Standard) ---
            rows = soup.find_all("tr")
            updated = 0

            for row in rows:
                cells = row.find_all("td")
                # La riga deve essere lunga abbastanza (almeno 29 celle per arrivare ai dati Away)
                if len(cells) < 29: continue
                # La prima cella deve essere un numero (la posizione in classifica)
                if not cells[0].get_text(strip=True).isdigit(): continue

                team_name = cells[1].get_text(strip=True)

                try:
                    # --- ESTRAZIONE DATI COMPLETI (Fusione v3 e v4) ---
                    
                    # CASA (Indici del v3)
                    wh = to_int(cells[13].get_text(strip=True))
                    dh = to_int(cells[14].get_text(strip=True))
                    lh = to_int(cells[15].get_text(strip=True))
                    gf_h = to_int(cells[16].get_text(strip=True)) # Gol Fatti
                    ga_h = to_int(cells[17].get_text(strip=True)) # Gol Subiti
                    gp_h = wh + dh + lh # Partite giocate
                    pts_h = (wh * 3) + dh # Punti Casa

                    # TRASFERTA (Indici del v3)
                    wa = to_int(cells[24].get_text(strip=True))
                    da = to_int(cells[25].get_text(strip=True))
                    la = to_int(cells[26].get_text(strip=True))
                    gf_a = to_int(cells[27].get_text(strip=True)) # Gol Fatti
                    ga_a = to_int(cells[28].get_text(strip=True)) # Gol Subiti
                    gp_a = wa + da + la # Partite giocate
                    pts_a = (wa * 3) + da # Punti Trasferta

                    # --- SALVATAGGIO SMART (Logica v4) ---
                    # Usiamo $or per trovare la squadra anche se il nome non è perfetto
                    filter_q = {
                        "$or": [
                            {"name": team_name},
                            {"aliases.soccerstats": team_name},
                            {"aliases": team_name}
                        ]
                    }

                    # Usiamo la DOT NOTATION per non cancellare altri dati dentro "ranking"
                    update_doc = {
                        "$set": {
                            "ranking.league": league['name'],
                            # Dati per Calcolatore Forza (dal v3)
                            "ranking.homeStats": {"played": gp_h, "goalsFor": gf_h, "goalsAgainst": ga_h},
                            "ranking.awayStats": {"played": gp_a, "goalsFor": gf_a, "goalsAgainst": ga_a},
                            # Dati Punti (dal v4)
                            "ranking.homePoints": pts_h,
                            "ranking.awayPoints": pts_a,
                            "last_updated": time.time()
                        }
                    }

                    res = teams_collection.update_one(filter_q, update_doc)
                    if res.matched_count > 0:
                        updated += 1
                    else:
                        # Se non trova nulla, prova a cercare parziale (Extrema Ratio)
                        # Attenzione: questo potrebbe fare match errati, ma lo teniamo come fallback
                        pass

                except Exception as e:
                    continue

            print(f"   ✅ Aggiornate {updated} squadre.")

        except Exception as e:
            print(f"   ❌ Errore: {e}")

if __name__ == "__main__":
    scrape_unified_ranking()