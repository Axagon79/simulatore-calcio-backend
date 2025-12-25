import os
import sys
from datetime import datetime

# 1. CONFIGURAZIONE DEI PERCORSI
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR)) 
sys.path.append(PROJECT_ROOT)
sys.path.append(CURRENT_DIR)

try:
    from config import db
    # Importiamo la logica di calcolo dal file che hai analizzato
    import calculate_team_rating as rating_lib
    print("✅ [INJECTOR-TEC-FORMAZIONI] Connessione stabilita.")
except ImportError as e:
    print(f"❌ [INJECTOR-TEC-FORMAZIONI] Errore: {e}")
    sys.exit(1)

def run_injection():
    """
    Iniezione specifica: 
    - TEC (Tecnica) per il grafico radar
    - FORMAZIONI (Titolari e Panchina) per il tabellino
    """
    teams_col = db["teams"]
    h2h_col = db["h2h_by_round"]

    print("🚀 Lancio iniezione DNA (TEC) e FORMAZIONI...")

    # Cache per velocizzare l'esecuzione tra vari match
    data_cache = {}

    def get_full_team_data(tm_id):
        if tm_id in data_cache:
            return data_cache[tm_id]

        # RISOLUZIONE ID -> NOME (Risolve il problema Guimaraes/Nomi diversi)
        team_doc = teams_col.find_one({"transfermarkt_id": int(tm_id)})
        if not team_doc:
            return None
        
        official_name = team_doc.get("name")

        try:
            # Chiamata alla funzione di calcolo
            result = rating_lib.calculate_team_rating(official_name)
            if result:
                processed = {
                    "tec_perc": round(result.get("rating_5_25", 0) * 4, 1), # Scala 0-100%
                    "starters": result.get("starters", []),
                    "bench": result.get("bench", []),
                    "formation": result.get("formation", "N/D")
                }
                data_cache[tm_id] = processed
                return processed
        except Exception as e:
            print(f"⚠️ Errore per {official_name}: {e}")
        
        return None

    all_rounds = list(h2h_col.find({}))
    processed_count = 0

    for round_doc in all_rounds:
        round_id = round_doc["_id"]
        matches = round_doc.get("matches", [])
        modified = False

        for match in matches:
            id_home = match.get("home_tm_id")
            id_away = match.get("away_tm_id")

            if not id_home or not id_away:
                continue

            h_data = get_full_team_data(id_home)
            a_data = get_full_team_data(id_away)

            if not h_data or not a_data:
                continue

            # Struttura h2h_data
            if "h2h_data" not in match or match["h2h_data"] is None:
                match["h2h_data"] = {}
            
            # --- PARTE 1: DNA (Grafico) ---
            if "h2h_dna" not in match["h2h_data"]:
                match["h2h_data"]["h2h_dna"] = {"home_dna": {}, "away_dna": {}}
            
            match["h2h_data"]["h2h_dna"]["home_dna"]["tec"] = h_data["tec_perc"]
            match["h2h_data"]["h2h_dna"]["away_dna"]["tec"] = a_data["tec_perc"]

            # --- PARTE 2: FORMAZIONI (Tabellino) ---
            match["h2h_data"]["formazioni"] = {
                "home_squad": {
                    "modulo": h_data["formation"],
                    "titolari": h_data["starters"],
                    "panchina": h_data["bench"]
                },
                "away_squad": {
                    "modulo": a_data["formation"],
                    "titolari": a_data["starters"],
                    "panchina": a_data["bench"]
                }
            }
            
            modified = True
            processed_count += 1

        if modified:
            h2h_col.update_one(
                {"_id": round_id},
                {"$set": {"matches": matches, "last_tec_formazioni_update": datetime.now()}}
            )

    print(f"🏁 Fine. Elaborati {processed_count} match. Database aggiornato con TEC e FORMAZIONI.")

if __name__ == "__main__":
    run_injection()