import requests
from bs4 import BeautifulSoup
import time
import random
from datetime import datetime
from tqdm import tqdm
import sys
import os

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

def find_team_smart(name):
    """
    Cerca una squadra nel DB in modo intelligente:
    1. Nome esatto
    2. Alias esatto (Transfermarkt)
    3. Alias esatto (Campo 'aliases' standard)
    4. Alias parziale
    5. Nome parziale
    """
    # 1. Cerca per Nome Esatto
    t = db.teams.find_one({"name": name})
    if t: return t

    # 2. Cerca per Alias Transfermarkt Esatto
    t = db.teams.find_one({"aliases_transfermarkt": name})
    if t: return t

    # 3. Cerca per Alias Standard (quello dove c'è scritto "Bor. M'gladbach")
    t = db.teams.find_one({"aliases": name})
    if t: return t
    
    # 4. Cerca per Alias (Contiene il nome - Case Insensitive)
    t = db.teams.find_one({"aliases_transfermarkt": {"$regex": f"^{name}$", "$options": "i"}})
    if t: return t

    # 5. Cerca nel campo 'name' con regex parziale
    # Usiamo ^ per dire "inizia con" per evitare falsi positivi strani
    t = db.teams.find_one({"name": {"$regex": name, "$options": "i"}})
    if t: return t
    
    return None

def download_and_save_h2h(home_name, away_name):
    """Scarica lo storico tra due squadre e lo salva nel DB."""
    
    # USIAMO LA FUNZIONE INTELLIGENTE ORA
    home_team = find_team_smart(home_name)
    away_team = find_team_smart(away_name)

    if not home_team:
        return False, f"Squadra HOME non trovata nel DB (neanche con smart search): {home_name}"
    if not away_team:
        return False, f"Squadra AWAY non trovata nel DB (neanche con smart search): {away_name}"

    id_home = home_team.get("transfermarkt_id")
    slug_home = home_team.get("transfermarkt_slug")
    id_away = away_team.get("transfermarkt_id")

    if not id_home or not id_away:
        return False, "ID Transfermarkt mancante nel documento squadra"

    # Costruisci URL
    url = (
        f"https://www.transfermarkt.it/{slug_home}/bilanzdetail/verein/{id_home}"
        f"/saison_id/0/wettbewerb_id//datum_von/0000-00-00/datum_bis/0000-00-00"
        f"/gegner_id/{id_away}/day/0/plus/1"
    )

    try:
        time.sleep(random.uniform(3, 6)) # Delay anti-ban
        
        # Timeout aumentato a 120s per la notte
        resp = requests.get(url, headers=HEADERS, timeout=120) 
        if resp.status_code != 200:
            return False, f"HTTP Error {resp.status_code}"

        soup = BeautifulSoup(resp.content, "html.parser")
        rows = soup.select("table.items tbody tr")

        matches_history = []
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 10: continue
            
            date_text = cols[5].get_text(strip=True)
            result_text = cols[9].get_text(strip=True)
            competition = cols[4].get('title', 'Unknown') if cols[4].find('img') else 'Unknown'
            
            if ":" in result_text and result_text != "-:-":
                parts = result_text.split(":")
                try:
                    score_h = int(parts[0])
                    score_a = int(parts[1])
                    
                    host_raw = cols[7].get_text(strip=True)
                    
                    # Confronto chi era in casa usando i nomi ufficiali del DB
                    db_home_name = home_team["name"]
                    is_home_host = db_home_name.lower() in host_raw.lower()
                    
                    winner = "Draw"
                    if score_h > score_a:
                        winner = db_home_name if is_home_host else away_team["name"]
                    elif score_a > score_h:
                        winner = away_team["name"] if is_home_host else db_home_name
                        
                    matches_history.append({
                        "date": date_text,
                        "score": result_text,
                        "competition": competition,
                        "winner": winner
                    })
                except:
                    continue

        # Salva usando i NOMI UFFICIALI DEL DB come ID (così è pulito)
        doc_id = f"{home_team['name']}_vs_{away_team['name']}"
        db.raw_h2h_data.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "team_a": home_team["name"],
                    "team_b": away_team["name"],
                    "matches": matches_history,
                    "last_updated": datetime.now()
                }
            },
            upsert=True
        )
        return True, f"Salvati {len(matches_history)} precedenti"

    except Exception as e:
        return False, str(e)

def run_mass_scraper():
    print("🚀 AVVIO SCRAPER MASSIVO H2H - VERSIONE INTELLIGENTE (SMART + ALIAS + STANDARD)")
    
    rounds = list(db.h2h_by_round.find({}))
    unique_pairs = set()

    print("📋 Analisi partite da scaricare...")
    for r in rounds:
        for m in r.get("matches", []):
            # Prendi il nome migliore disponibile
            h = m.get("home_canonical", m.get("home"))
            a = m.get("away_canonical", m.get("away"))
            
            if h and a:
                pair = tuple(sorted([h, a]))
                unique_pairs.add(pair)
    
    # Ordinamento Alfabetico per Resume sicuro
    pairs_list = sorted(list(unique_pairs)) 
    
    print(f"🎯 Trovate {len(pairs_list)} coppie uniche.")
    print("   (La lista è ordinata alfabeticamente per permettere il resume)")
    
    skips = 0
    
    for home, away in tqdm(pairs_list, desc="Download H2H"):
        # Controlla se esiste già
        exists = db.raw_h2h_data.find_one({
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
    print(f"⏩ Totale saltate perché già presenti: {skips}")
    print("="*60)

if __name__ == "__main__":
    run_mass_scraper()
