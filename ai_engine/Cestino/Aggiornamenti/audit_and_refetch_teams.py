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

def are_leagues_compatible(round_league, team_league):
    """
    Verifica se la lega della giornata e la lega della squadra sono compatibili.
    Ritorna True se va bene, False se c'è un errore palese.
    """
    if not team_league: return True # Nel dubbio, tieni buono
    
    rl = round_league.lower()
    tl = team_league.lower()
    
    # 1. Se sono identiche o contenute
    if rl in tl or tl in rl: return True
    
    # 2. Gestione Coppe (Qui le squadre di leghe diverse si incrociano!)
    # Se la giornata è una coppa, NON DOBBIAMO TOCCARE NULLA.
    keywords_cup = ["cup", "coppa", "pokal", "champions", "europa", "conference", "playoff", "play-off"]
    if any(k in rl for k in keywords_cup):
        return True
        
    # 3. Controllo specifico per il tuo caso Bra/Braga
    # Liga Portugal vs Serie C -> FALSE
    return False

def find_correct_team_strict_league(team_name, target_league, all_names_list, team_map):
    """
    Cerca il nome squadra usando FuzzyWuzzy MA accetta SOLO candidati della target_league.
    """
    candidates = process.extract(team_name, all_names_list, limit=10)
    
    best_candidate = None
    best_score = 0
    
    for cand_name, score in candidates:
        # Soglia minima (es. 70 per prendere "SC Braga" da "Braga")
        if score < 70: continue 
        
        cand_data = team_map.get(cand_name)
        cand_league = cand_data.get("league", "Unknown")
        
        # IL FILTRO DI FERRO: Deve essere della stessa lega!
        if are_leagues_compatible(target_league, cand_league):
            if score > best_score:
                best_score = score
                best_candidate = cand_data
                
    return best_candidate

def audit_and_fix():
    print("👮‍♂️ AVVIO AUDIT E FIX: CONTROLLO COERENZA LEGHE...")

    # 1. CARICAMENTO DATI SQUADRE
    all_teams = list(db.teams.find({}, {"name": 1, "transfermarkt_id": 1, "aliases_transfermarkt": 1, "league": 1, "aliases": 1}))
    
    # Mappa ID -> Dati Squadra (Per verificare chi c'è ora)
    id_to_data = {}
    
    # Mappa Nome -> Dati Squadra (Per cercare il sostituto)
    name_to_data = {}
    all_names_list = []

    for t in all_teams:
        tid = t.get("transfermarkt_id")
        if not tid: continue
        
        ldata = {"id": tid, "league": t.get("league", "Unknown"), "name": t["name"]}
        id_to_data[tid] = ldata
        
        # Popola mappa ricerca
        name_to_data[t["name"]] = ldata
        all_names_list.append(t["name"])
        
        if t.get("aliases_transfermarkt"):
            name_to_data[t["aliases_transfermarkt"]] = ldata
            all_names_list.append(t["aliases_transfermarkt"])
            
        for a in t.get("aliases", []):
            name_to_data[a] = ldata
            all_names_list.append(a)

    print(f"📚 Database caricato: {len(id_to_data)} squadre conosciute.")

    # 2. SCANSIONE CALENDARIO
    rounds = list(db.h2h_by_round.find({}))
    fixed_matches = 0
    errors_found = 0

    for r in tqdm(rounds, desc="Auditing Rounds"):
        round_league = r.get("league", "Unknown")
        matches = r.get("matches", [])
        modified = False
        
        # Se è una coppa, saltiamo l'audit rigoroso per evitare falsi positivi
        is_cup = any(k in round_league.lower() for k in ["cup", "coppa", "pokal", "champions", "europa", "playoff"])
        if is_cup:
            continue 

        for match in matches:
            for side in ["home", "away"]:
                tm_id_key = f"{side}_tm_id"
                name_key = side
                canonical_key = f"{side}_canonical"
                
                current_id = match.get(tm_id_key)
                current_name_str = match.get(name_key) # Il nome originale scritto nel calendario (es. "SC Braga")
                
                if not current_id: continue # Nulla da controllare
                
                # CHI È ASSEGNATO ORA?
                assigned_team = id_to_data.get(current_id)
                if not assigned_team: continue # ID non trovato nel DB teams? Strano, ma passiamo.
                
                assigned_league = assigned_team["league"]
                
                # CONTROLLO DI LEGALITÀ
                if not are_leagues_compatible(round_league, assigned_league):
                    # ERRORE TROVATO! (Es. Bra in Liga Portugal)
                    # print(f"🚨 ERRORE: {assigned_team['name']} ({assigned_league}) trovato in {round_league}. Match: {current_name_str}")
                    errors_found += 1
                    
                    # FIX: CERCA IL SOSTITUTO GIUSTO NELLA LEGA GIUSTA
                    correct_team = find_correct_team_strict_league(current_name_str, round_league, all_names_list, name_to_data)
                    
                    if correct_team:
                        # print(f"   ✅ FIXATO CON: {correct_team['name']} ({correct_team['league']})")
                        match[tm_id_key] = correct_team["id"]
                        match[canonical_key] = correct_team["name"]
                        modified = True
                        fixed_matches += 1
                    else:
                        # Se non troviamo nessuno, meglio rimuovere l'ID sbagliato che tenerlo
                        # print(f"   ❌ NESSUN SOSTITUTO TROVATO. Rimuovo ID errato.")
                        del match[tm_id_key]
                        if canonical_key in match: del match[canonical_key]
                        modified = True

        if modified:
            db.h2h_by_round.update_one({"_id": r["_id"]}, {"$set": {"matches": matches}})

    print("\n" + "="*60)
    print(f"🏁 AUDIT COMPLETATO.")
    print(f"🚨 Errori di lega rilevati: {errors_found}")
    print(f"✅ Partite corrette automaticamente: {fixed_matches}")
    print("="*60)

if __name__ == "__main__":
    audit_and_fix()
