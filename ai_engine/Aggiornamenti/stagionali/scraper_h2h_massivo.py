import requests
from bs4 import BeautifulSoup
import time
import random
from datetime import datetime
from tqdm import tqdm
import sys
import os
import re

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

def extract_team_and_pos(td_element):
    """Estrae nome e posizione (es. '(20.) Triestina' -> 'Triestina', 20)."""
    if not td_element: return None, None
    text_full = td_element.get_text(strip=True)
    pos = None
    match = re.search(r'\((\d+)\.\)', text_full)
    if match:
        pos = int(match.group(1))
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
    """Scarica lo storico e salva in raw_h2h_data_v2."""
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
        resp = requests.get(url, headers=HEADERS, timeout=60)
        if resp.status_code != 200: return False, f"HTTP {resp.status_code}"
        
        soup = BeautifulSoup(resp.content, "html.parser")
        table = soup.find("table", class_="items")
        if not table: return False, "Tabella non trovata"
        
        rows = table.find_all("tr", class_=["odd", "even"])
        matches_history = []
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 12: continue
            
            date_text = cols[5].get_text(strip=True)
            score_text = cols[9].get_text(strip=True)
            home_name_scraped, home_pos = extract_team_and_pos(cols[7])
            away_name_scraped, away_pos = extract_team_and_pos(cols[11])
            
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

def show_menu():
    """Mostra il menu per scegliere i campionati."""
    print("="*80)
    print("🚀 SCRAPER H2H v2.0 - MENU INTERATTIVO")
    print("="*80)
    print()
    
    # Trova tutti i campionati disponibili nel database
    all_leagues = sorted(db.h2h_by_round.distinct("league"))
    
    print("📊 CAMPIONATI DISPONIBILI:\n")
    
    for i, league in enumerate(all_leagues, 1):
        # Conta le giornate per campionato
        rounds_count = db.h2h_by_round.count_documents({"league": league})
        print(f"   {i:2d}. {league:45s} ({rounds_count} giornate)")
    
    print()
    print(f"   {len(all_leagues) + 1:2d}. 🌍 TUTTI I CAMPIONATI")
    print()
    print("="*80)
    print()
    
    while True:
        choice = input("🎯 Scegli un'opzione (numero o numeri separati da virgola, es: 1,3,5): ").strip()
        
        if not choice:
            print("❌ Devi inserire almeno un numero!")
            continue
        
        # Parsing della scelta
        try:
            if "," in choice:
                # Selezione multipla: 1,3,5
                indices = [int(x.strip()) for x in choice.split(",")]
            else:
                # Selezione singola
                indices = [int(choice)]
            
            # Verifica range
            if any(idx < 1 or idx > len(all_leagues) + 1 for idx in indices):
                print(f"❌ Numero non valido! Scegli tra 1 e {len(all_leagues) + 1}")
                continue
            
            # Opzione "TUTTI"
            if (len(all_leagues) + 1) in indices:
                selected_leagues = all_leagues
                print(f"\n✅ Selezionati TUTTI i {len(all_leagues)} campionati")
            else:
                selected_leagues = [all_leagues[idx - 1] for idx in indices]
                print(f"\n✅ Selezionati {len(selected_leagues)} campionati:")
                for league in selected_leagues:
                    print(f"   • {league}")
            
            print()
            confirm = input("⏸️  Confermi? (s/n): ").strip().lower()
            
            if confirm == 's':
                return selected_leagues
            else:
                print("\n🔄 Riprova...\n")
                continue
                
        except ValueError:
            print("❌ Formato non valido! Usa numeri separati da virgola (es: 1,3,5)")
            continue

def run_mass_scraper():
    # Mostra menu e ottieni selezione
    selected_leagues = show_menu()
    
    print()
    print("="*80)
    print(f"🎯 Campionati selezionati: {len(selected_leagues)}")
    print("="*80)
    print()
    
    # Filtra solo i round dei campionati selezionati
    rounds = list(db.h2h_by_round.find({"league": {"$in": selected_leagues}}))
    
    unique_pairs = set()
    
    print("📋 Analisi partite da scaricare...")
    
    for r in rounds:
        league = r.get("league")
        for m in r.get("matches", []):
            h = m.get("home_canonical", m.get("home"))
            a = m.get("away_canonical", m.get("away"))
            if h and a:
                pair = tuple(sorted([h, a]))
                unique_pairs.add((pair, league))
    
    pairs_list = sorted(list(unique_pairs))
    
    print(f"🎯 Trovate {len(pairs_list)} coppie uniche.\n")
    
    # Statistiche per campionato
    by_league = {}
    for (pair, league) in pairs_list:
        by_league[league] = by_league.get(league, 0) + 1
    
    print("📊 Distribuzione per campionato:")
    for league in selected_leagues:
        count = by_league.get(league, 0)
        print(f"   • {league:45s} → {count:3d} coppie")
    
    print()
    input("⏸️  Premi INVIO per iniziare il download...")
    print()
    
    skips = 0
    downloaded = 0
    errors = 0
    
    with tqdm(pairs_list, desc="Download H2H") as pbar:
        for (home_raw, away_raw), league in pbar:
            # Trova i team ufficiali
            home_team = find_team_smart(home_raw)
            away_team = find_team_smart(away_raw)
            
            if not home_team or not away_team:
                errors += 1
                pbar.set_postfix_str(f"⚠️ Skip: Squadre non trovate ({home_raw}/{away_raw})")
                continue
            
            home_official = home_team['name']
            away_official = away_team['name']
            
            # Controlla se esiste
            exists = db.raw_h2h_data_v2.find_one({
                "$or": [
                    {"team_a": home_official, "team_b": away_official},
                    {"team_a": away_official, "team_b": home_official}
                ]
            })
            
            if exists:
                skips += 1
                pbar.set_postfix_str(f"⏩ {skips} skip | ✅ {downloaded} OK | ❌ {errors} err")
                continue
            
            # Scarica
            pbar.set_postfix_str(f"📥 {league[:20]}: {home_official[:15]}-{away_official[:15]}")
            success, msg = download_and_save_h2h(home_raw, away_raw)
            
            if success:
                downloaded += 1
            else:
                errors += 1
    
    print()
    print("="*80)
    print("✅ COMPLETATO!")
    print("="*80)
    print(f"   ✅ Scaricati:           {downloaded}")
    print(f"   ⏩ Già presenti:        {skips}")
    print(f"   ❌ Errori:              {errors}")
    print(f"   📊 Totale processati:   {len(pairs_list)}")
    print("="*80)

if __name__ == "__main__":
    run_mass_scraper()