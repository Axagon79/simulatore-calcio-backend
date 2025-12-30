#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_simulator_A.py - VERSIONE DEFINITIVA (REAL DATA)
Si connette a MongoDB e recupera le PARTITE VERE del calendario.
"""

import os
import sys
import json
import re
from datetime import datetime
from pymongo import MongoClient  # ✅ NECESSARIO PER I DATI REALI

# --- PATH MAGIC ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
AI_ENGINE_DIR = CURRENT_DIR
PROJECT_ROOT = os.path.dirname(AI_ENGINE_DIR)
for path in [PROJECT_ROOT, AI_ENGINE_DIR, CURRENT_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

# --- IMPORT ALGORITMI ---
try:
    from ai_engine.universal_simulator import (
        preload_match_data,
        run_single_algo,
        run_monte_carlo_verdict_detailed
    )
except ImportError as e:
    err = {"success": False, "error": f"Import Error: {e}"}
    print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)


# --- CONFIG DB ---
DB_NAME = "football_simulator_db"
MONGO_URI = "mongodb://localhost:27017/"

ALGO_NAMES = {
    1: "Statistico Puro", 2: "Dinamico", 3: "Tattico", 
    4: "Caos", 5: "Master", 6: "MonteCarlo"
}

def get_real_matches_from_db(nation: str, league: str, main_mode: int):
    """ESATTA logia dal tuo universal_simulator.py [file:50]"""
    try:
        from config import db  # Come nel tuo file
        
        # OFFSET dal main_mode (IDENTICO al tuo flusso)
        OFFSET = 0
        if main_mode == 1: OFFSET = -1      # Giornata Precedente
        elif main_mode == 2: OFFSET = 0     # Giornata In Corso  
        elif main_mode == 3: OFFSET = 1     # Giornata Successiva
        
        print(f"[DB] Recupero {league} (OFFSET={OFFSET})...", file=sys.stderr)
        
        # QUERY ESATTA dal tuo codice
        rounds_cursor = db.h2h_by_round.find({"league": league})
        rounds_list = list(rounds_cursor)
        
        if not rounds_list:
            print(f"[DB] Nessun round trovato per {league}", file=sys.stderr)
            return []
        
        # ORDINA PER NUMERO GIORNATA (dal tuo codice)
        rounds_list.sort(key=lambda x: get_round_number(x.get('round_name', '0')))
        
        # TROVA ANCHOR (dal tuo codice ESATTO)
        anchor_index = -1
        for i, r in enumerate(rounds_list):
            if any(m.get('status') in ['Scheduled', 'Timed'] for m in r.get('matches', [])):
                anchor_index = i
                break
        if anchor_index == -1:
            for i in range(len(rounds_list) - 1, -1, -1):
                if has_valid_results(r):  # Funzione dal tuo file
                    anchor_index = i
                    break
        
        target_index = anchor_index + OFFSET if OFFSET != 0 else anchor_index
        if target_index < 0 or target_index >= len(rounds_list):
            print(f"[DB] Giornata fuori range (target={target_index})", file=sys.stderr)
            return []
        
        target_round = rounds_list[target_index]
        matches = target_round.get('matches', [])
        
        real_matches = []
        for m in matches:
            home = m.get('home')
            away = m.get('away')
            if home and away:
                real_matches.append({
                    "home": home,
                    "away": away, 
                    "round": target_round.get('round_name', 'N/A')
                })
        
        print(f"[DB] Trovate {len(real_matches)} partite {league} {target_round.get('round_name')}", file=sys.stderr)
        return real_matches
        
    except Exception as e:
        print(f"[DB] Errore: {e}", file=sys.stderr)
        return []
def get_round_number(round_name):
    """DAL TUO universal_simulator.py"""
    try:
        num = re.search(r'\d+', str(round_name))
        return int(num.group()) if num else 0
    except: 
        return 0

def has_valid_results(round_doc):
    """DAL TUO universal_simulator.py""" 
    for m in round_doc.get('matches', []):
        s = m.get('real_score')
        if s and isinstance(s, str) and ":" in s and s != "null":
            return True
    return False


def run_single_simulation(home_team: str, away_team: str, league: str, 
                         round_name: str, algo_id: int, cycles: int) -> dict:
    try:
        preloaded_data = preload_match_data(home_team, away_team)
        if not preloaded_data:
            return {"success": False, "error": "Dati insufficienti"}

        results = []
        for _ in range(cycles):
            if algo_id == 6:
                res = run_monte_carlo_verdict_detailed(preloaded_data, home_team, away_team, analyzer=None)
                gh, ga = res[0] if res else (0, 0)
            else:
                gh, ga = run_single_algo(algo_id, preloaded_data, home_name=home_team, away_name=away_team)
            results.append(f"{gh}-{ga}")
        
        from collections import Counter
        top_score = Counter(results).most_common(1)[0][0]
        gh, ga = map(int, top_score.split('-'))
        sign = "1" if gh > ga else ("2" if ga > gh else "X")
        
        return {
            "success": True,
            "predicted_score": top_score,
            "sign": sign,
            "gh": gh, "ga": ga,
            "top3": [x[0] for x in Counter(results).most_common(3)],
            "total_cycles": cycles,
            "algo_name": ALGO_NAMES.get(algo_id, "Custom")
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def run_massive_simulation(nation: str, league: str, algo_id: int, cycles: int, main_mode: int):
    # 1. RECUPERA PARTITE VERE
    real_matches = get_real_matches_from_db(nation, league, main_mode)
    
    # Se il DB non risponde o è vuoto per quella lega, usa una lista di sicurezza 
    # (Solo per evitare crash durante i test se non hai popolato il DB)
    if not real_matches:
        return {
            "success": False, 
            "error": f"Nessuna partita trovata nel DB per {nation} - {league}. Assicurati di aver aggiornato il calendario."
        }

    results = []
    for match in real_matches:
        single_result = run_single_simulation(
            match["home"], match["away"], league, 
            match.get("round", "N/A"), algo_id, cycles
        )
        single_result["match"] = match
        results.append(single_result)
    
    return {
        "success": True,
        "type": "massive",
        "nation": nation,
        "league": league,
        "total_matches": len(results),
        "matches": results
    }

def main():
    # --- GESTIONE PARAMETRI INTELLIGENTE (BASE vs DEV) ---
    try:
        # Se chiamiamo dal Backend (simulationRoutes.js fixato) arrivano sempre 10 argomenti (script + 9 params)
        if len(sys.argv) >= 10:
            main_mode = int(sys.argv[1])
            nation = sys.argv[2]
            league = sys.argv[3]
            home_team = sys.argv[4] if sys.argv[4] != "null" else None
            away_team = sys.argv[5] if sys.argv[5] != "null" else None
            round_name = sys.argv[6] if sys.argv[6] != "null" else None
            algo_id = int(sys.argv[7])
            cycles = int(sys.argv[8])
            save_db = sys.argv[9].lower() == "true"
        else:
            # Fallback manuale CLI
            err = {"error": "Parametri insufficienti. Usa il frontend."}
            print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)


        start_time = datetime.now()
        
        # --- ESECUZIONE ---
        if main_mode == 4 and home_team and away_team: # SINGOLA
            result = run_single_simulation(home_team, away_team, league, round_name, algo_id, cycles)
            result["type"] = "single"
        
        elif main_mode in [1, 2, 3]: # MASSIVO (1=Prev, 2=Curr, 3=Next)
            result = run_massive_simulation(nation, league, algo_id, cycles, main_mode)
            
        else:
            result = {"success": False, "error": "Modalità non valida"}

        # OUTPUT
        output = {
            "success": result.get("success", False),
            "timestamp": datetime.now().isoformat(),
            "execution_time": (datetime.now() - start_time).total_seconds(),
            "params": {
                "main_mode": main_mode, "nation": nation, "league": league, 
                "algo_id": algo_id, "cycles": cycles
            },
            "result": result
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.stdout.flush()


    except Exception as e:
        err = {"success": False, "error": f"Critical Error: {str(e)}"}
        print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
        sys.stderr.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
