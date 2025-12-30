#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_simulator_A.py - VERSIONE SILENZIOSA (BRIDGE CLOUD)
Interfaccia tra Backend Node.js e Motore di Simulazione.
"""

import os
import sys
import json
import re
from datetime import datetime

# --- PATH CONFIGURATION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
AI_ENGINE_DIR = CURRENT_DIR
PROJECT_ROOT = os.path.dirname(AI_ENGINE_DIR)

for path in [PROJECT_ROOT, AI_ENGINE_DIR, CURRENT_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

# --- IMPORT MOTORE ---
try:
    # Importiamo le funzioni core dal simulatore universale che abbiamo appena "silenziato"
    from ai_engine.universal_simulator import (
        preload_match_data,
        run_single_algo,
        run_monte_carlo_verdict_detailed,
        get_sign,
        get_round_number,
        has_valid_results
    )
    from config import db
except ImportError as e:
    err = {"success": False, "error": f"Import Error: {e}"}
    print(json.dumps(err), flush=True)
    sys.exit(1)

ALGO_NAMES = {1: "Statistico", 2: "Dinamico", 3: "Tattico", 4: "Caos", 5: "Master", 6: "MonteCarlo"}

def get_real_matches_from_db(league: str, main_mode: int):
    """Recupera le partite dal database in base alla giornata scelta."""
    try:
        # Pulizia nome lega per il DB
        league_clean = league.replace('_', ' ').title()
        
        # Mapping Giornate
        OFFSET = 0
        if main_mode == 1: OFFSET = -1    # Precedente
        elif main_mode == 2: OFFSET = 0   # In corso
        elif main_mode == 3: OFFSET = 1   # Successiva
        
        rounds_cursor = db.h2h_by_round.find({"league": league_clean})
        rounds_list = list(rounds_cursor)
        if not rounds_list: return []
        
        rounds_list.sort(key=lambda x: get_round_number(x.get('round_name', '0')))
        
        # Trova la giornata attuale
        anchor_index = -1
        for i, r in enumerate(rounds_list):
            if any(m.get('status') in ['Scheduled', 'Timed'] for m in r.get('matches', [])):
                anchor_index = i
                break
        if anchor_index == -1: anchor_index = len(rounds_list) - 1
        
        target_index = anchor_index + OFFSET
        if 0 <= target_index < len(rounds_list):
            target_round = rounds_list[target_index]
            return [{
                "home": m['home'], 
                "away": m['away'], 
                "round": target_round.get('round_name', 'N/A')
            } for m in target_round.get('matches', []) if m.get('home') and m.get('away')]
        return []
    except Exception as e:
        print(f"DB Error: {e}", file=sys.stderr)
        return []

def run_single_simulation(home_team: str, away_team: str, algo_id: int, cycles: int) -> dict:
    """Esegue una singola simulazione (o un set di Monte Carlo) per un match."""
    try:
        preloaded_data = preload_match_data(home_team, away_team)
        if not preloaded_data: return {"success": False, "error": "Dati DB mancanti"}

        # Se Algo 6 (Monte Carlo), deleghiamo il loop alla funzione core
        if algo_id == 6:
            # Impostiamo i cicli globali per la funzione
            import ai_engine.universal_simulator as us
            us.MONTE_CARLO_TOTAL_CYCLES = cycles
            
            res = run_monte_carlo_verdict_detailed(preloaded_data, home_team, away_team)
            (gh, ga) = res[0]
            top3 = [x[0] for x in res[2]] if len(res) > 2 else []
        else:
            # Per algoritmi singoli, facciamo una simulazione diretta
            gh, ga = run_single_algo(algo_id, preloaded_data, home_team, away_team)
            top3 = [f"{gh}-{ga}"]

        score = f"{gh}-{ga}"
        return {
            "success": True,
            "predicted_score": score,
            "sign": get_sign(gh, ga),
            "gh": gh, "ga": ga,
            "top3": top3,
            "algo_name": ALGO_NAMES.get(algo_id, "Custom")
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def main():
    start_time = datetime.now()
    try:
        # Lettura parametri da sys.argv (inviati dal Portiere main.py)
        if len(sys.argv) < 10:
            print(json.dumps({"success": False, "error": "Parametri insufficienti"}), flush=True)
            return

        main_mode = int(sys.argv[1])
        nation = sys.argv[2]
        league = sys.argv[3]
        home_team = sys.argv[4] if sys.argv[4] != "null" else None
        away_team = sys.argv[5] if sys.argv[5] != "null" else None
        algo_id = int(sys.argv[7])
        cycles = int(sys.argv[8])

        # --- ESECUZIONE ---
        if main_mode == 4 and home_team and away_team:
            # Simulazione Singola
            sim_res = run_single_simulation(home_team, away_team, algo_id, cycles)
            result = {"type": "single", **sim_res}
        
        elif main_mode in [1, 2, 3]:
            # Simulazione Massiva (Intera giornata)
            matches = get_real_matches_from_db(league, main_mode)
            sim_list = []
            for m in matches:
                res = run_single_simulation(m['home'], m['away'], algo_id, cycles)
                res["match"] = m
                sim_list.append(res)
            result = {"type": "massive", "league": league, "matches": sim_list, "total": len(sim_list), "success": True}
        
        else:
            result = {"success": False, "error": "Modalità non supportata"}

        # OUTPUT JSON FINALE (L'unico print verso il sito web)
        final_output = {
            "success": result.get("success", False),
            "timestamp": datetime.now().isoformat(),
            "execution_time": (datetime.now() - start_time).total_seconds(),
            "params": {"mode": main_mode, "league": league, "algo": algo_id, "cycles": cycles},
            "data": result
        }
        print(json.dumps(final_output, ensure_ascii=False), flush=True)

    except Exception as e:
        print(json.dumps({"success": False, "error": f"Critical: {str(e)}"}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()