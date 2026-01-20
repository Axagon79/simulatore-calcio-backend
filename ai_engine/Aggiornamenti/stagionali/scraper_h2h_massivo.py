import requests
from bs4 import BeautifulSoup
import time
import random
from datetime import datetime
from tqdm import tqdm
import sys
import os
import re
from colorama import Fore, Style, init
from concurrent.futures import ThreadPoolExecutor, as_completed

init(autoreset=True)

# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

# --- CACHE GLOBALE TEAM ---
print(f"{Fore.YELLOW}🧠 Caricamento cache squadre...")
all_teams = list(db.teams.find())
TEAM_CACHE_BY_ID = {t.get("transfermarkt_id"): t for t in all_teams if t.get("transfermarkt_id")}
TEAM_CACHE_BY_NAME = {t.get("name").lower(): t for t in all_teams}

for t in all_teams:
    for field in ["aliases_transfermarkt", "aliases"]:
        val = t.get(field, [])
        if isinstance(val, list):
            for a in val: TEAM_CACHE_BY_NAME[a.lower()] = t
        elif isinstance(val, str):
            TEAM_CACHE_BY_NAME[val.lower()] = t

def extract_team_and_pos(td_element):
    if not td_element: return None, None
    text_full = td_element.get_text(strip=True)
    pos = None
    match = re.search(r'\((\d+)\.\)', text_full)
    if match: pos = int(match.group(1))
    link = td_element.find("a")
    name = link.get_text(strip=True) if link else text_full
    if match: name = name.replace(match.group(0), "").strip()
    return name, pos

def find_team_optimized(tm_id, name):
    if tm_id and int(tm_id) in TEAM_CACHE_BY_ID: return TEAM_CACHE_BY_ID[int(tm_id)]
    return TEAM_CACHE_BY_NAME.get(name.lower() if name else "")

def download_and_save_h2h(match_data):
    """Unità di lavoro per ThreadPoolExecutor"""
    home_id = match_data.get("home_tm_id")
    away_id = match_data.get("away_tm_id")
    home_team = find_team_optimized(home_id, match_data.get("home"))
    away_team = find_team_optimized(away_id, match_data.get("away"))

    if not home_team or not away_team: return False
    
    id_h, id_a = home_team["transfermarkt_id"], away_team["transfermarkt_id"]
    slug_h = home_team["transfermarkt_slug"]
    
    url = f"https://www.transfermarkt.it/{slug_h}/bilanzdetail/verein/{id_h}/saison_id/0/wettbewerb_id//datum_von/0000-00-00/datum_bis/0000-00-00/gegner_id/{id_a}/day/0/plus/1"
    
    try:
        # Pausa tra i thread per simulare comportamento umano
        time.sleep(random.uniform(1.2, 2.5)) 
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200: return False
        
        soup = BeautifulSoup(resp.content, "html.parser")
        table = soup.find("table", class_="items")
        if not table: return False
        
        matches_history = []
        for row in table.find_all("tr", class_=["odd", "even"]):
            cols = row.find_all("td")
            if len(cols) < 12: continue
            score = cols[9].get_text(strip=True)
            h_n, h_p = extract_team_and_pos(cols[7])
            a_n, a_p = extract_team_and_pos(cols[11])
            
            winner = "Draw"
            if ":" in score and score != "-:-":
                try:
                    s1, s2 = map(int, score.split(":"))
                    if s1 > s2: winner = h_n
                    elif s2 > s1: winner = a_n
                except: pass

            matches_history.append({
                "date": cols[5].get_text(strip=True), "score": score,
                "winner": winner, "home_team": h_n, "away_team": a_n,
                "home_pos": h_p, "away_pos": a_p
            })
        
        db.raw_h2h_data_v2.update_one(
            {"_id": f"{home_team['name']}_vs_{away_team['name']}"},
            {"$set": {
                "team_a": home_team["name"], "team_b": away_team["name"],
                "tm_id_a": id_h, "tm_id_b": id_a,
                "matches": matches_history, "last_updated": datetime.now(), "v2_ready": True
            }}, upsert=True
        )
        return True
    except: return False

def run_mass_scraper():
    # 1. Recupero Leghe e Menu
    all_leagues = sorted(db.h2h_by_round.distinct("league"))
    print("\n" + "="*60)
    print(f"{Fore.CYAN}🚀 TURBO SCRAPER H2H MULTI-THREAD")
    print("="*60)
    for i, l in enumerate(all_leagues, 1):
        print(f"   {i:2d}. {l}")
    print(f"   {len(all_leagues) + 1:2d}. 🔥 TUTTI I CAMPIONATI")
    print("="*60)
    
    choice = input(f"\n🎯 Scelta (es: 1 o 1,2,5 o {len(all_leagues)+1}): ").strip()
    if not choice: return

    # Logica selezione multipla o Tutti
    if choice == str(len(all_leagues) + 1):
        selected_leagues = all_leagues
    else:
        try:
            indices = [int(x.strip()) - 1 for x in choice.split(",") if x.strip().isdigit()]
            selected_leagues = [all_leagues[i] for i in indices if 0 <= i < len(all_leagues)]
        except:
            print(f"{Fore.RED}❌ Scelta non valida."); return

    # 2. Cache ID esistenti per evitare download inutili
    print(f"\n{Fore.YELLOW}🧠 Controllo match già presenti nel DB...")
    existing_pairs = set()
    for doc in db.raw_h2h_data_v2.find({}, {"tm_id_a": 1, "tm_id_b": 1}):
        if "tm_id_a" in doc and "tm_id_b" in doc:
            existing_pairs.add(tuple(sorted([int(doc["tm_id_a"]), int(doc["tm_id_b"])])))
    
    # 3. Analisi Match da scaricare
    pairs_to_process = {}
    print(f"🔍 Analisi {len(selected_leagues)} campionati in corso...")
    
    for r in db.h2h_by_round.find({"league": {"$in": selected_leagues}}):
        for m in r.get("matches", []):
            id_h, id_a = m.get("home_tm_id"), m.get("away_tm_id")
            if id_h and id_a:
                pk = tuple(sorted([int(id_h), int(id_a)]))
                if pk not in existing_pairs and pk not in pairs_to_process:
                    pairs_to_process[pk] = m

    if not pairs_to_process:
        print(f"{Fore.GREEN}✅ Database già aggiornato per i campionati selezionati."); return

    print(f"🎯 Nuove coppie trovate: {len(pairs_to_process)}")
    print(f"🚀 Avvio download parallelo (3 Thread)...\n")
    
    # 4. CORE MULTI-THREAD
    with ThreadPoolExecutor(max_workers=3) as executor:
        # Creazione dei compiti
        futures = {executor.submit(download_and_save_h2h, m): m for m in pairs_to_process.values()}
        
        # tqdm gestisce la barra di progresso in tempo reale
        for _ in tqdm(as_completed(futures), total=len(futures), desc="Scraping in corso"):
            pass

    print(f"\n{Fore.CYAN}🏁 Operazione completata!")

if __name__ == "__main__":
    run_mass_scraper()