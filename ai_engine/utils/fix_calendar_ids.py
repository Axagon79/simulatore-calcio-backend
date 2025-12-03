import sys
import os
from tqdm import tqdm
from fuzzywuzzy import process

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
root_dir = os.path.dirname(parent_dir)
sys.path.insert(0, root_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)

from config import db

def fix_calendar_teams():
    print("🔧 AVVIO RIPARAZIONE ID SQUADRE (CON ALIAS)...")

    # 1. Carichiamo Nomi E Alias
    all_teams = list(db.teams.find({}, {"name": 1, "transfermarkt_id": 1, "aliases_transfermarkt": 1}))
    
    # Creiamo una mappa potente: Nome -> ID e Alias -> ID
    team_map = {}
    all_names_list = []

    for t in all_teams:
        tid = t.get("transfermarkt_id")
        if not tid: continue
        
        # Mappa nome principale
        main_name = t["name"]
        team_map[main_name] = tid
        all_names_list.append(main_name)
        
        # Mappa alias (se esiste)
        alias = t.get("aliases_transfermarkt")
        if alias:
            team_map[alias] = tid
            all_names_list.append(alias) # Aggiungiamo anche l'alias alla lista per la ricerca fuzzy

    print(f"📚 Mappati {len(team_map)} nomi/alias verso ID.")

    rounds = list(db.h2h_by_round.find({}))
    updates_count = 0

    for r in tqdm(rounds, desc="Fixing Rounds"):
        matches = r.get("matches", [])
        modified = False
        
        for match in matches:
            # Home
            h_name = match.get("home")
            if h_name and "home_tm_id" not in match:
                # Cerca esatto (Nome o Alias)
                found_id = team_map.get(h_name)
                
                # Se non trova esatto, cerca simile (Fuzzy) tra TUTTI i nomi e alias
                if not found_id:
                    best_match, score = process.extractOne(h_name, all_names_list)
                    if score >= 85:
                        found_id = team_map.get(best_match)
                        match["home_canonical"] = best_match # Salviamo chi abbiamo trovato

                if found_id:
                    match["home_tm_id"] = found_id
                    modified = True

            # Away (stessa logica)
            a_name = match.get("away")
            if a_name and "away_tm_id" not in match:
                found_id = team_map.get(a_name)
                if not found_id:
                    best_match, score = process.extractOne(a_name, all_names_list)
                    if score >= 85:
                        found_id = team_map.get(best_match)
                        match["away_canonical"] = best_match

                if found_id:
                    match["away_tm_id"] = found_id
                    modified = True

        if modified:
            db.h2h_by_round.update_one({"_id": r["_id"]}, {"$set": {"matches": matches}})
            updates_count += 1

    print(f"✅ Finito. Aggiornate {updates_count} giornate.")

if __name__ == "__main__":
    fix_calendar_teams()
