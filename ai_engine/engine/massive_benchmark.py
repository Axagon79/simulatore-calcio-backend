import os
import sys
import csv
import re
from datetime import datetime
from collections import Counter
from tqdm import tqdm
import contextlib
import random


#(** VERSIONE DI TEST, NON IL MOTORE PRINCIPALE: USARE SOLO PER PROVE E BENCHMARK TECNICI )​
#( LANCIA UN BENCHMARK AUTOMATICO SULL’ULTIMA GIORNATA E SOVRASCRIVE SEMPRE IL FILE 'benchmark_latest.csv' )​
#( GEMELLO “SPERIMENTALE” DI universal_simulator: SE ATTIVATO PUÒ RIEMPIRE DB E CSV CON DATI DI PROVA **)


# --- FIX PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) 

if project_root not in sys.path: sys.path.insert(0, project_root)
if current_dir not in sys.path: sys.path.insert(0, current_dir)

try:
    from config import db
    from engine_core import predict_match, preload_match_data
    from goals_converter import calculate_goals_from_engine
    
    # IMPORT MANAGER
    sys.path.append(os.path.join(current_dir, 'database'))
    try:
        from prediction_manager import PredictionManager
    except ImportError:
        try:
            from prediction_manager import PredictionManager # Fallback
        except:
            PredictionManager = None
except ImportError as e:
    print(f"❌ ERRORE DI IMPORT: {e}")
    sys.exit(1)

# --- CONFIGURAZIONI ---
MONTE_CARLO_TOTAL_CYCLES = 5000

# --- SUPPORTO ---
@contextlib.contextmanager
def suppress_stdout():
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try: yield
        finally: sys.stdout = old_stdout

def get_sign(h, a):
    if h > a: return "1"
    elif a > h: return "2"
    return "X"

def get_round_number(round_name):
    try:
        num = re.search(r'\d+', str(round_name))
        return int(num.group()) if num else 0
    except: return 0

def has_valid_results(round_doc):
    for m in round_doc.get('matches', []):
        s = m.get('real_score')
        if s and isinstance(s, str) and ":" in s and s != "null":
            return True
    return False

# --- SIMULAZIONI ---
def run_single_algo(algo_id, preloaded_data):
    s_h, s_a, r_h, r_a = predict_match("", "", mode=algo_id, preloaded_data=preloaded_data)
    if s_h is None: return 0, 0
    gh, ga, _, _, _ = calculate_goals_from_engine(s_h, s_a, r_h, r_a, algo_mode=algo_id)
    return gh, ga

def run_monte_carlo_verdict(preloaded_data):
    nominees = []
    algos = [2, 3, 4, 5]
    cycles_per_algo = MONTE_CARLO_TOTAL_CYCLES // 4
    
    for aid in algos:
        local_results = []
        for _ in range(cycles_per_algo): 
            s_h, s_a, r_h, r_a = predict_match("", "", mode=aid, preloaded_data=preloaded_data)
            if s_h is None: continue
            gh, ga, _, _, _ = calculate_goals_from_engine(s_h, s_a, r_h, r_a, algo_mode=aid)
            local_results.append(f"{gh}-{ga}")
            
        if not local_results: continue
        top_3 = Counter(local_results).most_common(3)
        for sc, freq in top_3:
            w = int(freq) 
            nominees.extend([sc] * w)
            
    if not nominees: return 0, 0
    final_verdict = random.choice(nominees)
    return map(int, final_verdict.split("-"))

