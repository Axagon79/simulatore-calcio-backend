import os
import sys
import re
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

# --- 1. IMPORTAZIONE LOGICA CALCOLATORE ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(BASE_DIR, "calculators"))

try:
    from calculator_affidabilità import calculate_reliability  
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
    
    # Prendiamo tutte le leghe per analizzarle una ad una
    leghe = h2h_collection.distinct("league")
    print(f"🚀 Avvio Aggiornamento Mirato su {len(leghe)} campionati...")

    count = 0
    oggi = datetime.now()

    for lega in leghe:
        # 1. Carichiamo tutti i round della lega e li ordiniamo
        rounds_lega = list(h2h_collection.find({"league": lega}))
        rounds_lega.sort(key=get_round_num)
        
        if not rounds_lega: continue

        # 2. Identificazione Giornata "Anchor" (Attuale)
        anchor_index = -1
        for i, r in enumerate(rounds_lega):
            matches = r.get('matches', [])
            # Se c'è almeno un match Scheduled, questa è la nostra zona operativa
            if any(m.get('status') in ['Scheduled', 'Timed'] for m in matches):
                anchor_index = i
                break
        
        # Se non troviamo match futuri, prendiamo l'ultima giornata disponibile
        if anchor_index == -1: anchor_index = len(rounds_lega) - 1

        # Definiamo il range di aggiornamento (2 PRECEDENTI, ATTUALE, 2 SUCCESSIVE)
        start = max(0, anchor_index - 2)
        end = min(len(rounds_lega), anchor_index + 3) # +3 perché il limite superiore è escluso
        target_rounds = rounds_lega[start:end]

        print(f"🏆 {lega}: Analizzo range AMPIO giornate {start+1} -> {end}")

        for doc in target_rounds:
            matches_array = doc.get('matches', [])
            modificato = False
            
            for index, match in enumerate(matches_array):
                # AGGIORNA SOLO SE: Il match è da giocare o non ha ancora un risultato verificato
                if match.get('status') in ['Scheduled', 'Timed'] or match.get('real_score') is None:
                    
                    home_team = match.get('home_team') or match.get('homeTeam') or match.get('home')
                    away_team = match.get('away_team') or match.get('awayTeam') or match.get('away')
                    
                    if home_team and away_team:
                        # Logica a ventaglio
                        voto_h = calculate_reliability(home_team)
                        voto_a = calculate_reliability(away_team)

                        # Iniezione chirurgica nell'oggetto h2h_data del match
                        if 'h2h_data' not in match or match['h2h_data'] is None:
                            match['h2h_data'] = {}
                        
                        match['h2h_data']['affidabilità'] = {
                            "affidabilità_casa": voto_h,
                            "affidabilità_trasferta": voto_a,
                            "last_update": oggi.strftime("%Y-%m-%d %H:%M")
                        }
                        
                        modificato = True
                        count += 1
                        print(f"   ⚡ [{doc['_id']}] {home_team} vs {away_team} -> Calcolato")

            # Salviamo la giornata solo se abbiamo apportato modifiche
            if modificato:
                h2h_collection.update_one(
                    {"_id": doc['_id']},
                    {"$set": {"matches": matches_array}}
                )

    print(f"\n✨ Operazione conclusa! Aggiornati {count} match critici.")

if __name__ == "__main__":
    run_update_affidabilità()