#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WEB SIMULATOR CUPS - Simulatore partite Champions League & Europa League
Replica la logica di web_simulator_A.py ma per le coppe europee.

Usage:
    python web_simulator_CUPS.py <mode> <round> <competition> <home> <away> <null> <algo_id> <cycles>
    
Example:
    python web_simulator_CUPS.py 4 null UCL "Inter Milan" "Benfica" null 5 1000
"""

import os
import sys
import json
import math
import time
from datetime import datetime
import collections

# --- CONFIGURAZIONE PERCORSI ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # cups_engine
CUPS_DIR = os.path.dirname(CURRENT_DIR)  # cups
AI_ENGINE_DIR = os.path.dirname(CUPS_DIR)  # ai_engine
FUNCTIONS_PYTHON_DIR = os.path.dirname(AI_ENGINE_DIR)  # functions_python
PROJECT_ROOT = os.path.dirname(FUNCTIONS_PYTHON_DIR)  # simulatore-calcio-backend

# Aggiungi ai path
for path in [PROJECT_ROOT, FUNCTIONS_PYTHON_DIR, AI_ENGINE_DIR, CUPS_DIR, CURRENT_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

# --- IMPORT ---
try:
    from ai_engine.universal_simulator import (
        run_single_algo,
        run_single_algo_montecarlo,
        get_sign,
        load_tuning
    )
    from ai_engine.deep_analysis import DeepAnalyzer
    from config import db
    from ai_engine.calculators.bulk_manager import get_all_data_bulk_cups
    
    # ✅ IMPORT CRONACA (da web_simulator_A)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "web_simulator_A",
        os.path.join(AI_ENGINE_DIR, "web_simulator_A.py")  # ✅ CORRETTO
    )
    web_sim_a = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(web_sim_a)
    genera_match_report_completo = web_sim_a.genera_match_report_completo
    
except ImportError as e:
    print(json.dumps({"success": False, "error": f"Import Error: {e}"}), flush=True)
    sys.exit(1)

ALGO_NAMES = {1: "Statistico", 2: "Dinamico", 3: "Tattico", 4: "Caos", 5: "Master", 6: "MonteCarlo"}

# --- CONFIGURAZIONE COPPE ---
COMPETITIONS_CONFIG = {
    "UCL": {
        "name": "Champions League",
        "teams_collection": "teams_champions_league",
        "matches_collection": "matches_champions_league"
    },
    "UEL": {
        "name": "Europa League",
        "teams_collection": "teams_europa_league",
        "matches_collection": "matches_europa_league"
    }
}

# Range per normalizzazione (da update_cups_data.py)
ELO_MIN = 1300
ELO_MAX = 2047
BUFFER = 0.2

# --- FUNZIONI NORMALIZZAZIONE ---

def normalize_with_buffer(value, min_val, max_val, buffer=0.2):
    """
    Normalizza valore con buffer su scala 5-25
    
    Args:
        value: valore da normalizzare
        min_val: valore minimo del range
        max_val: valore massimo del range
        buffer: percentuale di buffer (default 20%)
    
    Returns:
        valore normalizzato tra 5 e 25
    """
    buffer_low = min_val * (1 - buffer)
    buffer_high = max_val * (1 + buffer)
    
    normalized = 5 + ((value - buffer_low) / (buffer_high - buffer_low)) * 20
    
    # Clamp tra 5 e 25
    return max(5, min(25, normalized))


def calculate_cup_rating(valore_rosa, elo, quota, rosa_min, rosa_max):
    """
    Calcola rating per una squadra di coppa usando la formula:
    - 20% Valore Rosa
    - 40% Quote pure
    - 40% ELO sporcato (75% ELO + 25% Quote)
    
    Args:
        valore_rosa: valore di mercato squadra (€)
        elo: rating ELO squadra
        quota: quota bookmaker per la squadra (es. 1.80)
        rosa_min: valore rosa minimo della competizione
        rosa_max: valore rosa massimo della competizione
    
    Returns:
        rating finale normalizzato (5-25)
    """
    # 1. VALORE ROSA (20%)
    rosa_norm = normalize_with_buffer(valore_rosa, rosa_min, rosa_max, BUFFER)
    componente_rosa = rosa_norm * 0.20
    
    # 2. QUOTE PURE (40%)
    prob = 1 / quota if quota > 0 else 0.5
    quota_norm = 5 + (prob * 20)
    componente_quota = quota_norm * 0.40
    
    # 3. ELO "SPORCATO" (40%)
    elo_norm = normalize_with_buffer(elo, ELO_MIN, ELO_MAX, BUFFER)
    elo_sporcato = (elo_norm * 0.75) + (quota_norm * 0.25)
    componente_elo = elo_sporcato * 0.40
    
    # RATING FINALE
    rating_finale = componente_rosa + componente_quota + componente_elo
    
    return round(rating_finale, 2)


def sanitize_data(data):
    """Rimuove NaN e Inf dai dati, converte datetime in stringa ISO"""
    if isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(v) for v in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return 0.0
    elif isinstance(data, datetime):
        return data.isoformat()
    return data


def build_cup_preloaded_data(team_h_doc, team_a_doc, match_doc, rosa_min, rosa_max, competition, bulk_cache):
    """
    Costruisce il dizionario preloaded_data per le coppe
    USANDO IL BULK_CACHE come i campionati (chiave della velocità!)
    """
    
    # Calcola rating usando la formula 20-40-40
    valore_rosa_h = team_h_doc.get('valore_rosa_transfermarkt', 0)
    valore_rosa_a = team_a_doc.get('valore_rosa_transfermarkt', 0)
    
    elo_h = team_h_doc.get('elo_rating', 1500)
    elo_a = team_a_doc.get('elo_rating', 1500)
    
    odds = match_doc.get('odds', {})
    quota_h = odds.get('home', 2.5)
    quota_a = odds.get('away', 2.5)
    
    rating_h = calculate_cup_rating(valore_rosa_h, elo_h, quota_h, rosa_min, rosa_max)
    rating_a = calculate_cup_rating(valore_rosa_a, elo_a, quota_a, rosa_min, rosa_max)
    
    # ✅ USA MASTER_DATA DAL BULK_CACHE (come i campionati!)
    home_name = team_h_doc.get('name')
    away_name = team_a_doc.get('name')
    
    master_data = bulk_cache.get('MASTER_DATA', {})
    team_h_master = master_data.get(home_name, {})
    team_a_master = master_data.get(away_name, {})
    
    # ✅ DEBUG AGGIUNTIVO
    print(f"🔍 [DEBUG BUILD] home_name='{home_name}', away_name='{away_name}'", file=sys.stderr)
    print(f"🔍 [DEBUG BUILD] MASTER_DATA keys: {list(master_data.keys())}", file=sys.stderr)
    print(f"🔍 [DEBUG BUILD] team_h_master keys: {list(team_h_master.keys())}", file=sys.stderr)
    print(f"🔍 [DEBUG BUILD] team_a_master keys: {list(team_a_master.keys())}", file=sys.stderr)
    print(f"🔍 [DEBUG BUILD] team_h_master formazioni: {team_h_master.get('formazioni', 'MISSING')}", file=sys.stderr)
    print(f"🔍 [DEBUG BUILD] team_a_master formazioni: {team_a_master.get('formazioni', 'MISSING')}", file=sys.stderr)
    
    # Costruisci preloaded_data compatibile con engine_core
    preloaded_data = {
        "league": competition,
        "home_team": home_name,
        "away_team": away_name,
        
        # Rating calcolati
        "rating_home": rating_h,
        "rating_away": rating_a,
        
        # Dati squadre
        "team_h": {
            "name": home_name,
            "valore_rosa": valore_rosa_h,
            "elo_rating": elo_h,
            "country": team_h_doc.get('country', 'Unknown')
        },
        "team_a": {
            "name": away_name,
            "valore_rosa": valore_rosa_a,
            "elo_rating": elo_a,
            "country": team_a_doc.get('country', 'Unknown')
        },
        
        # Quote
        "odds": odds,
        
        # Per compatibilità con engine_core (usa medie europee)
        "avg_home_league": 1.50,
        "avg_away_league": 1.20,
        "avg_goals": 2.70,
        
        # H2H
        "h2h_h": 0,
        "h2h_a": 0,
        "base_val": 2.5,
        
        # ✅ AGGIUNGI BULK_CACHE (come i campionati!)
        "bulk_cache": bulk_cache,
        # ✅ FORMAZIONI (dal MASTER_DATA nel bulk_cache)
        # Cerca nel MASTER_DATA usando anche gli alias
        "formazioni": {
            "home_squad": team_h_master.get('formazioni', {}),
            "away_squad": team_a_master.get('formazioni', {})
        },
        "home_raw": {
            'power': rating_h * 3,
            'attack': rating_h / 2.5,
            'defense': rating_h / 5.0,
            'motivation': 10.0,
            'strength_score': rating_h / 5.0,
            'rating': rating_h,
            'reliability': 5.0,
            'bvs': 0.0,
            'field_factor': 3.5,
            'lucifero': 12.5,
            'h2h_score': 0,
            'h2h_avg_goals': 1.2
        },
        "away_raw": {
            'power': rating_a * 3,
            'attack': rating_a / 2.5,
            'defense': rating_a / 5.0,
            'motivation': 10.0,
            'strength_score': rating_a / 5.0,
            'rating': rating_a,
            'reliability': 5.0,
            'bvs': 0.0,
            'field_factor': 3.5,
            'lucifero': 12.5,
            'h2h_score': 0,
            'h2h_avg_goals': 1.0
        },
        
        # H2H vuoto (non abbiamo storico coppe)
        "h2h_stats": {
            "home_wins": 0,
            "draws": 0,
            "away_wins": 0,
            "avg_goals_home": 1.5,
            "avg_goals_away": 1.2
        },
        
        # Metadati
        "competition": competition,
        "match_date": match_doc.get('match_date', 'Unknown'),
        "is_cup": True
    }
    
    return preloaded_data


def run_cup_simulation(competition, home_team, away_team, algo_id, cycles):
    """
    Simula una partita di coppa europea
    
    Args:
        competition: "UCL" o "UEL"
        home_team: nome squadra casa
        away_team: nome squadra trasferta
        algo_id: algoritmo da usare (1-6)
        cycles: numero cicli simulazione
    
    Returns:
        dict con risultato simulazione
    """
    start_time = time.time()
    
    try:
        # Valida competizione
        if competition not in COMPETITIONS_CONFIG:
            return {
                "success": False,
                "error": f"Competizione non valida: {competition}. Usa UCL o UEL."
            }
        
        config = COMPETITIONS_CONFIG[competition]
        
        # ✅ 1. CARICA BULK_CACHE (UNA VOLTA SOLA - CHIAVE DELLA VELOCITÀ!)
        print(f"📦 [CUPS] Caricamento bulk_cache per {competition}...", file=sys.stderr)
        bulk_cache = get_all_data_bulk_cups(home_team, away_team, competition)
        
        if not bulk_cache:
            return {
                "success": False,
                "error": "Errore nel caricamento bulk_cache"
            }
        
        # ✅ 2. ESTRAI DATI DAL BULK_CACHE (già caricati, zero latenza DB!)
        team_h_doc = None
        team_a_doc = None
        
        for team in bulk_cache['TEAMS']:
            name = team.get('name')
            aliases = team.get('aliases', [])
            if name == home_team or home_team in aliases:
                team_h_doc = team
            if name == away_team or away_team in aliases:
                team_a_doc = team
        
        if not team_h_doc or not team_a_doc:
            return {
                "success": False,
                "error": f"Squadre non trovate: {home_team} o {away_team}"
            }
        
        match_doc = bulk_cache['MATCH_DATA']
        
        if not match_doc:
            return {
                "success": False,
                "error": f"Partita non trovata: {home_team} vs {away_team} in {config['name']}"
            }
        
        normalization = bulk_cache['NORMALIZATION']
        
        # ✅ 3. COSTRUISCI PRELOADED_DATA usando dati del bulk_cache
        preloaded_data = build_cup_preloaded_data(
            team_h_doc, 
            team_a_doc, 
            match_doc,
            normalization['rosa_min'],
            normalization['rosa_max'],
            competition,
            bulk_cache  # ✅ AGGIUNGI!
        )
        
        # ✅ 4. CARICA I SETTINGS UNA VOLTA SOLA (CACHE)
        settings_cache = load_tuning(algo_id)
        
        # ✅ 5. ESEGUI SIMULAZIONE (identica ai campionati - veloce!)
        gh, ga, top3, sim_list = run_single_algo_montecarlo(
            algo_id=algo_id,
            preloaded_data=preloaded_data,
            home_team=home_team,
            away_team=away_team,
            cycles=cycles,
            analyzer=None,
            settings_cache=settings_cache
        )
        
        # ✅ 6. GENERA CRONACA E STATISTICHE
        try:
            # Prepara h2h_data nel formato atteso
            h2h_data_formatted = {
                "formazioni": preloaded_data.get("formazioni", {}),
                "home_team": home_team,
                "away_team": away_team
            }
            
            # Crea deep_stats mock con TUTTI i campi necessari
            deep_stats_mock = {
                'under_over': {},
                'exact_scores': {},
                'confidence': {
                    'global_confidence': 50,
                    'total_std': 2.0
                },
                'sign_1': {'pct': 0, 'count': 0},
                'sign_x': {'pct': 0, 'count': 0},
                'sign_2': {'pct': 0, 'count': 0},
                'gg': {'pct': 0, 'count': 0},
                'ng': {'pct': 0, 'count': 0},        # ✅ AGGIUNGI (No Goal)
                'gg_yes': {'pct': 0, 'count': 0},
                'gg_no': {'pct': 0, 'count': 0},
                'total_simulations': len(sim_list),
                'top_10_scores': []
            }
            # ✅ DEBUG: Verifica formazioni
            print(f"🔍 [DEBUG] preloaded_data keys: {list(preloaded_data.keys())}", file=sys.stderr)
            print(f"🔍 [DEBUG] formazioni in preloaded_data: {preloaded_data.get('formazioni', 'MISSING')}", file=sys.stderr)
            print(f"🔍 [DEBUG] h2h_data_formatted: {h2h_data_formatted}", file=sys.stderr)
            anatomy = genera_match_report_completo(
                gh, ga,
                h2h_data_formatted,  # h2h_data formattato
                team_h_doc,          # team_h_doc
                team_a_doc,          # team_a_doc
                sim_list,            # sim_list
                deep_stats_mock,     # deep_stats con struttura minima
                bulkcache=bulk_cache
            )
        except Exception as e:
            import traceback
            print(f"⚠️ [CUPS] Errore generazione cronaca: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            anatomy = {"statistiche": {}, "cronaca": []}
        
        # 7. COSTRUISCI RISULTATO
        execution_time = time.time() - start_time
        
        # 6. COSTRUISCI RISULTATO
        execution_time = time.time() - start_time
        
        result = {
            "success": True,
            "competition": config['name'],
            "predicted_score": f"{gh}-{ga}",
            "gh": gh,
            "ga": ga,
            "algo_name": ALGO_NAMES.get(algo_id, "Custom"),
            "algo_id": algo_id,
            "cycles_requested": cycles,
            "cycles_executed": len(sim_list),
            "execution_time": round(execution_time, 3),
            # ✅ AGGIUNGI CRONACA E STATISTICHE
            "statistiche": anatomy.get("statistiche", {}),
            "cronaca": anatomy.get("cronaca", []),
            "match_info": {
                "home_team": home_team,
                "away_team": away_team,
                "match_date": match_doc.get('match_date'),
                "odds": match_doc.get('odds', {})
            },
            "ratings": {
                "rating_home": preloaded_data['rating_home'],
                "rating_away": preloaded_data['rating_away'],
                "formula": "20% Rosa + 40% Quote + 40% ELO(75% ELO + 25% Quote)"
            },
            "teams_data": {
                "home": {
                    "valore_rosa": team_h_doc.get('valore_rosa_transfermarkt'),
                    "elo": team_h_doc.get('elo_rating'),
                    "country": team_h_doc.get('country')
                },
                "away": {
                    "valore_rosa": team_a_doc.get('valore_rosa_transfermarkt'),
                    "elo": team_a_doc.get('elo_rating'),
                    "country": team_a_doc.get('country')
                }
            },
            "simulations": {
                "total_runs": len(sim_list),
                "score_distribution": dict(collections.Counter(sim_list).most_common(10))
            }
        }
        
        return sanitize_data(result)
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "execution_time": time.time() - start_time
        }


def main():
    """Entry point per chiamata da web"""
    start_time = datetime.now()
    
    try:
        if len(sys.argv) < 9:
            print(json.dumps({
                "success": False, 
                "error": "Parametri insufficienti. Usage: mode round competition home away null algo_id cycles"
            }), flush=True)
            return
        
        # Parse argomenti (stesso formato di web_simulator_A)
        main_mode = int(sys.argv[1])      # 4 = singola partita
        # sys.argv[2] = round (non usato per coppe)
        competition = sys.argv[3]          # UCL o UEL
        home_team = sys.argv[4]
        away_team = sys.argv[5]
        # sys.argv[6] = null
        algo_id = int(sys.argv[7])
        cycles = int(sys.argv[8])
        
        if main_mode != 4:
            result = {
                "success": False,
                "error": "Solo modalità Singola (4) supportata per coppe"
            }
        else:
            result = run_cup_simulation(competition, home_team, away_team, algo_id, cycles)
        
        # Output JSON
        final_output = {
            "success": result.get("success", False),
            "timestamp": datetime.now().isoformat(),
            "execution_time": (datetime.now() - start_time).total_seconds(),
            **{k: v for k, v in result.items() if k != "success"}
        }
        
        print(json.dumps(final_output, ensure_ascii=False), flush=True)
        
    except Exception as e:
        print(json.dumps({
            "success": False,
            "error": f"Errore critico: {str(e)}"
        }), flush=True)


if __name__ == "__main__":
    main()