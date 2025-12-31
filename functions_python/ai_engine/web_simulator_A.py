#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_simulator_A.py - VERSIONE DEFINITIVA PRO (FULL STATS & BETTING)
Generatore di Match Anatomy, Cronaca Live e Report Scommesse (Italiano)
"""

import os
import sys
import json
import random
import math  # <--- AGGIUNGI QUESTA RIGA
from datetime import datetime


# --- CONFIGURAZIONE PERCORSI ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path: sys.path.insert(0, CURRENT_DIR)
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path: sys.path.insert(0, PROJECT_ROOT)

# --- IMPORT MOTORE E DB ---
try:
    from ai_engine.universal_simulator import (
        preload_match_data,
        run_single_algo,
        run_monte_carlo_verdict_detailed,
        get_sign,
        get_round_number,
        has_valid_results
    )
    from config import db
    from ai_engine.deep_analysis import DeepAnalyzer #
except ImportError as e:
    print(json.dumps({"success": False, "error": f"Import Error: {e}"}), flush=True)
    sys.exit(1)

ALGO_NAMES = {1: "Statistico", 2: "Dinamico", 3: "Tattico", 4: "Caos", 5: "Master", 6: "MonteCarlo"}

# --- FUNZIONE SALVAVITA PER EVITARE CRASH DA NaN ---
def sanitize_data(data):
    if isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(v) for v in data]
    elif isinstance(data, float):
        # Se è NaN (Not a Number) o Infinito, lo trasformiamo in 0.0
        if math.isnan(data) or math.isinf(data):
            return 0.0
    return data

def genera_match_report_completo(gh, ga, h2h_data, team_h, team_a, simulazioni_raw, deep_stats):
    """
    Genera l'anatomia della partita, la cronaca live e il report scommesse professionale.
    Include 30+ parametri statistici e localizzazione integrale in italiano.
    """
    dna_h = h2h_data.get('h2h_dna', {}).get('home_dna', {})
    dna_a = h2h_data.get('h2h_dna', {}).get('away_dna', {})
    
    # --- 1. GENERATORE STATISTICHE ULTRA-DETTAGLIATE (In Italiano) ---
    tec_h, tec_a = dna_h.get('tec', 50), dna_a.get('tec', 50)
    att_h, att_a = dna_h.get('att', 50), dna_a.get('att', 50)
    def_h, def_a = dna_h.get('def', 50), dna_a.get('def', 50)

    # Possesso e Passaggi
    pos_h = max(35, min(65, int(50 + (tec_h - tec_a)/3 + random.randint(-2, 2))))
    pass_h = int(pos_h * 9.2) + random.randint(-20, 20)
    pass_a = int((100 - pos_h) * 8.8) + random.randint(-20, 20)
    
    # Tiri e Pericolosità
    t_h = int(att_h / 5) + random.randint(2, 8)
    t_a = int(att_a / 5) + random.randint(2, 8)
    sog_h = min(t_h, gh + random.randint(1, 4))
    sog_a = min(t_a, ga + random.randint(1, 4))

    stats_finali = {
        "Possesso Palla": [f"{pos_h}%", f"{100-pos_h}%"],
        "Possesso Palla (PT)": [f"{pos_h + random.randint(-3,3)}%", f"{100-pos_h + random.randint(-3,3)}%"],
        "Tiri Totali": [t_h, t_a],
        "Tiri in Porta": [sog_h, sog_a],
        "Tiri Fuori": [t_h - sog_h, t_a - sog_a],
        "Tiri Respinti": [random.randint(1, 5), random.randint(1, 5)],
        "Calci d'Angolo": [max(1, int(att_h/12)), max(1, int(att_a/12))],
        "Angoli (PT)": [random.randint(0, 4), random.randint(0, 4)],
        "Attacchi": [random.randint(90, 115), random.randint(90, 115)],
        "Attacchi Pericolosi": [random.randint(35, 65), random.randint(35, 65)],
        "Passaggi Totali": [pass_h, pass_a],
        "Passaggi Riusciti": [int(pass_h * 0.82), int(pass_a * 0.79)],
        "Precisione Passaggi": [f"{random.randint(78, 92)}%", f"{random.randint(74, 88)}%"],
        "Falli": [random.randint(8, 18), random.randint(8, 18)],
        "Ammonizioni": [random.randint(0, 4), random.randint(0, 4)],
        "Parate": [sog_a - ga, sog_h - gh],
        "Fuorigioco": [random.randint(0, 4), random.randint(0, 4)],
        "Pali Colpiti": [random.choice([0,0,1]), random.choice([0,0,1])],
        "Tackle Totali": [random.randint(15, 25), random.randint(15, 25)],
        "Intercettazioni": [random.randint(10, 20), random.randint(10, 20)],
        "Dribbling": [random.randint(3, 12), random.randint(3, 12)],
        "Cross": [random.randint(5, 15), random.randint(5, 15)],
        "Lanci Lunghi": [random.randint(15, 30), random.randint(15, 30)],
        "Sostituzioni": [5, 5]
    }

    # --- 2. CRONACA LIVE (Timeline 0-90' con Nomi Reali) ---
    cronaca = []
    titolari_h = h2h_data.get('formazioni', {}).get('home_squad', {}).get('titolari', [])
    titolari_a = h2h_data.get('formazioni', {}).get('away_squad', {}).get('titolari', [])

    def pick_p(squad, role_list):
        pool = [p for p in squad if p.get('role') in role_list] or squad
        return random.choice(pool).get('player', "Giocatore") if pool else "Giocatore"

    for _ in range(gh):
        cronaca.append({"minuto": random.randint(1, 90), "squadra": "casa", "tipo": "gol", "testo": f"⚽ GOL! {pick_p(titolari_h, ['ATT', 'MID'])}!"})
    for _ in range(ga):
        cronaca.append({"minuto": random.randint(1, 90), "squadra": "ospite", "tipo": "gol", "testo": f"⚽ GOL! {pick_p(titolari_a, ['ATT', 'MID'])}!"})
    
    for _ in range(random.randint(1, 4)):
        cronaca.append({"minuto": random.randint(10, 88), "squadra": random.choice(["casa", "ospite"]), "tipo": "cartellino", "testo": "🟨 Ammonizione per gioco scorretto."})

    # --- 3. REPORT SCOMMESSE PROFESSIONALE ---
    tot = len(simulazioni_raw)
    v_h = sum(1 for r in simulazioni_raw if int(str(r).split('-')[0]) > int(str(r).split('-')[1]))
    par = sum(1 for r in simulazioni_raw if int(str(r).split('-')[0]) == int(str(r).split('-')[1]))
    v_a = sum(1 for r in simulazioni_raw if int(str(r).split('-')[0]) < int(str(r).split('-')[1]))
    over = sum(1 for r in simulazioni_raw if sum(map(int, str(r).split('-'))) > 2.5)
    gg = sum(1 for r in simulazioni_raw if all(int(x) > 0 for x in str(r).split('-')))

    from collections import Counter
    top5 = Counter(simulazioni_raw).most_common(5)

    # --- REPORT SCOMMESSE CON DATI DAL DEEP ANALYZER ---
    uo = deep_stats.get('under_over', {}) #
    conf = deep_stats.get('confidence', {}) #

    report_scommesse = {
        "Bookmaker": {
            "1": f"{deep_stats['sign_1']['pct']}%", #
            "X": f"{deep_stats['sign_x']['pct']}%", #
            "2": f"{deep_stats['sign_2']['pct']}%", #
            "1X": f"{round(deep_stats['sign_1']['pct'] + deep_stats['sign_x']['pct'], 1)}%", #
            "X2": f"{round(deep_stats['sign_2']['pct'] + deep_stats['sign_x']['pct'], 1)}%", #
            "12": f"{round(deep_stats['sign_1']['pct'] + deep_stats['sign_2']['pct'], 1)}%", #
            "U 2.5": f"{uo.get('U2.5', {}).get('pct', 0)}%", #
            "O 2.5": f"{uo.get('O2.5', {}).get('pct', 0)}%", #
            "GG": f"{deep_stats['gg']['pct']}%", #
            "NG": f"{deep_stats['ng']['pct']}%" #
        },
        "Analisi_Profonda": {
            "Confidence_Globale": f"{conf.get('global_confidence', 0)}%", #
            "Deviazione_Standard_Totale": conf.get('total_std', 0), #
            "Affidabilita_Previsione": f"{conf.get('total_confidence', 0)}%" #
        },
        "risultati_esatti_piu_probabili": [
            {"score": s, "pct": f"{round(c/deep_stats['total_simulations']*100, 1)}%"} 
            for s, c in deep_stats.get('top_10_scores', [])[:5] #
        ]
    }

    return {
        "statistiche": stats_finali,
        "cronaca": sorted(cronaca, key=lambda x: x['minuto']),
        "report_scommesse": report_scommesse
    }

def genera_anatomia_partita(gh, ga, h2h_match_data, team_h_doc, sim_list):
    """Genera statistiche dettagliate e report scommesse in italiano."""
    import random
    from collections import Counter
    
    h2h_data = h2h_match_data.get('h2h_data', {})
    dna_h = h2h_data.get('h2h_dna', {}).get('home_dna', {})
    dna_a = h2h_data.get('h2h_dna', {}).get('away_dna', {})
    
    # --- 1. CALCOLI PRELIMINARI (Necessari per il dizionario stats) ---
    tec_h, tec_a = dna_h.get('tec', 50), dna_a.get('tec', 50)
    att_h, att_a = dna_h.get('att', 50), dna_a.get('att', 50)
    
    # Possesso
    pos_h = max(35, min(65, int(50 + (tec_h - tec_a)/3 + random.randint(-2, 2))))
    
    # Tiri (Definiamo queste variabili PRIMA di usarle sotto)
    tiri_h = int(att_h / 5) + random.randint(2, 8)
    tiri_a = int(att_a / 5) + random.randint(2, 8)
    
    # Tiri in porta (SOG)
    sog_h = min(tiri_h, gh + random.randint(1, 4))
    sog_a = min(tiri_a, ga + random.randint(1, 4))

    # --- 2. DIZIONARIO STATISTICHE ---
    stats = {
        "Possesso Palla": [f"{pos_h}%", f"{100-pos_h}%"],
        "Possesso Palla (PT)": [f"{pos_h + random.randint(-2,2)}%", f"{100-pos_h + random.randint(-2,2)}%"],
        "Tiri Totali": [tiri_h, tiri_a],
        "Tiri in Porta": [sog_h, sog_a],
        "Tiri Fuori": [max(0, tiri_h - sog_h), max(0, tiri_a - sog_a)],
        "Tiri Respinti": [random.randint(1, 5), random.randint(1, 5)],
        "Calci d'Angolo": [max(1, int(att_h/12)), max(1, int(att_a/12))],
        "Angoli (PT)": [random.randint(0, 4), random.randint(0, 4)],
        "Attacchi Pericolosi": [random.randint(35, 65), random.randint(35, 65)],
        "Falli": [random.randint(8, 18), random.randint(8, 18)],
        "Ammonizioni": [random.randint(0, 4), random.randint(0, 4)],
        "Parate": [max(0, sog_a - ga), max(0, sog_h - gh)],
        "Pali Colpiti": [random.choice([0,0,1]), random.choice([0,0,1])],
        "Sostituzioni": [5, 5]
    }

    # --- 3. REPORT SCOMMESSE ---
    tot = len(sim_list)
    if tot == 0: tot = 1 # Evita divisione per zero
    
    v_h = sum(1 for r in sim_list if int(str(r).split('-')[0]) > int(str(r).split('-')[1]))
    par = sum(1 for r in sim_list if int(str(r).split('-')[0]) == int(str(r).split('-')[1]))
    v_a = sum(1 for r in sim_list if int(str(r).split('-')[0]) < int(str(r).split('-')[1]))
    over = sum(1 for r in sim_list if sum(map(int, str(r).split('-'))) > 2.5)
    gg = sum(1 for r in sim_list if all(int(x) > 0 for x in str(r).split('-')))
    
    report_bet = {
        "Bookmaker": {
            "1": f"{round(v_h/tot*100, 1)}%", "X": f"{round(par/tot*100, 1)}%", "2": f"{round(v_a/tot*100, 1)}%",
            "U 2.5": f"{round((tot-over)/tot*100, 1)}%", "O 2.5": f"{round(over/tot*100, 1)}%",
            "GG": f"{round(gg/tot*100, 1)}%", "NG": f"{round((tot-gg)/tot*100, 1)}%",
            "1X": f"{round((v_h+par)/tot*100, 1)}%", "12": f"{round((v_h+v_a)/tot*100, 1)}%", "X2": f"{round((v_a+par)/tot*100, 1)}%"
        },
        "risultati_esatti_piu_probabili": [{"score": s, "pct": f"{round(f/tot*100, 1)}%"} for s, f in Counter(sim_list).most_common(5)]
    }
    
    return stats, report_bet

def run_single_simulation(home_team: str, away_team: str, algo_id: int, cycles: int, league: str, main_mode: int) -> dict:
    """Esegue la simulazione e arricchisce il risultato con i dati del DB."""
    try:
        team_h_doc = db.teams.find_one({"name": home_team}) or {}
        team_a_doc = db.teams.find_one({"name": away_team}) or {}
        
        league_clean = league.replace('_', ' ').title()
        h2h_doc = db.h2h_by_round.find_one({"league": league_clean})
        match_data = next((m for m in h2h_doc.get('matches', []) if m['home'] == home_team), {})
        h2h_data = match_data.get('h2h_data', {})

        # 1. ESECUZIONE ALGORITMO E CREAZIONE sim_list
        sim_list = [] 
        preloaded_data = preload_match_data(home_team, away_team)
        
        if algo_id == 6:
            import ai_engine.universal_simulator as us
            us.MONTE_CARLO_TOTAL_CYCLES = cycles
            res = run_monte_carlo_verdict_detailed(preloaded_data, home_team, away_team)
            gh, ga = res[0]
            # Creazione sim_list dai risultati grezzi
            if len(res) > 4 and isinstance(res[4], list):
                sim_list = [f"{r[0]}-{r[1]}" for r in res[4]]
            else:
                sim_list = [f"{gh}-{ga}"] * cycles
            top3 = [x[0] for x in res[2]]
            cronaca = res[1] if len(res) > 1 else [] # Recupero cronaca se disponibile
        else:
            gh, ga = run_single_algo(algo_id, preloaded_data, home_team, away_team)
            sim_list = [f"{gh}-{ga}"] * cycles
            top3 = [f"{gh}-{ga}"]
            cronaca = []

        # 2. INTEGRAZIONE DEEP ANALYSIS
        analyzer = DeepAnalyzer()
        analyzer.start_match(home_team, away_team, league=league)
        for score in sim_list:
            h, a = map(int, score.split('-'))
            analyzer.add_result(algo_id, h, a)
        analyzer.end_match()
        
        # DEFINIZIONE DI deep_stats
        deep_stats = analyzer.matches[-1]['algorithms'][algo_id]['stats']

        # 3. GENERAZIONE REPORT
        # Usiamo la tua funzione esistente
        anatomy = genera_match_report_completo(gh, ga, h2h_data, team_h_doc, team_a_doc, sim_list, deep_stats)

        # Creazione dell'oggetto risultato
        raw_result = {
            "success": True,
            "predicted_score": f"{gh}-{ga}", "gh": gh, "ga": ga,
            "sign": get_sign(gh, ga), "top3": top3,
            "algo_name": ALGO_NAMES.get(algo_id, "Custom"),
            "statistiche": anatomy["statistiche"],
            "cronaca": anatomy["cronaca"],
            "report_scommesse": anatomy["report_scommesse"],
            "info_extra": {
                "valore_mercato": f"{team_h_doc.get('stats', {}).get('marketValue', 0) // 1000000}M €",
                "motivazione": team_h_doc.get('ranking_c', {}).get('motivation', 'N/D')
            }
        }

        # PULIZIA FINALE: Rimuove i NaN prima di inviare al frontend
        # 
        return sanitize_data(raw_result)

    except Exception as e:
        return {"success": False, "error": str(e)}

def main():
    start_time = datetime.now()
    try:
        if len(sys.argv) < 9:
            print(json.dumps({"success": False, "error": "Parametri insufficienti"}), flush=True)
            return

        main_mode = int(sys.argv[1])
        league = sys.argv[3]
        home_team = sys.argv[4]
        away_team = sys.argv[5]
        algo_id = int(sys.argv[7])
        cycles = int(sys.argv[8])

        if main_mode == 4 and home_team != "null":
            result = run_single_simulation(home_team, away_team, algo_id, cycles, league, main_mode)
        else:
            result = {"success": False, "error": "Solo modalità Singola (4) supportata"}

        # --- TROVA QUESTA PARTE NEL MAIN E SOSTITUISCILA ---
        final_output = {
            "success": result.get("success", False),
            "timestamp": datetime.now().isoformat(),
            "execution_time": (datetime.now() - start_time).total_seconds(),
            # Questo unisce tutto il contenuto di result al livello principale
            **{k: v for k, v in result.items() if k != "success"} 
        }
        
        print(json.dumps(final_output, ensure_ascii=False), flush=True)

    except Exception as e:
        print(json.dumps({"success": False, "error": f"Critico: {str(e)}"}), flush=True)

if __name__ == "__main__":
    main()