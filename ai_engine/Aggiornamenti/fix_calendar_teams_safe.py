import sys
import os
from tqdm import tqdm
from fuzzywuzzy import process

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grandparent_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)

try:
    from config import db
except ImportError:
    print("❌ Errore import config")
    sys.exit(1)

def fix_calendar_teams_safe():
    print("🔧 AVVIO RIPARAZIONE SQUADRE (LEAGUE AWARE MODE)...")

    # 1. Carichiamo Tutto: Nome, Alias, ID e LEGA
    all_teams = list(db.teams.find({}, {"name": 1, "transfermarkt_id": 1, "aliases_transfermarkt": 1, "league": 1}))
    
    # Mappa: Nome -> {id, league}
    team_map = {}
    # Liste separate per lega per ricerca più veloce? No, meglio filtrare dopo il match.
    all_names_list = []

    for t in all_teams:
        tid = t.get("transfermarkt_id")
        if not tid: continue
        
        league = t.get("league", "Unknown")
        
        # Mappa nome principale
        main_name = t["name"]
        team_map[main_name] = {"id": tid, "league": league}
        all_names_list.append(main_name)
        
        # Mappa alias
        alias = t.get("aliases_transfermarkt")
        if alias:
            team_map[alias] = {"id": tid, "league": league}
            all_names_list.append(alias)
            
        # Mappa alias standard (array)
        aliases_std = t.get("aliases", [])
        if isinstance(aliases_std, list):
            for a in aliases_std:
                team_map[a] = {"id": tid, "league": league}
                all_names_list.append(a)

    print(f"📚 Mappati {len(team_map)} nomi/alias. Inizio scansione...")

    rounds = list(db.h2h_by_round.find({}))
    updates_count = 0

    for r in tqdm(rounds, desc="Fixing Rounds"):
        round_league = r.get("league", "Unknown") # Es: "Liga Portugal"
        matches = r.get("matches", [])
        modified = False
        
        for match in matches:
            # --- HOME ---
            h_name = match.get("home")
            # Se manca ID o se vogliamo forzare il controllo
            if h_name and "home_tm_id" not in match:
                
                # 1. Cerca Esatto
                found_data = team_map.get(h_name)
                
                # 2. Fuzzy Match (se non esatto)
                if not found_data:
                    # Estraiamo i top 3 candidati
                    candidates = process.extract(h_name, all_names_list, limit=5)
                    
                    best_candidate = None
                    best_score = 0
                    
                    for cand_name, score in candidates:
                        if score < 85: continue # Soglia minima
                        
                        cand_data = team_map.get(cand_name)
                        cand_league = cand_data["league"]
                        
                        # IL FILTRO MAGICO:
                        # Accetta se le leghe coincidono OPPURE se una delle due è sconosciuta
                        # (Ma se round_league è "Liga Portugal" e cand_league è "Serie C", SCARTA!)
                        
                        leagues_compatible = (
                            round_league == cand_league or 
                            round_league == "Unknown" or 
                            cand_league == "Unknown" or
                            # Eccezione per le coppe europee se le gestisci
                            "Champions" in round_league or
                            "Europa" in round_league
                        )
                        
                        if leagues_compatible:
                            if score > best_score:
                                best_score = score
                                best_candidate = cand_name
                                found_data = cand_data
                        else:
                            # Debug opzionale
                            # print(f"⚠️ Scartato '{cand_name}' per '{h_name}' (Lega diversa: {cand_league} vs {round_league})")
                            pass

                    if best_candidate:
                        match["home_canonical"] = best_candidate

                # Se abbiamo trovato un ID valido (Esatto o Fuzzy-Compatible)
                if found_data:
                    match["home_tm_id"] = found_data["id"]
                    modified = True

            # --- AWAY (Identico a sopra) ---
            a_name = match.get("away")
            if a_name and "away_tm_id" not in match:
                found_data = team_map.get(a_name)
                
                if not found_data:
                    candidates = process.extract(a_name, all_names_list, limit=5)
                    best_candidate = None
                    best_score = 0
                    
                    for cand_name, score in candidates:
                        if score < 85: continue
                        cand_data = team_map.get(cand_name)
                        cand_league = cand_data["league"]
                        
                        leagues_compatible = (
                            round_league == cand_league or 
                            round_league == "Unknown" or 
                            cand_league == "Unknown" or
                            "Champions" in round_league or
                            "Europa" in round_league
                        )
                        
                        if leagues_compatible:
                            if score > best_score:
                                best_score = score
                                best_candidate = cand_name
                                found_data = cand_data
                
                if found_data:
                    match["away_tm_id"] = found_data["id"]
                    match["away_canonical"] = match.get("away_canonical", best_candidate if not team_map.get(a_name) else a_name)
                    modified = True

        if modified:
            db.h2h_by_round.update_one({"_id": r["_id"]}, {"$set": {"matches": matches}})
            updates_count += 1

    print(f"✅ Finito. Aggiornate {updates_count} giornate con controllo LEGA.")

if __name__ == "__main__":
    fix_calendar_teams_safe()
