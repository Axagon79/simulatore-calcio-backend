import requests
from bs4 import BeautifulSoup
import time
import random
from datetime import datetime
from tqdm import tqdm
import sys
import os
import re

# --- CONFIGURAZIONE ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
root_dir = os.path.dirname(parent_dir)
sys.path.insert(0, root_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)

from config import db

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def extract_team_and_pos(td_element):
    """Estrae nome e posizione (es. '(20.) Triestina' -> 'Triestina', 20)."""
    if not td_element: return None, None
    text_full = td_element.get_text(strip=True)
    
    # Cerca pattern (XX.) -> Cattura solo le cifre
    pos = None
    match = re.search(r'\((\d+)\.\)', text_full)
    if match:
        pos = int(match.group(1)) # group(1) è solo il numero, senza punto
    
    # Nome: è nel tag <a>
    link = td_element.find("a")
    name = link.get_text(strip=True) if link else text_full
    if match:
        name = name.replace(match.group(0), "").strip()
    return name, pos

def find_team_smart(name):
    """Cerca una squadra nel DB in modo intelligente."""
    t = db.teams.find_one({"name": name})
    if t: return t
    t = db.teams.find_one({"aliases_transfermarkt": name})
    if t: return t
    t = db.teams.find_one({"aliases": name})
    if t: return t
    t = db.teams.find_one({"aliases_transfermarkt": {"$regex": f"^{name}$", "$options": "i"}})
    if t: return t
    t = db.teams.find_one({"name": {"$regex": name, "$options": "i"}})
    if t: return t
    return None

def download_and_save_h2h(home_name, away_name):
    """Scarica lo storico e salva in raw_h2h_data_v2 (COLLEZIONE NUOVA DI SICUREZZA)."""
    
    home_team = find_team_smart(home_name)
    away_team = find_team_smart(away_name)

    if not home_team: return False, f"Squadra HOME non trovata: {home_name}"
    if not away_team: return False, f"Squadra AWAY non trovata: {away_name}"

    id_home = home_team.get("transfermarkt_id")
    slug_home = home_team.get("transfermarkt_slug")
    id_away = away_team.get("transfermarkt_id")

    if not id_home or not id_away: return False, "ID mancante"

    url = (
        f"https://www.transfermarkt.it/{slug_home}/bilanzdetail/verein/{id_home}"
        f"/saison_id/0/wettbewerb_id//datum_von/0000-00-00/datum_bis/0000-00-00"
        f"/gegner_id/{id_away}/day/0/plus/1"
    )

    try:
        time.sleep(random.uniform(3, 6)) 
        resp = requests.get(url, headers=HEADERS, timeout=120) 
        if resp.status_code != 200: return False, f"HTTP {resp.status_code}"

        soup = BeautifulSoup(resp.content, "html.parser")
        table = soup.find("table", class_="items")
        if not table: return False, "Tabella non trovata"
        
        rows = table.find_all("tr", class_=["odd", "even"])
        matches_history = []
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 10: continue
            
            # --- MAPPA INDICI VERIFICATA ---
            # [5]: DATA
            # [7]: SINISTRA (CASA)
            # [9]: SCORE
            # [11]: DESTRA (OSPITE)

            # A volte gli indici possono variare leggermente se ci sono celle vuote.
            # Usiamo gli indici fissi che abbiamo testato, ma con un controllo di sicurezza sulla lunghezza.
            if len(cols) < 12: 
                # Se la riga è strana (meno colonne), saltiamo o proviamo indici ridotti?
                # Meglio saltare per sicurezza.
                continue

            date_text = cols[5].get_text(strip=True)
            score_text = cols[9].get_text(strip=True)
            
            home_name_scraped, home_pos = extract_team_and_pos(cols[7])  # Casa (Sinistra)
            away_name_scraped, away_pos = extract_team_and_pos(cols[11]) # Ospite (Destra)
            
            winner = "-"
            final_score_str = score_text

            if ":" in score_text and score_text != "-:-":
                try:
                    parts = score_text.split(":")
                    score_home = int(parts[0])
                    score_away = int(parts[1])
                    
                    final_score_str = f"{score_home}:{score_away}"

                    if score_home > score_away:
                        winner = home_name_scraped
                    elif score_away > score_home:
                        winner = away_name_scraped
                    else:
                        winner = "Draw"
                except:
                    pass

            matches_history.append({
                "date": date_text,
                "score": final_score_str,
                "competition": "Unknown",
                "winner": winner,
                "home_team": home_name_scraped,
                "away_team": away_name_scraped,
                "home_pos": home_pos,
                "away_pos": away_pos
            })

        doc_id = f"{home_team['name']}_vs_{away_team['name']}"
        
        # SALVIAMO IN raw_h2h_data_v2 (Collezione Sicura)
        db.raw_h2h_data_v2.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "team_a": home_team["name"],
                    "team_b": away_team["name"],
                    "matches": matches_history,
                    "last_updated": datetime.now(),
                    "v2_ready": True 
                }
            },
            upsert=True
        )
        return True, f"Salvati {len(matches_history)} precedenti (v2)"

    except Exception as e:
        return False, str(e)

def run_mass_scraper():
    print("🚀 AVVIO SCRAPER MASSIVO H2H v2.0 (Salvataggio in raw_h2h_data_v2)")
    
    rounds = list(db.h2h_by_round.find({}))
    unique_pairs = set()

    print("📋 Analisi partite da scaricare...")
    for r in rounds:
        for m in r.get("matches", []):
            h = m.get("home_canonical", m.get("home"))
            a = m.get("away_canonical", m.get("away"))
            if h and a:
                pair = tuple(sorted([h, a]))
                unique_pairs.add(pair)
    
    pairs_list = sorted(list(unique_pairs)) 
    print(f"🎯 Trovate {len(pairs_list)} coppie uniche.")
    
    skips = 0
    for home, away in tqdm(pairs_list, desc="Download H2H"):
        # Controlliamo se esiste già nella NUOVA collezione v2
        exists = db.raw_h2h_data_v2.find_one({
            "$or": [
                {"team_a": home, "team_b": away},
                {"team_a": away, "team_b": home}
            ]
        })
        
        if exists:
            skips += 1
            continue
        
        success, msg = download_and_save_h2h(home, away)
        if not success:
            tqdm.write(f"⚠️  Skip {home}-{away}: {msg}")

    print("\n" + "="*60)
    print(f"✅ TUTTO FINITO!")
    print(f"⏩ Saltati perché già in v2: {skips}")
    print("="*60)

if __name__ == "__main__":
    run_mass_scraper()
