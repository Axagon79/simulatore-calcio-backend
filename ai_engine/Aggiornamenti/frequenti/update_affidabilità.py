import os
import sys
import re
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

# --- 1. IMPORTAZIONE LOGICA CALCOLATORE ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = os.path.dirname(BASE_DIR)  # simulatore-calcio-backend/
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, "calculators"))

try:
    from calculator_affidabilità import calculate_reliability, build_caches  # type: ignore
    print("✅ Modulo 'calculator_affidabilità' caricato con successo.")
except ImportError as e:
    print(f"❌ Errore critico: Impossibile caricare il calcolatore. {e}")
    sys.exit(1)

# --- 2. CONFIGURAZIONE DATABASE ---
load_dotenv(os.path.join(BASE_DIR, ".env"))
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['football_simulator_db']

def get_round_num(r):
    """Estrae il numero della giornata dall'ID per l'ordinamento"""
    nums = re.findall(r'\d+', str(r.get('_id', '')))
    return int(nums[0]) if nums else 999

def run_update_affidabilità():
    h2h_collection = db['h2h_by_round']
    
    leghe = h2h_collection.distinct("league")
    print(f"\n{'='*60}")
    print(f"🚀 AVVIO AGGIORNAMENTO TOTALE SU {len(leghe)} CAMPIONATI")
    print(f"{'='*60}")

    # Carica cache in memoria (teams + matches_history) per eliminare query ripetute
    build_caches()

    count_total = 0
    oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    for lega in leghe:
        rounds_lega = list(h2h_collection.find({"league": lega}))
        rounds_lega.sort(key=get_round_num)
        
        if not rounds_lega: continue

        # --- ANCHOR: legge la giornata corrente dal DB (salvata dallo scraper NowGoal) ---
        anchor_index = -1
        current_round_doc = db['league_current_rounds'].find_one({"league": lega})
        if current_round_doc and current_round_doc.get('current_round'):
            target = current_round_doc['current_round']
            for i, r in enumerate(rounds_lega):
                if get_round_num(r) == target:
                    anchor_index = i
                    break

        # Fallback: ultima giornata con risultati
        if anchor_index == -1:
             for i in range(len(rounds_lega) - 1, -1, -1):
                 r = rounds_lega[i]
                 if any(m.get('status') == 'Finished' for m in r.get('matches', [])):
                     anchor_index = i
                     break
        if anchor_index == -1: anchor_index = len(rounds_lega) - 1

        # Range: 2 Prima, Attuale, 2 Dopo
        start = max(0, anchor_index - 2)
        end = min(len(rounds_lega), anchor_index + 3)
        target_rounds = rounds_lega[start:end]

        print(f"\n\n🏆 CAMPIONATO: {lega}")
        print(f"📍 Anchor rilevata: {rounds_lega[anchor_index].get('round_name', 'N/D')}")
        print(f"{'-'*60}")

        for doc in target_rounds:
            round_name = doc.get('round_name', 'Senza Nome')
            matches_array = doc.get('matches', [])
            
            # STAMPA INTESTAZIONE GIORNATA
            print(f"\n📅 {round_name.upper()} ({len(matches_array)} partite)")
            print(f"   {'Status':<12} | {'Incontro':<40} | {'Esito'}")
            print(f"   {'-'*65}")

            modificato = False
            for index, match in enumerate(matches_array):
                home_team = match.get('home_team') or match.get('homeTeam') or match.get('home')
                away_team = match.get('away_team') or match.get('awayTeam') or match.get('away')
                status = match.get('status', 'Unknown')
                
                if home_team and away_team:
                    voto_h = calculate_reliability(home_team)
                    voto_a = calculate_reliability(away_team)

                    if 'h2h_data' not in match or match['h2h_data'] is None:
                        match['h2h_data'] = {}
                    
                    match['h2h_data']['affidabilità'] = {
                        "affidabilità_casa": voto_h,
                        "affidabilità_trasferta": voto_a,
                        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    
                    modificato = True
                    count_total += 1
                    
                    # STAMPA RIGA PARTITA ALLINEATA
                    match_str = f"{home_team} vs {away_team}"
                    print(f"   ⚡ [{status:<10}] | {match_str:<40} | ✅ OK")

            if modificato:
                h2h_collection.update_one(
                    {"_id": doc['_id']},
                    {"$set": {"matches": matches_array}}
                )

    print(f"\n{'='*60}")
    print(f"✨ FINE OPERAZIONE! Totale partite processate: {count_total}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    run_update_affidabilità()