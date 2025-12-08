import os
import sys

# --- HARD FIX PERCORSI ---
current_script_path = os.path.abspath(__file__)
ai_engine_dir = os.path.dirname(current_script_path)
project_root = os.path.dirname(ai_engine_dir)

if project_root not in sys.path: sys.path.insert(0, project_root)
if ai_engine_dir not in sys.path: sys.path.insert(0, ai_engine_dir)
if os.path.join(ai_engine_dir, 'engine') not in sys.path: sys.path.insert(0, os.path.join(ai_engine_dir, 'engine'))

try:
    try: from config import db
    except: 
        sys.path.append(project_root)
        from config import db

    import engine_core 
    from engine_core import predict_match, preload_match_data
    from goals_converter import calculate_goals_from_engine
    
    PredictionManager = None
    try:
        from prediction_manager import PredictionManager
        print("✅ [MANAGER] PredictionManager caricato.")
    except:
        print("⚠️ PredictionManager NON trovato (Salvataggio DB off).")

except ImportError as e:
    print(f"❌ ERRORE FATALE IMPORT: {e}")
    sys.exit(1)

# --- FINE IMPORT ---
import csv
import re
from datetime import datetime
from collections import Counter
from tqdm import tqdm
import contextlib
import random

# --- CONFIGURAZIONI ---
MONTE_CARLO_TOTAL_CYCLES = 5000
CSV_DELIMITER = ';'

# --- HELPER FUNZIONI ---
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

def get_under_over(h, a, threshold=2.5):
    return "OVER" if (h + a) > threshold else "UNDER"

def get_gol_nogol(h, a):
    return "GG" if (h > 0 and a > 0) else "NG"

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

# --- MOTORI ---
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

