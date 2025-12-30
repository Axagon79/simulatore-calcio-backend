#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_simulator_A.py - VERSIONE DEFINITIVA PRO
Generatore di Match Anatomy, Cronaca Live e Report Scommesse (Localizzato in Italiano)
"""

import os
import sys
import json
import random
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
        get_round_number
    )
    from config import db
except ImportError as e:
    print(json.dumps({"success": False, "error": f"Errore Import: {e}"}), flush=True)
    sys.exit(1)

ALGO_NAMES = {1: "Statistico", 2: "Dinamico", 3: "Tattico", 4: "Caos", 5: "Master", 6: "MonteCarlo"}

def genera_match_report_completo(gh, ga, h2h_data, team_h, team_a, simulazioni_raw):
    """
    Genera l'anatomia della partita, la cronaca live e il report scommesse.
    Tutti i dati sono estratti dal DB e localizzati in italiano.
    """
    dna_h = h2h_data.get('h2h_dna', {}).get('home_dna', {})
    dna_a = h2h_data.get('h2h_dna', {}).get('away_dna', {})
    
    # --- 1. STATISTICHE AVANZATE (In Italiano) ---
    tec_h, tec_a = dna_h.get('tec', 50), dna_a.get('tec', 50)
    att_h, att_a = dna_h.get('att', 50), dna_a.get('att', 50)
    def_h, def_a = dna_h.get('def', 50), dna_a.get('def', 50)

    # Calcoli dinamici basati su DNA
    pos_h = max(35, min(65, int(50 + (tec_h - tec_a)/3 + random.randint(-2, 2))))
    pass_h = int(pos_h * 9.2) + random.randint(-15, 15)
    pass_a = int((100 - pos_h) * 8.8) + random.randint(-15, 15)
    
    tiri_h = int(att_h / 5) + random.randint(2, 7)
    tiri_a = int(att_a / 5) + random.randint(2, 7)
    sog_h = min(tiri_h, gh + random.randint(1, 4))
    sog_a = min(tiri_a, ga + random.randint(1, 4))

    stats_finali = {
        "Possesso Palla": [f"{pos_h}%", f"{100-pos_h}%"],
        "Possesso Palla (PT)": [f"{pos_h + random.randint(-3,3)}%", f"{100-pos_h + random.randint(-3,3)}%"],
        "Tiri Totali": [tiri_h, tiri_a],
        "Tiri in Porta": [sog_h, sog_a],
        "Tiri Fuori": [tiri_h - sog_h, tiri_a - sog_a],
        "Tiri Respinti": [random.randint(1, 5), random.randint(1, 5)],
        "Calci d'Angolo": [max(1, int(att_h/15)), max(1, int(att_a/15))],
        "Angoli (PT)": [random.randint(0, 3), random.randint(0, 3)],
        "Attacchi Pericolosi": [random.randint(30, 60), random.randint(30, 60)],
        "Passaggi Totali": [pass_h, pass_a],
        "Precisione Passaggi": [f"{random.randint(75, 92)}%", f"{random.randint(70, 88)}%"],
        "Falli": [random.randint(8, 18), random.randint(8, 18)],
        "Parate": [sog_a - ga, sog_h - gh],
        "Fuorigioco": [random.randint(0, 4), random.randint(0, 4)],
        "Pali Colpiti": [random.choice([0,0,1]), random.choice([0,0,1])],
        "Sostituzioni": [5, 5]
    }

    # --- 2. CRONACA LIVE (Timeline 0-90') ---
    cronaca = []
    titolari_h = h2h_data.get('formazioni', {}).get('home_squad', {}).get('titolari', [])
    titolari_a = h2h_data.get('formazioni', {}).get('away_squad', {}).get('titolari', [])

    def pick_player(squad, roles):
        pool = [p for p in squad if p.get('role') in roles] or squad
        return random.choice(pool).get('player', "Giocatore") if pool else "Giocatore"

    # Generazione Gol con nomi reali
    for _ in range(gh):
        cronaca.append({"minuto": random.randint(1, 90), "squadra": "casa", "tipo": "gol", "testo": f"⚽ GOL! {pick_player(titolari_h, ['ATT', 'MID'])}!"})
    for _ in range(ga):
        cronaca.append({"minuto": random.randint(1, 90), "squadra": "ospite", "tipo": "gol", "testo": f"⚽ GOL! {pick_player(titolari_a, ['ATT', 'MID'])}!"})
    
    # Ammonizioni
    for _ in range(random.randint(1, 4)):
        cronaca.append({"minuto": random.randint(10, 88), "squadra": random.choice(["casa", "ospite"]), "tipo": "cartellino", "testo": "🟨 Ammonizione per gioco falloso."})

    # --- 3. REPORT SCOMMESSE ---
    tot = len(simulazioni_raw)
    v_h = sum(1 for r in simulazioni_raw if int(r.split('-')[0]) > int(r.split('-')[1]))
    par = sum(1 for r in simulazioni_raw if int(r.split('-')[0]) == int(r.split('-')[1]))
    v_a = sum(1 for r in simulazioni_raw if int(r.split('-')[0]) < int(r.split('-')[1]))
    over = sum(1 for r in simulazioni_raw if sum(map(int, r.split('-'))) > 2.5)
    gg = sum(1 for r in simulazioni_raw if all(int(x) > 0 for x in r.split('-')))

    from collections import Counter
    top5 = Counter(simulazioni_raw).most_common(5)

    report_scommesse = {
        "Bookmaker": {
            "1": f"{round(v_h/tot*100, 1)}%", "X": f"{round(par/tot*100, 1)}%", "2": f"{round(v_a/tot*100, 1)}%",
            "U 2.5": f"{round((tot-over)/tot*100, 1)}%", "O 2.5": f"{round(over/tot*100, 1)}%",
            "GG": f"{round(gg/tot*100, 1)}%", "NG": f"{round((tot-gg)/tot*100, 1)}%",
            "1X": f"{round((v_h+par)/tot*100, 1)}%", "12": f"{round((v_h+v_a)/tot*100, 1)}%", "X2": f"{round((v_a+par)/tot*100, 1)}%"
        },
        "risultati_esatti_piu_probabili": [{"score": s, "pct": f"{round(f/tot*100, 1)}%"} for s, f in top5]
    }

    return {
        "statistiche": stats_finali,
        "cronaca": sorted(cronaca, key=lambda x: x['minuto']),
        "report_scommesse": report_scommesse
    }

def run_single_simulation(home_team: str, away_team: str, algo_id: int, cycles: int, league: str, main_mode: int) -> dict:
    """Esegue la simulazione e arricchisce il risultato con i dati del DB."""
    try:
        # Recupero dati contestuali dal DB (Teams e H2H)
        team_h_doc = db.teams.find_one({"name": home_team}) or {}
        team_a_doc = db.teams.find_one({"name": away_team}) or {}
        
        league_clean = league.replace('_', ' ').title()
        h2h_doc = db.h2h_by_round.find_one({"league": league_clean})
        match_data = next((m for m in h2h_doc.get('matches', []) if m['home'] == home_team), {})
        h2h_data = match_data.get('h2h_data', {})

        # Esecuzione Motore
        preloaded_data = preload_match_data(home_team, away_team)
        if not preloaded_data: return {"success": False, "error": "Dati DB insufficienti"}

        sim_list = []
        if algo_id == 6:
            import ai_engine.universal_simulator as us
            us.MONTE_CARLO_TOTAL_CYCLES = cycles
            res = run_monte_carlo_verdict_detailed(preloaded_data, home_team, away_team)
            gh, ga = res[0]
            sim_list = [f"{r[0]}-{r[1]}" for r in res[4]] if len(res) > 4 else [f"{gh}-{ga}"]*cycles
            top3 = [x[0] for x in res[2]]
        else:
            gh, ga = run_single_algo(algo_id, preloaded_data, home_team, away_team)
            sim_list = [f"{gh}-{ga}"] * cycles
            top3 = [f"{gh}-{ga}"]

        # Generazione Report Narrativo e Scommesse
        anatomy = genera_match_report_completo(gh, ga, h2h_data, team_h_doc, team_a_doc, sim_list)

        return {
            "success": True,
            "predicted_score": f"{gh}-{ga}",
            "gh": gh, "ga": ga,
            "sign": get_sign(gh, ga),
            "top3": top3,
            "algo_name": ALGO_NAMES.get(algo_id, "Custom"),
            "statistiche": anatomy["statistiche"],
            "cronaca": anatomy["cronaca"],
            "report_scommesse": anatomy["report_scommesse"],
            "info_extra": {
                "valore_mercato_casa": f"{team_h_doc.get('stats', {}).get('marketValue', 0) // 1000000}M €",
                "motivazione": team_h_doc.get('ranking_c', {}).get('motivation', 'N/D')
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def main():
    start_time = datetime.now()
    try:
        if len(sys.argv) < 10:
            print(json.dumps({"success": False, "error": "Parametri insufficienti"}), flush=True)
            return

        main_mode = int(sys.argv[1])
        league = sys.argv[3]
        home_team = sys.argv[4] if sys.argv[4] != "null" else None
        away_team = sys.argv[5] if sys.argv[5] != "null" else None
        algo_id = int(sys.argv[7])
        cycles = int(sys.argv[8])

        if main_mode == 4 and home_team and away_team:
            # ESECUZIONE BRIDGE
            result = run_single_simulation(home_team, away_team, algo_id, cycles, league, main_mode)
        else:
            result = {"success": False, "error": "Modalità supportata: Singola Match (4)"}

        # OUTPUT JSON PER APPDEV.TSX
        final_output = {
            "success": result.get("success", False),
            "timestamp": datetime.now().isoformat(),
            "execution_time": (datetime.now() - start_time).total_seconds(),
            "params": {"mode": main_mode, "league": league, "algo": algo_id, "cycles": cycles},
            "result": result 
        }
        print(json.dumps(final_output, ensure_ascii=False), flush=True)

    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}), flush=True)

if __name__ == "__main__":
    main()