# --- MAIN ---
def run_benchmark():
    print(f"\n🚀 AVVIO BENCHMARK REALE (Monte Carlo = {MONTE_CARLO_TOTAL_CYCLES} cicli)")
    
    # --- INTERRUTTORE INTERATTIVO ---
    save_to_db = False
    db_mode = "SANDBOX"
    manager = None

    if PredictionManager:
        print("\n💾 SALVATAGGIO DATABASE")
        ans = input("   Vuoi salvare i risultati nel DB Mongo? (S/N): ").strip().upper()
        if ans == 'S':
            save_to_db = True
            print("   Dove vuoi salvare?")
            print("   [1] SANDBOX (Test/Sperimentale)")
            print("   [2] UFFICIALE (Produzione)")
            choice = input("   Scelta (1/2): ").strip()
            
            manager = PredictionManager() 
            if choice == '2':
                manager.collection = db['predictions_official']
                manager.coll_name = 'predictions_official'
                db_mode = "OFFICIAL"
                print("   ✅ Modalità UFFICIALE attivata.")
            else:
                manager.collection = db['predictions_sandbox']
                manager.coll_name = 'predictions_sandbox'
                db_mode = "SANDBOX"
                print("   ✅ Modalità SANDBOX attivata.")
        else:
            print("   ❌ Nessun salvataggio DB. Solo CSV.")
    
    # --- RECUPERO PARTITE ---
    print("\n🔍 Ricerca partite (Ultima Giornata Giocata)...")
    matches_to_test = []
    leagues = db.h2h_by_round.distinct("league")
    
    for league_name in leagues:
        rounds_cursor = db.h2h_by_round.find({"league": league_name})
        rounds_list = list(rounds_cursor)
        if not rounds_list: continue
        rounds_list.sort(key=lambda x: get_round_number(x.get('round_name', '0')))
        
        target_round = None
        for r in reversed(rounds_list):
            if has_valid_results(r):
                target_round = r
                break 
        
        if not target_round: continue
        r_name = target_round.get('round_name', 'Unknown')

        for m in target_round.get('matches', []):
            real_s = m.get('real_score')
            if real_s and isinstance(real_s, str) and ":" in real_s and real_s != "null":
                try:
                    rh, ra = map(int, real_s.split(":"))
                    matches_to_test.append({
                        "home": m['home'],
                        "away": m['away'],
                        "league": league_name,
                        "round": r_name,
                        "real_h": rh,
                        "real_a": ra,
                        "date_obj": m.get('date_obj')
                    })
                except: continue

    print(f"🎯 Trovate {len(matches_to_test)} partite.")
    if not matches_to_test: return

    # --- NOME FILE FISSO (Sovrascrittura) ---
    filename = "benchmark_latest.csv"
    print(f"💾 Output CSV: {filename}")
    print("⏳ Elaborazione in corso...")

    fieldnames = ['League', 'Round', 'Match', 'Real_Score', 'Real_Sign']
    algos_map = {1:'Statistica', 2:'Dinamico', 3:'Tattico', 4:'Caos', 5:'Master', 6:'MonteCarlo'}
    for i in range(1, 7): fieldnames.extend([f'{name}_Score', f'{name}_Sign', f'{name}_Correct'])

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for match in tqdm(matches_to_test):
            h = match['home']
            a = match['away']
            
            with suppress_stdout():
                try: preloaded = preload_match_data(h, a)
                except: continue

            row = {
                'League': match['league'],
                'Round': match['round'],
                'Match': f"{h} vs {a}",
                'Real_Score': f"{match['real_h']}-{match['real_a']}",
                'Real_Sign': get_sign(match['real_h'], match['real_a'])
            }

            algo_results = {}
            for algo_id in range(1, 6):
                name = algos_map[algo_id]
                gh, ga = run_single_algo(algo_id, preloaded)
                algo_results[name] = f"{gh}-{ga}"
                row[f'{name}_Score'] = f"{gh}-{ga}"
                row[f'{name}_Sign'] = get_sign(gh, ga)
                row[f'{name}_Correct'] = (row[f'{name}_Sign'] == row['Real_Sign'])

            mh, ma = run_monte_carlo_verdict(preloaded)
            verdict_score = f"{mh}-{ma}"
            row['MonteCarlo_Score'] = verdict_score
            row['MonteCarlo_Sign'] = get_sign(mh, ma)
            row['MonteCarlo_Correct'] = (row['MonteCarlo_Sign'] == row['Real_Sign'])

            if save_to_db and manager:
                snapshot = {
                    "home_att": preloaded['home_raw']['attack'],
                    "home_def": preloaded['home_raw']['defense'],
                    "away_att": preloaded['away_raw']['attack'],
                    "away_def": preloaded['away_raw']['defense']
                }
                d_str = str(match.get('date_obj', datetime.now().date()))
                
                pred_id, coll = manager.save_prediction(
                    home=h, away=a, league=match['league'], date_str=d_str,
                    snapshot_data=snapshot,
                    algo_data=algo_results,
                    final_verdict_score=verdict_score 
                )
                
                manager.collection.update_one(
                    {"_id": pred_id},
                    {"$set": {
                        "real_outcome": row['Real_Score'],
                        "status": "VERIFIED",
                        "check_sign": row['MonteCarlo_Correct']
                    }}
                )

            writer.writerow(row)
            csvfile.flush()

    print(f"\n✅ FINITO! CSV aggiornato.")
    if save_to_db:
        print(f"✅ DATI SALVATI NEL DATABASE ({db_mode}).")

if __name__ == "__main__":
    run_benchmark()