# --- LOGICA CORE ---
def run_universal_simulator():
    print(f"\n🌍 SIMULATORE UNIVERSALE (Versione Completa)")
    
    # 1. SCELTA TARGET
    print("\n📅 SELEZIONA PERIODO:")
    print("   [1] GIORNATA PRECEDENTE (Verifica Storica)")
    print("   [2] GIORNATA IN CORSO (Mix Giocate/Da Giocare)")
    print("   [3] GIORNATA SUCCESSIVA (Pronostici Futuri)")
    
    try:
        offset_choice = int(input("   Scelta (1-3): ").strip())
        if offset_choice == 1: OFFSET = -1
        elif offset_choice == 2: OFFSET = 0
        elif offset_choice == 3: OFFSET = 1
        else: raise ValueError
    except: return

    # 2. SCELTA LEGA
    print("\n🏆 SELEZIONE CAMPIONATI:")
    print("   [0] TUTTI I CAMPIONATI (Massivo)")
    leagues = sorted(db.h2h_by_round.distinct("league"))
    for i, l in enumerate(leagues):
        print(f"   [{i+1}] {l}")
    
    selected_leagues = []
    try:
        l_choice = int(input("   Scelta: ").strip())
        if l_choice == 0: selected_leagues = leagues
        else: selected_leagues = [leagues[l_choice-1]]
    except: return

    # 3. RECUPERO PARTITE
    matches_to_process = []
    print(f"\n🔍 Recupero partite...")
    
    for league_name in selected_leagues:
        rounds_cursor = db.h2h_by_round.find({"league": league_name})
        rounds_list = list(rounds_cursor)
        if not rounds_list: continue
        rounds_list.sort(key=lambda x: get_round_number(x.get('round_name', '0')))
        
        anchor_index = -1
        for i in range(len(rounds_list) - 1, -1, -1):
            if has_valid_results(rounds_list[i]):
                anchor_index = i
                break
        
        if anchor_index == -1 and OFFSET <= 0: continue 
        target_index = anchor_index + OFFSET
        
        if 0 <= target_index < len(rounds_list):
            target_round = rounds_list[target_index]
            r_name = target_round.get('round_name', 'Unknown')
            for m in target_round.get('matches', []):
                real_s = m.get('real_score')
                has_real = False
                rh, ra = 0, 0
                if real_s and isinstance(real_s, str) and ":" in real_s and real_s != "null":
                    try:
                        rh, ra = map(int, real_s.split(":"))
                        has_real = True
                    except: pass
                
                matches_to_process.append({
                    "home": m['home'], "away": m['away'],
                    "league": league_name, "round": r_name,
                    "real_gh": rh, "real_ga": ra,
                    "real_score_str": f"{rh}-{ra}" if has_real else "-",
                    "has_real": has_real, "date_obj": m.get('date_obj')
                })

    if not matches_to_process:
        print("❌ Nessuna partita trovata.")
        return

    # --- ANTEPRIMA PARTITE (RESTAURATA!) ---
    print("\n📋 ANTEPRIMA PARTITE:")
    limit_preview = 5
    for m in matches_to_process[:limit_preview]:
        status_txt = f"[FINITA {m['real_score_str']}]" if m['has_real'] else "[DA GIOCARE]"
        print(f"   • {m['league']}: {m['home']} vs {m['away']} {status_txt}")
    if len(matches_to_process) > limit_preview:
        print(f"   ... e altre {len(matches_to_process) - limit_preview}.")

    # 4. SALVATAGGIO DB (Opzionale)
    save_to_db = False
    manager = None
    if PredictionManager:
        print("\n💾 VUOI SALVARE I RISULTATI NEL DB?")
        if input("   (S/N): ").strip().upper() == 'S':
            save_to_db = True
            choice = input("   [1] SANDBOX | [2] UFFICIALE: ").strip()
            manager = PredictionManager()
            manager.collection = db['predictions_official'] if choice == '2' else db['predictions_sandbox']

    # 5. CALCOLO E REPORT
    filename = "simulation_report.csv"
    print(f"\n⏳ Output: {filename}")
    
    algos_names = ['Stat', 'Din', 'Tat', 'Caos', 'Master', 'MonteCarlo']
    data_by_algo = {name: [] for name in algos_names}
    
    processed = 0
    
    for match in tqdm(matches_to_process):
        with suppress_stdout():
            try: preloaded = preload_match_data(match['home'], match['away'])
            except: continue
        
        algo_preds_db = {}
        for aid in range(1, 6):
            th, ta = run_single_algo(aid, preloaded)
            name = algos_names[aid-1]
            data_by_algo[name].append({
                'match': match, 'pred_gh': th, 'pred_ga': ta
            })
            algo_preds_db[f"Algo_{aid}"] = f"{th}-{ta}"
            
        mh, ma = run_monte_carlo_verdict(preloaded)
        data_by_algo['MonteCarlo'].append({
            'match': match, 'pred_gh': mh, 'pred_ga': ma
        })
        
        if save_to_db and manager:
            d_str = str(match.get('date_obj', datetime.now().date()))
            snap = {"home_att": 0, "away_att": 0}
            pred_id, _ = manager.save_prediction(
                home=match['home'], away=match['away'], league=match['league'], date_str=d_str,
                snapshot_data=snap, algo_data=algo_preds_db, final_verdict_score=f"{mh}-{ma}" 
            )
            if match['has_real']:
                is_win = get_sign(mh, ma) == get_sign(match['real_gh'], match['real_ga'])
                manager.collection.update_one(
                    {"_id": pred_id},
                    {"$set": {"real_outcome": match['real_score_str'], "status": "VERIFIED", "check_sign": is_win}}
                )
        processed += 1

    # --- SCRITTURA REPORT (CON ; PER EXCEL) ---
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, delimiter=CSV_DELIMITER)
        
        headers = [
            "League", "Match", "Real Score", "Real Sign", 
            "PRED Score", "PRED Sign", "1X2 Outcome", 
            "Exact Score", "U/O 2.5 Pred", "U/O Outcome", 
            "GG/NG Pred", "GG/NG Outcome"
        ]

        for algo_name in algos_names:
            writer.writerow([])
            writer.writerow([f"=== ALGORITMO: {algo_name.upper()} ==="])
            writer.writerow(headers)
            
            stats = {'1X2': 0, 'Exact': 0, 'UO': 0, 'GG': 0, 'Total': 0}
            rows_data = data_by_algo[algo_name]
            
            for item in rows_data:
                m = item['match']
                ph, pa = item['pred_gh'], item['pred_ga']
                p_score = f"{ph}-{pa}"
                p_sign = get_sign(ph, pa)
                p_uo = get_under_over(ph, pa)
                p_gg = get_gol_nogol(ph, pa)
                
                r_score = m['real_score_str']
                r_sign = "-"
                out_1x2 = "WAITING"
                out_exact = "WAITING"
                out_uo = "WAITING"
                out_gg = "WAITING"
                
                if m['has_real']:
                    stats['Total'] += 1
                    rh, ra = m['real_gh'], m['real_ga']
                    r_sign = get_sign(rh, ra)
                    r_uo = get_under_over(rh, ra)
                    r_gg = get_gol_nogol(rh, ra)
                    
                    if p_sign == r_sign: 
                        out_1x2 = "WIN"
                        stats['1X2'] += 1
                    else: out_1x2 = "LOSS"
                    
                    if ph == rh and pa == ra:
                        out_exact = "WIN"
                        stats['Exact'] += 1
                    else: out_exact = "LOSS"
                    
                    if p_uo == r_uo:
                        out_uo = "WIN"
                        stats['UO'] += 1
                    else: out_uo = "LOSS"
                    
                    if p_gg == r_gg:
                        out_gg = "WIN"
                        stats['GG'] += 1
                    else: out_gg = "LOSS"

                writer.writerow([
                    m['league'],
                    f"{m['home']} vs {m['away']}",
                    r_score, r_sign,
                    p_score, p_sign, out_1x2,
                    out_exact,
                    p_uo, out_uo,
                    p_gg, out_gg
                ])
            
            if stats['Total'] > 0:
                t = stats['Total']
                writer.writerow([
                    "--- PERCENTUALI ---", "", "", "",
                    "", "", 
                    f"{round(stats['1X2']/t*100,1)}%",
                    f"{round(stats['Exact']/t*100,1)}%",
                    "",
                    f"{round(stats['UO']/t*100,1)}%",
                    "",
                    f"{round(stats['GG']/t*100,1)}%"
                ])
            else:
                writer.writerow(["Nessuna statistica disponibile"])
            
            writer.writerow([])

    print(f"\n✅ REPORT GENERATO: {filename}")
    print(f"   (Separatore: punto e virgola ';' per Excel)")

if __name__ == "__main__":
    run_universal_simulator()
