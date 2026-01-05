import os
import sys
import csv
import re
import json  # ✅ AGGIUNTO: Necessario per inviare i dati al sito web
from datetime import datetime, date
from collections import Counter
import statistics
import contextlib
import random

# --- GESTIONE PERCORSI FIREBASE (MODIFICATA) ---
# Forza lo script a vedere la cartella corrente e quella superiore
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# --- INIZIO GESTIONE IMPORT ---
try:
    from . import diagnostics
    from .deep_analysis import DeepAnalyzer
except (ImportError, ValueError):
    import diagnostics
    from deep_analysis import DeepAnalyzer
# --- FINE GESTIONE IMPORT ---

def tqdm(x):
    return x

import contextlib
import random



# --- CONFIGURAZIONI ---
MONTE_CARLO_TOTAL_CYCLES = 5000  # Default, sovrascritto dal menu
CSV_DELIMITER = ';'


def ask_monte_carlo_cycles(manual_cycles=None):
    """
    Versione Online: Non fa domande. 
    Usa il valore passato dal sito o il default di sistema.
    """
    if manual_cycles is not None:
        # Assicura che sia un multiplo di 4 per i 4 algoritmi
        adjusted = (int(manual_cycles) // 4) * 4
        return max(40, adjusted)
    
    return MONTE_CARLO_TOTAL_CYCLES


# --- HARD FIX PERCORSI ---
current_script_path = os.path.abspath(__file__)
ai_engine_dir = os.path.dirname(current_script_path)
project_root = os.path.dirname(ai_engine_dir)

if project_root not in sys.path: sys.path.insert(0, project_root)
if ai_engine_dir not in sys.path: sys.path.insert(0, ai_engine_dir)
if os.path.join(ai_engine_dir, 'engine') not in sys.path: sys.path.insert(0, os.path.join(ai_engine_dir, 'engine'))

try:
    # config.py nella root del progetto (già gestito con project_root)
    try:
        from config import db
    except ImportError:
        sys.path.append(project_root)
        from config import db

    # Moduli engine dentro ai_engine/engine
    from .engine import engine_core
    from .engine.engine_core import predict_match, preload_match_data
    from .engine.goals_converter import calculate_goals_from_engine, load_tuning

    # PredictionManager nello stesso package ai_engine
    try:
        from .prediction_manager import PredictionManager
        print("✅ [MANAGER] PredictionManager caricato.")
    except ImportError:
        PredictionManager = None
        print("⚠️ PredictionManager NON trovato (Salvataggio DB off).")

except ImportError as e:
    print(f"❌ ERRORE FATALE IMPORT: {e}")
    sys.exit(1)



# --- MAPPA NAZIONI ---
NATION_GROUPS = {
    "🇮🇹 ITALIA": ["Serie A", "Serie B", "Serie C - Girone A", "Serie C - Girone B", "Serie C - Girone C"],
    "🇬🇧 INGHILTERRA": ["Premier League"],
    "🇪🇸 SPAGNA": ["La Liga"],
    "🇩🇪 GERMANIA": ["Bundesliga"],
    "🇫🇷 FRANCIA": ["Ligue 1"],
    "🇳🇱 OLANDA": ["Eredivisie"],
    "🇵🇹 PORTOGALLO": ["Liga Portugal"]
}


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


def analyze_odds(match):
    """Calcola favorita bookmaker e colora quote per HTML"""
    odds = match.get("odds", {})
    if not odds or "1" not in odds:
        return '<span class="text-muted">-</span>', None, False
    try:
        q1 = float(odds.get("1", 0))
        qx = float(odds.get("X", 0))
        q2 = float(odds.get("2", 0))
        min_q = min(q1, qx, q2)
        fav_sign = "1" if q1 == min_q else ("2" if q2 == min_q else "X")
        
        s1 = f"<b>{q1:.2f}</b>" if fav_sign == "1" else f"{q1:.2f}"
        sx = f"<b>{qx:.2f}</b>" if fav_sign == "X" else f"{qx:.2f}"
        s2 = f"<b>{q2:.2f}</b>" if fav_sign == "2" else f"{q2:.2f}"
        
        return f"{s1} | {sx} | {s2}", fav_sign, True
    except:
        return '<span class="text-muted">Err</span>', None, False


# --- MOTORI ---
# SOSTITUISCI QUESTA FUNZIONE IN universal_simulator.py
def run_single_algo(algo_id, preloaded_data, home_name="Home", away_name="Away", settings_cache=None, debug_mode=True):
    """Esegue una singola simulazione (Ora supporta Turbo e Silenziatore)"""
    s_h, s_a, r_h, r_a = predict_match("", "", mode=algo_id, preloaded_data=preloaded_data)
    if s_h is None: return 0, 0

    gh, ga, *_ = calculate_goals_from_engine(
        s_h, s_a, r_h, r_a, 
        algo_mode=algo_id, 
        home_name=home_name, 
        away_name=away_name,
        settings_cache=settings_cache,  # <--- ADESSO ACCETTA IL TURBO
        debug_mode=debug_mode           # <--- ADESSO ACCETTA IL SILENZIATORE
    )
    return gh, ga

def run_single_algo_montecarlo(algo_id, preloaded_data, home_team, away_team, cycles=500, analyzer=None):
    """MonteCarlo per SINGOLO algoritmo"""
    local_results = []
    valid_cycles = 0
    
    # ⚡ 1. CARICAMENTO IN RAM (Fuori dal ciclo) ⚡
    settings_in_ram = load_tuning(algo_id)

    for cycle_idx in range(cycles):
        with suppress_stdout():
            s_h, s_a, r_h, r_a = predict_match(home_team, away_team, mode=algo_id, preloaded_data=preloaded_data)
            if s_h is None: continue
            
            # ⚡ 2. PASSIAMO LA CACHE (settings_cache=settings_in_ram) ⚡
            gh, ga, *_ = calculate_goals_from_engine(
                s_h, s_a, r_h, r_a, 
                algo_mode=algo_id, 
                home_name=home_team, 
                away_name=away_team,
                settings_cache=settings_in_ram, # <--- ECCO IL TURBO
                debug_mode=False                # 2. SILENZIATORE (Niente print inutili)
            )
            score = f"{gh}-{ga}"
            local_results.append(score)
            valid_cycles += 1
            
            if analyzer:
                analyzer.add_result(algo_id=algo_id, home_goals=gh, away_goals=ga)
        
        # 🔥 BARRA PROGRESSO CON FLUSH
        # ✅ FIX: Usiamo max(1, ...) per evitare la divisione per zero con pochi cicli
        # ✅ FIX: Qui usiamo "cycles" (senza _per_algo)
        if cycle_idx % max(1, cycles // 10) == 0 or cycle_idx == cycles - 1:
            pct = (cycle_idx + 1) / cycles * 100
            
    
    
    
    if not local_results:
        return 0, 0, []
    
    from collections import Counter
    top3 = Counter(local_results).most_common(3)
    final_score = top3[0][0]
    gh, ga = map(int, final_score.split("-"))
    
    return gh, ga, top3, local_results  # ← AGGIUNGI local_results



def run_monte_carlo_verdict_detailed(preloaded_data, home_team, away_team, analyzer=None, cycles=None, algo_id=None, **kwargs):
    """
    Versione SILENZIOSA con statistiche pesi aggregate.
    
    ✅ PARAMETRI NUOVI:
    - cycles: Numero di cicli totali da eseguire
    - algo_id: ID algoritmo da usare (se specificato, usa SOLO quello invece di tutti e 4)
    """
    
    nominees = []
    algos_stats = {}
    algos_full_results = {}
    algos_weights_tracking = {}
    algos_scontrini_tracking = {}
    
    # ✅ USA I CICLI PASSATI O IL DEFAULT
    total_cycles = cycles if cycles is not None else MONTE_CARLO_TOTAL_CYCLES
    
    # ✅ LOGICA ALGORITMI: Se algo_id è specificato, usa SOLO quello
    if algo_id is not None and algo_id != 6:
        # MODALITÀ SINGOLO ALGORITMO (quando l'utente sceglie 1, 2, 3, 4, o 5)
        algos = [algo_id]
        cycles_per_algo = total_cycles
        print(f"🎯 MODALITÀ SINGOLO ALGORITMO: Algo {algo_id} con {total_cycles} cicli", file=sys.stderr)
    else:
        # MODALITÀ MONTE CARLO (quando l'utente sceglie 6 o non specifica)
        algos = [2, 3, 4, 5]
        
        # PROTEZIONE DINAMICA: Usa len(algos) per contare automaticamente e max(1, ...) per evitare lo zero
        cycles_per_algo = max(1, total_cycles // len(algos))
        
        print(f"🎯 MODALITÀ MONTE CARLO: {len(algos)} algoritmi con {cycles_per_algo} cicli ciascuno", file=sys.stderr)
    
    tempo_stimato = total_cycles // 70
    
    print()
    
    algo_names = {2: 'Dinamico', 3: 'Tattico', 4: 'Caos', 5: 'Master'}
    
    for aid in algos:
        local_results = []
        weights_sum = {}
        params_sum = {}
        scontrini_sum = {'casa': {}, 'ospite': {}}
        valid_cycles = 0
        
        # ⚡ 1. CARICAMENTO IN RAM (Prima di iniziare i cicli di questo algoritmo) ⚡
        settings_in_ram = load_tuning(aid)
        
        for cycle_idx in range(cycles_per_algo):
            with suppress_stdout():
                s_h, s_a, r_h, r_a = predict_match(home_team, away_team, mode=aid, preloaded_data=preloaded_data)
                if s_h is None: continue
                
                # ⚡ 2. PASSIAMO LA CACHE (settings_cache=settings_in_ram) ⚡
                gh, ga, _, _, _, pesi_dettagliati, parametri, scontrino_casa, scontrino_ospite = calculate_goals_from_engine(
                    s_h, s_a, r_h, r_a, 
                    algo_mode=aid, 
                    home_name=home_team, 
                    away_name=away_team,
                    settings_cache=settings_in_ram, # <--- ECCO IL TURBO
                    debug_mode=False
                )
                
                score = f"{gh}-{ga}"
                local_results.append(score)
                valid_cycles += 1
                
                if analyzer:
                    analyzer.add_result(algo_id=aid, home_goals=gh, away_goals=ga)
                
                # Accumula pesi
                if pesi_dettagliati:
                    for nome_peso, info in pesi_dettagliati.items():
                        if nome_peso not in weights_sum:
                            weights_sum[nome_peso] = {
                                'base_sum': 0,
                                'multiplier_sum': 0,
                                'final_sum': 0,
                                'disabled_count': 0,
                                'count': 0
                            }
                        
                        weights_sum[nome_peso]['base_sum'] += info['weight_base']
                        weights_sum[nome_peso]['multiplier_sum'] += info['multiplier']
                        weights_sum[nome_peso]['final_sum'] += info['weight_final']
                        weights_sum[nome_peso]['disabled_count'] += (1 if info['is_disabled'] else 0)
                        weights_sum[nome_peso]['count'] += 1
                
                # Accumula parametri
                if parametri:
                    for nome_param, valore in parametri.items():
                        if nome_param not in params_sum:
                            params_sum[nome_param] = {'sum': 0, 'count': 0}
                        params_sum[nome_param]['sum'] += valore
                        params_sum[nome_param]['count'] += 1
                
                # Accumula scontrini
                if scontrino_casa:
                    for voce, dati in scontrino_casa.items():
                        if voce not in scontrini_sum['casa']:
                            scontrini_sum['casa'][voce] = {'valore_sum': 0, 'peso_sum': 0, 'punti_sum': 0}
                        scontrini_sum['casa'][voce]['valore_sum'] += dati.get('valore', 0)
                        scontrini_sum['casa'][voce]['peso_sum'] += dati.get('peso', 0)
                        scontrini_sum['casa'][voce]['punti_sum'] += dati.get('punti', 0)
                
                if scontrino_ospite:
                    for voce, dati in scontrino_ospite.items():
                        if voce not in scontrini_sum['ospite']:
                            scontrini_sum['ospite'][voce] = {'valore_sum': 0, 'peso_sum': 0, 'punti_sum': 0}
                        scontrini_sum['ospite'][voce]['valore_sum'] += dati.get('valore', 0)
                        scontrini_sum['ospite'][voce]['peso_sum'] += dati.get('peso', 0)
                        scontrini_sum['ospite'][voce]['punti_sum'] += dati.get('punti', 0)
            
            # Barra progresso
            if cycle_idx % max(1, cycles_per_algo // 10) == 0 or cycle_idx == cycles_per_algo - 1:
                pct = (cycle_idx + 1) / cycles_per_algo * 100
                bar_len = int(pct / 5)
                bar = "█" * bar_len + "░" * (20 - bar_len)
        
        if not local_results:
            continue
        
        # Calcola medie intelligenti
        if valid_cycles > 0:
            weights_avg = {}
            for nome_peso, dati in weights_sum.items():
                weights_avg[nome_peso] = {
                    'base': round(dati['base_sum'] / dati['count'], 3),
                    'multiplier': round(dati['multiplier_sum'] / dati['count'], 2),
                    'final': round(dati['final_sum'] / dati['count'], 3),
                    'disabled_pct': round((dati['disabled_count'] / dati['count']) * 100, 1)
                }
            
            params_avg = {}
            for nome_param, dati in params_sum.items():
                params_avg[nome_param] = round(dati['sum'] / dati['count'], 2)
            
            algos_weights_tracking[aid] = {'pesi': weights_avg, 'parametri': params_avg}
            
            # Calcola medie scontrini
            scontrini_avg = {'casa': {}, 'ospite': {}}
            for team in ['casa', 'ospite']:
                for voce, dati in scontrini_sum[team].items():
                    scontrini_avg[team][voce] = {
                        'valore': round(dati['valore_sum'] / valid_cycles, 2),
                        'peso': round(dati['peso_sum'] / valid_cycles, 2),
                        'punti': round(dati['punti_sum'] / valid_cycles, 2)
                    }
            algos_scontrini_tracking[aid] = scontrini_avg
        
        algos_full_results[aid] = local_results.copy()
        top_3 = Counter(local_results).most_common(3)
        algos_stats[aid] = top_3
        
        preview = ", ".join([f"{sc}({freq})" for sc, freq in top_3[:3]])
        
        for sc, freq in top_3:
            nominees.extend([sc] * freq)
    
    if not nominees:
        return (0, 0), {}, [], {}, {}
    
    final_verdict = random.choice(nominees)
    gh, ga = map(int, final_verdict.split("-"))
    global_top3 = Counter(nominees).most_common(3)
    
    # ✅ LOG FINALE PER VERIFICA
    print(f"✅ SIMULAZIONE COMPLETATA: {total_cycles} cicli eseguiti", file=sys.stderr)
    print(f"✅ ALGORITMO USATO: {algos}", file=sys.stderr)
    print(f"✅ RISULTATO FINALE: {gh}-{ga}", file=sys.stderr)
    
    # Salva debug JSON
    try:
        import json
        
        debug_data = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'match': f"{home_team} vs {away_team}",
            'risultato_finale': f"{gh}-{ga}",
            'algoritmi': {}
        }
        
        for aid in algos:
            if aid in algos_full_results:
                all_results = algos_full_results[aid]
                freq_counter = Counter(all_results)
                
                debug_data['algoritmi'][algo_names[aid]] = {
                    'totale_simulazioni': len(all_results),
                    'top_10': freq_counter.most_common(10),
                    'top_3_usati': algos_stats.get(aid, []),
                    'pesi_medi': algos_weights_tracking.get(aid, {}),
                    'scontrino_medio': algos_scontrini_tracking.get(aid, {})
                }
        
        with open("monte_carlo_debug.json", "w", encoding="utf-8") as f:
            json.dump(debug_data, f, indent=2, ensure_ascii=False)
    except:
        pass
    
    # ✅ MODIFICA: Restituisce anche total_cycles
    return (gh, ga), algos_stats, global_top3, algos_weights_tracking, algos_scontrini_tracking, total_cycles


def flow_single_match(nation=None, league=None, home=None, away=None, algo_id=6, cycles=1000):
    """
    Versione Online: Salta i menu e punta direttamente alla partita nel DB.
    """
    print(f"🔍 Ricerca automatica: {home} vs {away} ({league})", file=sys.stderr)
    
    # 1. Cerca la giornata nel DB h2h_by_round
    rounds_cursor = db.h2h_by_round.find({"league": league})
    rounds_list = list(rounds_cursor)
    
    if not rounds_list:
        return None, None, None

    # 2. Cerca la partita specifica tra tutti i round per trovare quella con i nomi giusti
    selected_match = None
    target_round_name = "N/A"
    
    for r in rounds_list:
        for m in r.get('matches', []):
            # Confronto nomi (senza spazi extra e minuscolo per sicurezza)
            if m['home'].strip().lower() == home.strip().lower():
                selected_match = m
                target_round_name = r.get('round_name', 'N/A')
                break
        if selected_match: break

    if not selected_match:
        print(f"❌ Partita {home} vs {away} non trovata nel database.", file=sys.stderr)
        return None, None, None

    # Prepara i dati per il simulatore
    selected_match['league'] = league
    selected_match['round'] = target_round_name
    
    # Restituisce i dati pronti per run_universal_simulator senza aver fatto una singola domanda
    return [selected_match], int(algo_id), int(cycles)
                
                
def analyze_result_dispersion(all_predictions):
    """
    Versione Online: Analizza la dispersione dei risultati senza stampare nulla.
    Restituisce solo i dati statistici puri.
    """
    all_results = []
    algo_analysis = {}
    
    for algo_name, pred_data in all_predictions.items():
        algo_results = None
        if isinstance(pred_data, dict):
            algo_results = pred_data.get('all_results')
            if not algo_results and 'top3' in pred_data:
                top3 = pred_data['top3']
                if top3 and isinstance(top3, list):
                    algo_results = []
                    for score, freq in top3:
                        algo_results.extend([score] * freq)
        elif isinstance(pred_data, tuple):
            if len(pred_data) >= 4:
                algo_results = pred_data[3]
            elif len(pred_data) >= 3:
                top3 = pred_data[2]
                if top3 and isinstance(top3, list):
                    algo_results = []
                    for score, freq in top3:
                        algo_results.extend([score] * freq)

        if not algo_results:
            continue

        signs_count = {'1': 0, 'X': 0, '2': 0}
        for score in algo_results:
            sign = get_sign(*map(int, score.split("-")))
            signs_count[sign] += 1
        
        total = len(algo_results)
        signs_pct = {'1': (signs_count['1']/total)*100, 'X': (signs_count['X']/total)*100, '2': (signs_count['2']/total)*100}
        
        pct_values = list(signs_pct.values())
        std_dev = statistics.stdev(pct_values) if len(pct_values) > 1 else 0
        
        algo_analysis[algo_name] = {
            'signs_pct': signs_pct,
            'std_dev': std_dev,
            'dominant_sign': max(signs_pct, key=signs_pct.get),
            'total_sims': total
        }
        all_results.extend(algo_results)
    
    if not all_results:
        return {'is_dispersed': False, 'all_results': []}
    
    global_signs_count = {'1': 0, 'X': 0, '2': 0}
    for score in all_results:
        sign = get_sign(*map(int, score.split("-")))
        global_signs_count[sign] += 1
    
    total_sims = len(all_results)
    global_signs_pct = {'1': (global_signs_count['1']/total_sims)*100, 'X': (global_signs_count['X']/total_sims)*100, '2': (global_signs_count['2']/total_sims)*100}
    global_std_dev = statistics.stdev(global_signs_pct.values())
    
    # Logica dispersione semplificata per il sito
    is_dispersed = global_std_dev < 20
    
    return {
        'is_dispersed': is_dispersed,
        'global_std_dev': round(global_std_dev, 2),
        'global_signs_pct': global_signs_pct,
        'all_results': all_results,
        'algo_analysis': algo_analysis
    }

# --- FUNZIONI DI STAMPA SILENZIATE ---
# Queste funzioni vengono mantenute per non rompere il resto del codice, 
# ma non stampano più nulla nel terminale.

def print_dispersion_warning(dispersion_analysis):
    pass

def print_single_match_summary(match, all_predictions, monte_carlo_data=None):
    pass

def print_massive_summary(matches_data, algo_name="MonteCarlo"):
    pass





def run_universal_simulator(mode=4, league=None, home=None, away=None, algo_id=6, cycles=1000):
    """
    Versione Online: Esegue la simulazione senza menu e restituisce i dati.
    """
    deep_analyzer = DeepAnalyzer()
    
    # 1. Recupero Partita (Usa la funzione silenziata che abbiamo creato nel Blocco 1)
    matches_to_process, selected_algo_id, total_cycles = flow_single_match(
        league=league, home=home, away=away, algo_id=algo_id, cycles=cycles
    )

    if not matches_to_process:
        print(json.dumps({"success": False, "error": "Partita non trovata"}), flush=True)
        return

    match = matches_to_process[0]
    
    # 2. Avvio Analizzatore
    deep_analyzer.start_match(
        home_team=match['home'],
        away_team=match['away'],
        league=match.get('league', 'Unknown'),
        date_str=match.get('date_iso')
    )    

    # 3. Esecuzione Simulazione (Monte Carlo)
    with suppress_stdout():
        preloaded = preload_match_data(match['home'], match['away'])
        
        # 🟢 AGGIUNGI QUESTE RIGHE: Risolviamo i nomi veri una volta sola
        # Estraiamo i nomi reali che il motore ha trovato durante il preload
        real_home = preloaded.get('home_team', match['home'])
        real_away = preloaded.get('away_team', match['away'])
        
        # Ora passiamo real_home e real_away invece di match['home']
        (mh, ma), algos_stats, global_top3, pesi_medi, scontrini_medi, cycles_executed = run_monte_carlo_verdict_detailed(
            preloaded, 
            real_home, # <--- NOME GIÀ RISOLTO
            real_away, # <--- NOME GIÀ RISOLTO
            analyzer=deep_analyzer,
            algo_id=selected_algo_id,
            cycles=total_cycles
        )
    
    deep_analyzer.end_match()

    # 4. Creazione Risultato Finale JSON per il Sito
    final_output = {
        "success": True,
        "match": f"{match['home']} vs {match['away']}",
        "prediction": f"{mh}-{ma}",
        "sign": get_sign(mh, ma),
        # ✅ Aggiungi solo questo per completezza (utile per debug manuale)
        "cycles_executed": cycles_executed,
        "probabilities": {
            "top_3": [{"score": s, "pct": round(f/sum([x[1] for x in global_top3])*100, 1)} for s, f in global_top3]
        },
        "deep_analysis": {
            "algo_details": algos_stats,
            "weights": pesi_medi
        }
    }

    # L'unica cosa che lo script stampa è il JSON finale
    print(json.dumps(final_output, indent=2, ensure_ascii=False), flush=True)

# --- AVVIO AUTOMATICO DA SITO WEB ---
if __name__ == "__main__":
    # Legge i parametri passati dal Portiere (main.py)
    # Esempio: python universal_simulator.py 4 "Serie A" "Inter" "Milan" 6 500
    if len(sys.argv) > 5:
        mode = int(sys.argv[1])
        league = sys.argv[2]
        home = sys.argv[3]
        away = sys.argv[4]
        algo = int(sys.argv[5])
        cycles = int(sys.argv[6]) if len(sys.argv) > 6 else 1000
        
        run_universal_simulator(mode, league, home, away, algo, cycles)
    else:
        # Se mancano parametri, chiude subito senza restare appeso
        error = {"success": False, "error": "Parametri mancanti per la simulazione"}
        print(json.dumps(error))
        sys.exit(1)