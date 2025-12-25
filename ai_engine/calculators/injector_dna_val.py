import os
import sys
from datetime import datetime

# Aggiunta path per caricare la configurazione centralizzata
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(CURRENT_DIR)

try:
    from config import db
    print("✅ [INJECTOR-VAL] Connessione al database stabilita.")
except ImportError:
    print("❌ [INJECTOR-VAL] Errore: config.py non trovato.")
    sys.exit(1)

def run_injection_val():
    """
    Estrae 'strengthScore09' da Teams e lo inietta come percentuale (0-100)
    nella struttura nidificata DNA di h2h_by_round sotto la chiave 'val'.
    """
    teams_col = db["teams"]
    h2h_col = db["h2h_by_round"]

    print("🚀 Inizio aggiornamento asse VALORE (VAL)...")

    # 1. Recuperiamo tutti i documenti delle giornate
    all_rounds = list(h2h_col.find({}))
    matches_processed = 0

    for round_doc in all_rounds:
        round_id = round_doc["_id"]
        matches = round_doc.get("matches", [])
        modified = False

        for match in matches:
            # Recupero ID per il matching
            id_home = match.get("home_tm_id")
            id_away = match.get("away_tm_id")

            if id_home is None or id_away is None:
                continue

            # Cerchiamo le squadre nella collezione Teams tramite transfermarkt_id
            home_team_data = teams_col.find_one({"transfermarkt_id": int(id_home)})
            away_team_data = teams_col.find_one({"transfermarkt_id": int(id_away)})

            # Estrazione strengthScore09 e conversione in percentuale (x10)
            val_home = 0
            if home_team_data:
                score = home_team_data.get("stats", {}).get("strengthScore09", 0)
                val_home = round(score * 10, 1)

            val_away = 0
            if away_team_data:
                score = away_team_data.get("stats", {}).get("strengthScore09", 0)
                val_away = round(score * 10, 1)

            # COSTRUZIONE STRUTTURA NIDIFICATA (DNA System)
            if "h2h_data" not in match or match["h2h_data"] is None:
                match["h2h_data"] = {}
            
            if "h2h_dna" not in match["h2h_data"]:
                match["h2h_data"]["h2h_dna"] = {
                    "home_dna": {},
                    "away_dna": {}
                }

            # Iniezione del campo VALORE (Corretto da 'tec' a 'val')
            match["h2h_data"]["h2h_dna"]["home_dna"]["val"] = val_home
            match["h2h_data"]["h2h_dna"]["away_dna"]["val"] = val_away
            
            modified = True
            matches_processed += 1

        # Aggiornamento del documento su MongoDB
        if modified:
            h2h_col.update_one(
                {"_id": round_id},
                {"$set": {"matches": matches, "last_dna_val_update": datetime.now()}}
            )

    print(f"🏁 Fine. Elaborati {matches_processed} match. Asse VAL aggiornato al 100%.")

if __name__ == "__main__":
    run_injection_val()