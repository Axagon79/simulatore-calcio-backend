import os
import sys

# CONFIGURAZIONE PATH
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
sys.path.append(PROJECT_ROOT)

from config import db

def run_injection_v3():
    h2h_col = db["h2h_by_round"]
    teams_col = db["teams"]
    
    # Prendiamo i documenti delle giornate (es. SerieA_25Giornata)
    rounds = list(h2h_col.find({}))
    print(f"🔄 Analisi di {len(rounds)} giornate/documenti...")

    updated_rounds = 0

    for round_doc in rounds:
        round_id = round_doc["_id"]
        matches_list = round_doc.get("matches", [])
        
        has_changes = False
        
        # Iteriamo sui singoli match dentro l'array
        for match in matches_list:
            home_id = match.get("home_tm_id") # Livello corretto
            away_id = match.get("away_tm_id") # Livello corretto

            if not home_id or not away_id:
                continue

            # Recupero dati da Teams (che avevamo già confermato essere corretto)
            home_team = teams_col.find_one({"transfermarkt_id": home_id})
            away_team = teams_col.find_one({"transfermarkt_id": away_id})

            # Inizializziamo il DNA se non esiste (anche se nel tuo JSON c'è già tec e val)
            if "h2h_data" not in match: match["h2h_data"] = {}
            if "h2h_dna" not in match["h2h_data"]: match["h2h_data"]["h2h_dna"] = {}
            
            dna = match["h2h_data"]["h2h_dna"]
            if "home_dna" not in dna: dna["home_dna"] = {}
            if "away_dna" not in dna: dna["away_dna"] = {}

            # --- SQUADRA CASA ---
            if home_team and "scores" in home_team:
                s = home_team["scores"]
                dna["home_dna"]["att"] = round((s.get("attack_home", 0) / 15) * 100, 1)
                dna["home_dna"]["def"] = round((s.get("defense_home", 0) / 10) * 100, 1)
                has_changes = True

            # --- SQUADRA TRASFERTA ---
            if away_team and "scores" in away_team:
                s = away_team["scores"]
                dna["away_dna"]["att"] = round((s.get("attack_away", 0) / 15) * 100, 1)
                dna["away_dna"]["def"] = round((s.get("defense_away", 0) / 10) * 100, 1)
                has_changes = True

        # Se abbiamo modificato i match dentro la giornata, salviamo l'intero array
        if has_changes:
            h2h_col.update_one({"_id": round_id}, {"$set": {"matches": matches_list}})
            updated_rounds += 1

    print(f"🏁 Fine. Aggiornate {updated_rounds} giornate con i valori ATT e DEF.")

if __name__ == "__main__":
    run_injection_v3()