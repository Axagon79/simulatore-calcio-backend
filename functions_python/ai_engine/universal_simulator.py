import os
import sys
import csv
import re
from datetime import datetime, date
from collections import Counter
import statistics

# --- INIZIO GESTIONE IMPORT DUAL-MODE (LOCALE + FIREBASE) ---
try:
    # Tenta import relativo (Standard per Firebase/Package)
    from . import diagnostics
    from .deep_analysis import DeepAnalyzer
except ImportError:
    # Se fallisce (es. Script lanciato in locale da solo), usa import assoluto
    # Aggiunge la cartella padre al path per trovare i moduli
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import ai_engine.diagnostics as diagnostics
    from ai_engine.deep_analysis import DeepAnalyzer
# --- FINE GESTIONE IMPORT ---

def tqdm(x):
    return x

import contextlib
import random



# --- CONFIGURAZIONI ---
MONTE_CARLO_TOTAL_CYCLES = 5000  # Default, sovrascritto dal menu
CSV_DELIMITER = ';'


# --- FUNZIONE MENU CICLI ---
def ask_monte_carlo_cycles():
    """
    Menu interattivo per scegliere quanti cicli Monte Carlo eseguire.
    Restituisce il numero totale di cicli (divisibili per 4 algoritmi).
    """
    while True:
        print("\n" + "="*60)
        print("🎲 CONFIGURAZIONE MONTE CARLO")
        print("="*60)
        print("\n📊 PRESET VELOCITÀ (Cicli Totali / Per Algoritmo):\n")
        print("   [1] ⚡ TURBO       →    400 totali  (100 per algo)    ~10 sec")
        print("   [2] 🏃 RAPIDO      →  1,000 totali  (250 per algo)    ~20 sec")
        print("   [3] 🚶 VELOCE      →  2,000 totali  (500 per algo)    ~40 sec")
        print("   [4] ⚖️  STANDARD    →  5,000 totali  (1,250 per algo)  ~90 sec")
        print("   [5] 🎯 ACCURATO    → 10,000 totali  (2,500 per algo)  ~3 min")
        print("   [6] 🔬 PRECISO     → 20,000 totali  (5,000 per algo)  ~6 min")
        print("   [7] 💎 ULTRA       → 50,000 totali  (12,500 per algo) ~15 min")
        print("\n   [8] ✏️  PERSONALIZZATO (Inserisci numero manuale)")
        print("   [99] 🔙 ANNULLA\n")
        
        try:
            choice = int(input("   Scelta: ").strip())
        except ValueError:
            print("❌ Input non valido. Inserisci un numero.")
            continue
        
        if choice == 99:
            return None
        
        presets = {
            1: 400,
            2: 1000,
            3: 2000,
            4: 5000,
            5: 10000,
            6: 20000,
            7: 50000
        }
        
        if choice in presets:
            total = presets[choice]
            per_algo = total // 4
            
            print(f"\n✅ Selezionato: {total:,} cicli totali ({per_algo:,} per algoritmo)")
            confirm = input("   Confermi? [S/n]: ").strip().upper()
            if confirm in ['', 'S', 'Y', 'SI', 'YES']:
                return total
            else:
                continue
        
        elif choice == 8:
            while True:
                print("\n✏️  MODALITÀ PERSONALIZZATA")
                print("   Inserisci numero cicli totali (min: 40, max: 100,000)")
                print("   Nota: Verrà arrotondato al multiplo di 4 più vicino")
                
                try:
                    custom = int(input("\n   Cicli totali: ").strip())
                except ValueError:
                    print("❌ Inserisci un numero valido.")
                    continue
                
                if custom < 10:
                    print("❌ Minimo 40 cicli.")
                    continue
                if custom > 100000:
                    print("❌ Massimo 100,000 cicli.")
                    continue
                
                adjusted = (custom // 4) * 4
                if adjusted != custom:
                    print(f"⚠️  Arrotondato a {adjusted:,} (multiplo di 4)")
                
                per_algo = adjusted // 4
                tempo_stimato = adjusted // 60
                
                print(f"\n📊 Riepilogo:")
                print(f"   • Cicli totali:     {adjusted:,}")
                print(f"   • Per algoritmo:    {per_algo:,}")
                print(f"   • Tempo stimato:    ~{tempo_stimato} secondi")
                
                confirm = input("\n   Confermi? [S/n]: ").strip().upper()
                if confirm in ['', 'S', 'Y', 'SI', 'YES']:
                    return adjusted
                else:
                    break
        
        else:
            print("❌ Scelta non valida.")


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
    from .engine.goals_converter import calculate_goals_from_engine

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
def run_single_algo(algo_id, preloaded_data, home_name="Home", away_name="Away"):
    s_h, s_a, r_h, r_a = predict_match("", "", mode=algo_id, preloaded_data=preloaded_data)
    if s_h is None: return 0, 0

    gh, ga, *_ = calculate_goals_from_engine(
        s_h, s_a, r_h, r_a, 
        algo_mode=algo_id, 
        home_name=home_name, 
        away_name=away_name
    )
    return gh, ga

def run_single_algo_montecarlo(algo_id, preloaded_data, home_team, away_team, cycles=500, analyzer=None):
    """MonteCarlo per SINGOLO algoritmo - COPIA LOGICA run_monte_carlo_verdict_detailed"""
    local_results = []
    valid_cycles = 0
    
    print(f"🔄 Algo{algo_id} x {cycles:,} cicli...", end=" ", flush=True)
    
    for cycle_idx in range(cycles):
        with suppress_stdout():
            s_h, s_a, r_h, r_a = predict_match(home_team, away_team, mode=algo_id, preloaded_data=preloaded_data)
            if s_h is None: continue
            
            gh, ga, *_ = calculate_goals_from_engine(s_h, s_a, r_h, r_a, algo_mode=algo_id, home_name=home_team, away_name=away_team)
            score = f"{gh}-{ga}"
            local_results.append(score)
            valid_cycles += 1
            
            if analyzer:
                analyzer.add_result(algo_id=algo_id, home_goals=gh, away_goals=ga)
        
        # 🔥 BARRA PROGRESSO CON FLUSH
        if cycle_idx % max(1, cycles // 10) == 0 or cycle_idx == cycles - 1:
            pct = (cycle_idx + 1) / cycles * 100
            print(f"\r🔄 Algo{algo_id}: {pct:.0f}% ({valid_cycles} ok)", end="", flush=True)
    
    print(f"\r🔄 Algo{algo_id}: ✅ {valid_cycles} cicli completati", flush=True)
    
    if not local_results:
        return 0, 0, []
    
    from collections import Counter
    top3 = Counter(local_results).most_common(3)
    final_score = top3[0][0]
    gh, ga = map(int, final_score.split("-"))
    
    print(f" 📊 Top 3: {', '.join([f'{sc}({f})' for sc, f in top3])}", flush=True)
    return gh, ga, top3, local_results  # ← AGGIUNGI local_results



def run_monte_carlo_verdict_detailed(preloaded_data, home_team, away_team, analyzer=None):
    
    """
    Versione SILENZIOSA con statistiche pesi aggregate.
    """
    nominees = []
    algos_stats = {}
    algos_full_results = {}
    algos_weights_tracking = {}
    algos_scontrini_tracking = {}
    
    algos = [2, 3, 4, 5]
    cycles_per_algo = MONTE_CARLO_TOTAL_CYCLES // 4
    
    # 📊 STAMPA INFORMATIVA
    print(f"\n🎲 Monte Carlo: {MONTE_CARLO_TOTAL_CYCLES:,} simulazioni totali")
    print(f"   ({cycles_per_algo:,} per algoritmo)")
    
    tempo_stimato = MONTE_CARLO_TOTAL_CYCLES // 70
    if tempo_stimato < 60:
        print(f"   ⏱️  Tempo stimato: ~{tempo_stimato} secondi")
    else:
        minuti = tempo_stimato // 60
        secondi = tempo_stimato % 60
        print(f"   ⏱️  Tempo stimato: ~{minuti}m {secondi}s")
    print()
    
    algo_names = {2: 'Dinamico', 3: 'Tattico', 4: 'Caos', 5: 'Master'}
    
    for aid in algos:
        local_results = []
        weights_sum = {}
        params_sum = {}
        scontrini_sum = {'casa': {}, 'ospite': {}}
        valid_cycles = 0
        
        print(f"🔄 {algo_names[aid]}...", end=" ", flush=True)
        
        for cycle_idx in range(cycles_per_algo):
            with suppress_stdout():
                s_h, s_a, r_h, r_a = predict_match(home_team, away_team, mode=aid, preloaded_data=preloaded_data)
                if s_h is None: continue
                
                gh, ga, _, _, _, pesi_dettagliati, parametri, scontrino_casa, scontrino_ospite = calculate_goals_from_engine(
                    s_h, s_a, r_h, r_a, algo_mode=aid, home_name=home_team, away_name=away_team
                )
                
                score = f"{gh}-{ga}"
                local_results.append(score)
                valid_cycles += 1
                # ✨ AGGIUNGI QUESTA RIGA (subito dopo valid_cycles):
                if analyzer:
                    analyzer.add_result(algo_id=aid, home_goals=gh, away_goals=ga)
                # Accumula pesi (versione SMART)
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
            if cycle_idx % (cycles_per_algo // 10) == 0 or cycle_idx == cycles_per_algo - 1:
                pct = (cycle_idx + 1) / cycles_per_algo * 100
                bar_len = int(pct / 5)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                print(f"\r🔄 {algo_names[aid]}... {bar} {pct:.0f}%", end="", flush=True)
        
        print(f"  ✅ {valid_cycles} cicli")
        
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
        print(f"   📊 Top 3: {preview}")
        
        for sc, freq in top_3:
            nominees.extend([sc] * freq)
    
    if not nominees:
        return (0, 0), {}, [], {}, {}
    
    final_verdict = random.choice(nominees)
    gh, ga = map(int, final_verdict.split("-"))
    global_top3 = Counter(nominees).most_common(3)
    
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
    
    return (gh, ga), algos_stats, global_top3, algos_weights_tracking, algos_scontrini_tracking


# --- LOGICA NAVIGAZIONE GERARCHICA ---
def flow_single_match():
    """Gestisce il flusso Nazione -> Lega -> Giornata -> Partita -> Algoritmo."""
    
    while True:
        print("\n🌍 SELEZIONA NAZIONE:")
        nations_list = list(NATION_GROUPS.keys())
        for i, n in enumerate(nations_list):
            print(f"   [{i+1}] {n}")
        print("   [99] INDIETRO (Menu Principale)")
        
        try: n_sel = int(input("   Scelta: ").strip())
        except: continue
        
        if n_sel == 99: return None, None, None
        if n_sel < 1 or n_sel > len(nations_list): continue
        selected_nation = nations_list[n_sel-1]
        
        while True:
            possible_leagues = NATION_GROUPS[selected_nation]
            print(f"\n🏆 SELEZIONA CAMPIONATO ({selected_nation}):")
            for i, l in enumerate(possible_leagues):
                print(f"   [{i+1}] {l}")
            print("   [99] INDIETRO (Torna a Nazioni)")
            
            try: l_sel = int(input("   Scelta: ").strip())
            except: continue
            if l_sel == 99: break
            if l_sel < 1 or l_sel > len(possible_leagues): continue
            selected_league_name = possible_leagues[l_sel-1]

            while True:
                print(f"\n📅 SELEZIONA PERIODO ({selected_league_name}):")
                print("   [1] GIORNATA PRECEDENTE (Appena finita)")
                print("   [2] GIORNATA ATTUALE (In corso/Prossima)")
                print("   [3] GIORNATA SUCCESSIVA (Futura)")
                print("   [99] INDIETRO (Torna a Campionati)")

                try: d_sel = int(input("   Scelta: ").strip())
                except: continue
                if d_sel == 99: break
                
                OFFSET = 0
                if d_sel == 1: OFFSET = -1
                elif d_sel == 2: OFFSET = 0
                elif d_sel == 3: OFFSET = 1
                else: continue
            
                while True:
                    print(f"\n⚽ RECUPERO PARTITE PER: {selected_league_name}...")
                    rounds_cursor = db.h2h_by_round.find({"league": selected_league_name})
                    rounds_list = list(rounds_cursor)
                    if not rounds_list:
                        print("❌ Nessun dato trovato.")
                        break

                    rounds_list.sort(key=lambda x: get_round_number(x.get('round_name', '0')))
                    
                    anchor_index = -1
                    for i, r in enumerate(rounds_list):
                        if any(m.get('status') in ['Scheduled', 'Timed'] for m in r.get('matches', [])):
                            anchor_index = i
                            break
                    if anchor_index == -1:
                         for i in range(len(rounds_list) - 1, -1, -1):
                            if has_valid_results(rounds_list[i]):
                                anchor_index = i
                                break
                    
                    target_index = anchor_index + OFFSET if OFFSET != 0 else anchor_index
                    
                    if target_index < 0 or target_index >= len(rounds_list):
                        print(f"❌ Nessuna giornata trovata per l'offset selezionato.")
                        break

                    target_round = rounds_list[target_index]
                    matches = target_round.get('matches', [])
                    if not matches:
                        print("❌ Nessuna partita in questa giornata.")
                        break

                    print(f"📌 Giornata: {target_round.get('round_name')}")
                    print("\nPARTITE DISPONIBILI:")
                    for i, m in enumerate(matches):
                        real = f"[{m.get('real_score')}]" if m.get('real_score') else ""
                        q_info = ""
                        if m.get('odds') and '1' in m.get('odds'):
                            o1 = m['odds'].get('1', '-')
                            ox = m['odds'].get('X', '-')
                            o2 = m['odds'].get('2', '-')
                            q_info = f" [Q:{o1}|{ox}|{o2}]"
                        print(f"   [{i+1}] {m['home']} vs {m['away']} {real}{q_info}")

                    print("   [99] INDIETRO")

                    try: m_sel = int(input("   Scegli partita: ").strip())
                    except: continue
                    if m_sel == 99: break
                    if m_sel < 1 or m_sel > len(matches): continue

                    selected_match = matches[m_sel-1]
                    selected_match['league'] = selected_league_name
                    selected_match['round'] = target_round.get('round_name')
                    
                    print("\n🧠 SCELTA ALGORITMO:")
                    print("   [0] TUTTI (Report Completo)")
                    print("   [1] Statistico Puro")
                    print("   [2] Dinamico")
                    print("   [3] Tattico")
                    print("   [4] Caos")
                    print("   [5] Master")
                    print("   [6] MonteCarlo (Consigliato)")
                    print("   [7] CUSTOM (Algo + Cicli Manuali)")

                    # 🔥 FUNZIONE MENU CICLI (con indentazione corretta)
                    def show_cycles_menu(algo_name="Algoritmo"):
                        print(f"\n📊 PRESET VELOCITÀ ({algo_name}):")
                        presets = [
                            ("[1] ⚡ TURBO", 100, "~3 sec"),
                            ("[2] 🏃 RAPIDO", 250, "~6 sec"),
                            ("[3] 🚶 VELOCE", 500, "~12 sec"),
                            ("[4] ⚖️ STANDARD", 1250, "~30 sec"),
                            ("[5] 🎯 ACCURATO", 2500, "~60 sec"),
                            ("[6] 🔬 PRECISO", 5000, "~2 min"),
                            ("[7] 💎 ULTRA", 12500, "~5 min")
                        ]
                        for label, cycles, time in presets:
                            print(f"   {label} → {cycles:,} cicli    {time}")
                        print("   [8] ✏️  PERSONALIZZATO (Inserisci numero manuale)")
                        print("   [99] 🔙 ANNULLA")
                        return input("   Scelta: ").strip()

                    algo_names = {1: "Statistico Puro", 2: "Dinamico", 3: "Tattico", 4: "Caos", 5: "Master"}

                    try: 
                        algo_sel = int(input("   Scelta: ").strip())
                    except: 
                        algo_sel = 0

                    monte_carlo_cycles = None
                    if algo_sel == 6:
                        monte_carlo_cycles = ask_monte_carlo_cycles()
                        if monte_carlo_cycles is None:
                            continue
                    elif algo_sel in [1,2,3,4,5]:
                        algo_name = algo_names.get(algo_sel, "Tattico")
                        cycle_choice = show_cycles_menu(algo_name)
                        
                        if cycle_choice == '99':
                            continue
                        elif cycle_choice == '8':
                            cycles = int(input("Cicli (50-20000) [def=500]: ") or 500)
                            monte_carlo_cycles = cycles
                        else:
                            cycles_map = {'1':100, '2':250, '3':500, '4':1250, '5':2500, '6':5000, '7':12500}
                            cycles = cycles_map.get(cycle_choice, 500)
                            monte_carlo_cycles = cycles
                    elif algo_sel == 7:
                        print("\n🧠 SCELTA ALGORITMO CUSTOM:")
                        for i, name in algo_names.items():
                            print(f"   [{i}] {name}")
                        try:
                            custom_algo = int(input("   Algo (1-5): ").strip())
                        except:
                            custom_algo = 3  # Default Tattico
                        algo_name = algo_names.get(custom_algo, "Tattico")
                        cycle_choice = show_cycles_menu(algo_name)
                        
                        if cycle_choice == '99':
                            continue
                        elif cycle_choice == '8':
                            cycles = int(input("Cicli (50-20000) [def=500]: ") or 500)
                            monte_carlo_cycles = cycles
                            algo_sel = custom_algo
                        else:
                            cycles_map = {'1':100, '2':250, '3':500, '4':1250, '5':2500, '6':5000, '7':12500}
                            cycles = cycles_map.get(cycle_choice, 500)
                            monte_carlo_cycles = cycles
                            algo_sel = custom_algo

                    if 'monte_carlo_cycles' not in locals():
                        monte_carlo_cycles = None
                    
                    return [selected_match], algo_sel, monte_carlo_cycles
                
                
def analyze_result_dispersion(all_predictions):
    """
    Analizza la dispersione dei risultati usando DEVIAZIONE STANDARD.
    Conta TUTTI i risultati, non solo top3.
    
    Returns:
        dict con analisi dispersione basata su statistica reale
    """
    
    all_results = []  # Lista completa di TUTTI i risultati
    algo_analysis = {}
    
    # Raccogli TUTTI i risultati (non solo top3)
    for algo_name, pred_data in all_predictions.items():
        algo_results = None
        
        # (tolte le print di debug su type/keys/tuple)

        # Cerca 'all_results' PRIMA di top3
        if isinstance(pred_data, dict):
            algo_results = pred_data.get('all_results')
            # (tolta la print su all_results)

            if not algo_results and 'top3' in pred_data:
                top3 = pred_data['top3']
                if top3 and isinstance(top3, list):
                    algo_results = []
                    for score, freq in top3:
                        algo_results.extend([score] * freq)
                    # (tolta la print di FALLBACK)

        elif isinstance(pred_data, tuple):
            if len(pred_data) >= 4:
                algo_results = pred_data[3]
                # (tolta la print su all_results da tuple)
            elif len(pred_data) >= 3:
                top3 = pred_data[2]
                if top3 and isinstance(top3, list):
                    algo_results = []
                    for score, freq in top3:
                        algo_results.extend([score] * freq)
                    # (tolta la print di FALLBACK da tuple)

        if not algo_results:
            # (tolta la print "SKIP")
            continue

        
        print(f"   ✅ Processando {len(algo_results)} risultati")
        
        signs_count = {'1': 0, 'X': 0, '2': 0}
        for score in algo_results:
            sign = get_sign(*map(int, score.split("-")))
            signs_count[sign] += 1
        
        total = len(algo_results)
        signs_pct = {
            '1': (signs_count['1'] / total) * 100,
            'X': (signs_count['X'] / total) * 100,
            '2': (signs_count['2'] / total) * 100
        }
        
        pct_values = list(signs_pct.values())
        std_dev = statistics.stdev(pct_values) if len(pct_values) > 1 else 0
        
        dominant_sign = max(signs_pct, key=signs_pct.get)
        dominant_pct = signs_pct[dominant_sign]
        
        algo_analysis[algo_name] = {
            'results': algo_results,
            'signs_count': signs_count,
            'signs_pct': signs_pct,
            'std_dev': std_dev,
            'dominant_sign': dominant_sign,
            'dominant_pct': dominant_pct,
            'total_sims': total
        }
        
        all_results.extend(algo_results)
    
    if not all_results:
        return {
            'is_dispersed': False,
            'dispersion_score': 0,
            'conflicting_signs': False,
            'recommendation': None,
            'all_results': []
        }
    
    # Analisi globale
    global_signs_count = {'1': 0, 'X': 0, '2': 0}
    for score in all_results:
        sign = get_sign(*map(int, score.split("-")))
        global_signs_count[sign] += 1
    
    total_sims = len(all_results)
    global_signs_pct = {
        '1': (global_signs_count['1'] / total_sims) * 100,
        'X': (global_signs_count['X'] / total_sims) * 100,
        '2': (global_signs_count['2'] / total_sims) * 100
    }
    
    # Deviazione standard globale
    global_std_dev = statistics.stdev(global_signs_pct.values())
    
    # Determina segno dominante globale
    dominant_sign = max(global_signs_pct, key=global_signs_pct.get)
    dominant_pct = global_signs_pct[dominant_sign]
    
    # ========== LOGICA DISPERSIONE ==========
    
    # 1. BASSA DISPERSIONE (std_dev < 35): Un segno domina nettamente
    #    Esempio: 1=80%, X=15%, 2=5% → std=40.4 (concentrato)
    
    # 2. MEDIA DISPERSIONE (35 <= std_dev < 45): Due segni vicini
    #    Esempio: 1=50%, X=30%, 2=20% → std=15.3 (medio)
    
    # 3. ALTA DISPERSIONE (std_dev >= 45): Risultati equiprobabili
    #    Esempio: 1=40%, X=35%, 2=25% → std=7.6 (disperso)
    
    # NUOVO CRITERIO: usa std_dev ma considera anche dominanza
    is_dispersed = False
    conflicting_signs = False
    recommendation = None
    
    if global_std_dev > 45:
        # Concentrato su UN segno (es. 100%, 0%, 0%)
        # STD ALTO = buono!
        is_dispersed = False
        recommendation = None
        
    elif global_std_dev < 20:
        # Molto disperso (es. 33%, 33%, 33%)
        # STD BASSO = cattivo!
        is_dispersed = True
        conflicting_signs = True
        recommendation = "⚠️  ALTA IMPREVEDIBILITÀ - Risultati equiprobabili tra più segni. EVITARE scommesse 1X2."
        
    elif global_std_dev < 35:
        # Medio disperso
        # Controlla se ci sono 2 segni vicini
        sorted_pcts = sorted(global_signs_pct.values(), reverse=True)
        if sorted_pcts[0] - sorted_pcts[1] < 15:  # Top 2 sono vicini
            is_dispersed = True
            conflicting_signs = False
            recommendation = "⚠️  RISULTATI DISPERSI - Due segni competitivi. Considerare Under/Over o GG/NG."
    
    # Analisi PER ALGORITMO: controlla conflitti
    algo_conflicts = []
    if len(algo_analysis) > 1:
        # Controlla se algoritmi predicono segni OPPOSTI
        algo_signs = [data['dominant_sign'] for data in algo_analysis.values()]
        
        has_1 = '1' in algo_signs
        has_2 = '2' in algo_signs
        
        if has_1 and has_2:
            # Conflitto critico: alcuni dicono 1, altri dicono 2
            algo_conflicts.append("Algoritmi predicono segni opposti (1 vs 2)")
            conflicting_signs = True
            is_dispersed = True
            recommendation = "⚠️  ALGORITMI IN DISACCORDO - Alcuni predicono casa, altri trasferta. EVITARE 1X2."
    
    dispersion_score = 100 - (global_std_dev / 0.7)  # Normalizza 0-100
    dispersion_score = max(0, min(100, dispersion_score))
    
    return {
        'is_dispersed': is_dispersed,
        'dispersion_score': dispersion_score,
        'conflicting_signs': conflicting_signs,
        'recommendation': recommendation,
        'all_results': all_results,
        'global_signs_pct': global_signs_pct,
        'global_std_dev': global_std_dev,
        'dominant_sign': dominant_sign,
        'dominant_pct': dominant_pct,
        'algo_analysis': algo_analysis,
        'algo_conflicts': algo_conflicts
    }


def print_dispersion_warning(dispersion_analysis):
    """
    Stampa warning SOLO se realmente disperso.
    """
    if not dispersion_analysis['is_dispersed']:
        return
    
    print("\n" + "⚠️ " * 30)
    print("⚠️  ATTENZIONE: PARTITA AD ALTA VARIANZA RILEVATA")
    print("⚠️ " * 30)
    
    print(f"\n🔍 ANALISI DISPERSIONE:")
    print(f"   Deviazione Standard Segni: {dispersion_analysis['global_std_dev']:.1f}")
    print(f"   Score Imprevedibilità: {dispersion_analysis['dispersion_score']:.0f}/100")
    
    # Mostra distribuzione segni
    signs = dispersion_analysis['global_signs_pct']
    print(f"\n   📊 DISTRIBUZIONE SEGNI:")
    print(f"      1 (Casa):     {signs['1']:5.1f}%")
    print(f"      X (Pareggio): {signs['X']:5.1f}%")
    print(f"      2 (Trasferta):{signs['2']:5.1f}%")
    
    # Conflitti tra algoritmi
    if dispersion_analysis['algo_conflicts']:
        print(f"\n   🚨 CONFLITTI RILEVATI:")
        for conflict in dispersion_analysis['algo_conflicts']:
            print(f"      • {conflict}")
        
        # Dettaglio per algoritmo
        print(f"\n   🔬 PREDIZIONI PER ALGORITMO:")
        for algo, data in dispersion_analysis['algo_analysis'].items():
            dom_sign = data['dominant_sign']
            dom_pct = data['dominant_pct']
            print(f"      • {algo}: {dom_sign} ({dom_pct:.0f}%)")
    
    print(f"\n💡 RACCOMANDAZIONE:")
    print(f"   {dispersion_analysis['recommendation']}")
    if dispersion_analysis['conflicting_signs']:
        print(f"   ✅ Alternative sicure: UNDER/OVER 2.5 o GOL/NOGOL")
        print(f"   ❌ EVITARE scommesse 1X2 (troppo rischioso)")
    
    print("\n" + "⚠️ " * 30 + "\n")

    # ============================================
    # NUOVA FUNZIONE: Report per Singola Partita
    # ============================================

def print_single_match_summary(match, all_predictions, monte_carlo_data=None):
    """
    Stampa un report dettagliato per una singola partita.
    FOCUS: Confidenza basata su simulazioni reali, non su consenso algoritmi.
    
    Args:
        match: dict con dati partita (home, away, league, odds, real_score, ecc)
        all_predictions: dict {algo_name: (pred_gh, pred_ga, top3_optional)}
        monte_carlo_data: tuple (mh, ma, global_top3, algos_stats) oppure None
    """
    
    print("\n" + "="*90)
    print("📋 REPORT DETTAGLIATO PARTITA")
    print("="*90)
    
    # ========== INTESTAZIONE PARTITA ==========
    print(f"\n🏆 {match.get('league', 'Unknown League')}")
    print(f"📅 {match.get('date_str', 'Data N/D')}")
    print(f"⚽ {match['home']} vs {match['away']}")
    
    # Mostra risultato reale se disponibile
    if match.get('has_real'):
        real_sign = get_sign(match['real_gh'], match['real_ga'])
        print(f"✅ RISULTATO REALE: {match['real_gh']}-{match['real_ga']} ({real_sign})")
    else:
        print(f"⏳ PARTITA DA GIOCARE")
    
    # Mostra quote bookmaker
    book_sign = None
    book_prob_1x2 = None
    if match.get('odds') and '1' in match['odds']:
        try:
            q1 = float(match['odds'].get('1', 0))
            qx = float(match['odds'].get('X', 0))
            q2 = float(match['odds'].get('2', 0))
            
            # Calcola probabilità implicite bookmaker
            prob_1 = (1/q1) * 100 if q1 > 0 else 0
            prob_x = (1/qx) * 100 if qx > 0 else 0
            prob_2 = (1/q2) * 100 if q2 > 0 else 0
            
            min_q = min(q1, qx, q2)
            if min_q == q1:
                book_sign = '1'
                fav_name = match['home']
            elif min_q == q2:
                book_sign = '2'
                fav_name = match['away']
            else:
                book_sign = 'X'
                fav_name = 'Pareggio'
            
            book_prob_1x2 = {'1': prob_1, 'X': prob_x, '2': prob_2}
            
            print(f"\n📊 QUOTE BOOKMAKER:")
            print(f"   1={q1:.2f} ({prob_1:.0f}%) | X={qx:.2f} ({prob_x:.0f}%) | 2={q2:.2f} ({prob_2:.0f}%)")
            print( )
            print(f"   💰 FAVORITA: {fav_name} ({book_sign}) - Quota {min_q:.2f}")
        except:
            pass
    
    print("\n" + "-"*90)
    
    # ========== TABELLA PREDIZIONI ==========
    print("\n🔮 PREDIZIONI PER ALGORITMO:")
    print("-"*90)
    print(f"{'ALGORITMO':^15} {'SCORE':^10} {'SEGNO':^8} {'CONFIDENZA':^15} {'SIMULAZIONI':^15} {'MATCH REALE':^12}")
    print("-"*90)
    
    # Raccogli stats globali
    all_scores = []
    best_confidence = 0
    best_algo = None
    
    for algo_name, pred_data in all_predictions.items():
        gh, ga, top3, all_res = None, None, None, None
        
        if isinstance(pred_data, dict):
            gh = pred_data.get('pred_gh')
            ga = pred_data.get('pred_ga')
            top3 = pred_data.get('top3')
            all_res = pred_data.get('all_results')
            
        elif isinstance(pred_data, tuple) and len(pred_data) >= 2:
            gh, ga = pred_data[0], pred_data[1]
            top3 = pred_data[2] if len(pred_data) >= 3 else None
            all_res = pred_data[3] if len(pred_data) >= 4 else None
            
        
        if gh is None or ga is None:
            print(f"   ❌ SKIP: gh o ga sono None!")
            continue
        
        # ✅ CALCOLA SIGN SUBITO!
        sign = get_sign(gh, ga)
        
        # Calcola confidenza REALE dalle simulazioni
        confidence_str = "-"
        num_simulations = "-"
        
        # ✅ PRIORITÀ: Usa all_res se disponibile, altrimenti fallback a top3
        if all_res and isinstance(all_res, list):
            # CASO 1: Abbiamo TUTTI i risultati
            total_votes = len(all_res)
            
            signs_count = {'1': 0, 'X': 0, '2': 0}
            for score in all_res:
                s = get_sign(*map(int, score.split("-")))
                signs_count[s] += 1
            
            votes_for_sign = signs_count[sign]
            conf_sign = (votes_for_sign / total_votes * 100) if total_votes > 0 else 0
            
            from collections import Counter
            exact_counter = Counter(all_res)
            exact_votes = exact_counter.get(f"{gh}-{ga}", 0)
            conf_exact = (exact_votes / total_votes * 100) if total_votes > 0 else 0
            
            confidence_str = f"{conf_sign:.1f}% (1X2)"
            num_simulations = f"{total_votes} cicli"
            
            if conf_sign > best_confidence:
                best_confidence = conf_sign
                best_algo = algo_name
            
            all_scores.extend(all_res)
        
        elif top3 and isinstance(top3, list):
            # CASO 2: Solo top3 (fallback)
            total_votes = sum([f for s, f in top3])
            
            votes_for_sign = sum([f for s, f in top3 if get_sign(*map(int, s.split("-"))) == sign])
            conf_sign = (votes_for_sign / total_votes * 100) if total_votes > 0 else 0
            
            exact_votes = top3[0][1] if top3 and top3[0][0] == f"{gh}-{ga}" else 0
            conf_exact = (exact_votes / total_votes * 100) if total_votes > 0 else 0
            
            confidence_str = f"{conf_sign:.1f}% (top3)"
            num_simulations = f"~{total_votes} cicli"
            
            if conf_sign > best_confidence:
                best_confidence = conf_sign
                best_algo = algo_name
            
            for s, f in top3:
                all_scores.extend([s] * f)
        
        # Verifica vs reale
        match_real = ""
        if match.get('has_real'):
            real_sign = get_sign(match['real_gh'], match['real_ga'])
            match_real = "✅ OK" if sign == real_sign else "❌ MISS"
        
       # Riga dati (DENTRO il loop)
        print(
            f"{algo_name:^15} "
            f"{f'{gh}-{ga}':^10} "
            f"{sign:^8} "
            f"{confidence_str:^15} "
            f"{num_simulations:^15} "
            f"{match_real:^12}"
        )
        print("-"*90)
    
    # ========== RILEVAMENTO DISPERSIONE ==========
    dispersion_analysis = analyze_result_dispersion(all_predictions)
    if dispersion_analysis['is_dispersed'] or dispersion_analysis['conflicting_signs']:
        print_dispersion_warning(dispersion_analysis)
    
    # ========== ANALISI STATISTICA SIMULAZIONI ==========
    
    # Usa i risultati dall'analisi dispersione (che ha già raccolto TUTTO)
    if dispersion_analysis and dispersion_analysis['all_results']:
        all_scores = dispersion_analysis['all_results']
        from collections import Counter
        scores_counter = Counter(all_scores)
        total_sims = len(all_scores)
        
        print(f"\n📊 ANALISI STATISTICA ({total_sims:,} simulazioni totali):")
        print("-"*90)
        
        # Top 5 risultati più probabili
        top5_scores = scores_counter.most_common(5)
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        RED = "\033[91m"
        RESET = "\033[0m"

        # 🎨 NUOVO ALGORITMO COLORI
        first_result, first_freq = top5_scores[0]
        first_pct = (first_freq / total_sims) * 100
        first_sign = get_sign(*map(int, first_result.split("-")))

        top5_sum = sum(freq for _, freq in top5_scores)
        top5_sum_pct = (top5_sum / total_sims) * 100

        first_sign_pct = 0
        opposition_pct = 0
        for score, freq in top5_scores:
            sign = get_sign(*map(int, score.split("-")))
            pct = (freq / total_sims) * 100
            if sign == first_sign:
                first_sign_pct += pct
            else:
                opposition_pct += pct

        # COLORE PRIMO risultato
        if first_pct >= 20:
            primo_color = GREEN + "🟢" + RESET
        elif (first_pct >= 15 and top5_sum_pct >= 55 and opposition_pct <= 35):
            primo_color = GREEN + "🟢" + RESET
        elif first_pct >= 8 or top5_sum_pct >= 35:
            primo_color = YELLOW + "🟡" + RESET
        else:
            primo_color = RED + "🔴" + RESET

        print(f"\n   🎯 TOP 5 RISULTATI PIÙ PROBABILI:")
        # Calcola % per OGNI segno DENTRO i top5 (rispetto ai soli top5!)
        top5_total_freq = sum(freq for _, freq in top5_scores)
        segno1_pct = sum((freq/top5_total_freq*100) for score, freq in top5_scores if get_sign(*map(int, score.split("-"))) == '1')
        segnoX_pct = sum((freq/top5_total_freq*100) for score, freq in top5_scores if get_sign(*map(int, score.split("-"))) == 'X')
        segno2_pct = sum((freq/top5_total_freq*100) for score, freq in top5_scores if get_sign(*map(int, score.split("-"))) == '2')


        print(f"   📊 Primo: {primo_color} {first_pct:.1f}% | Top5: {top5_sum_pct:.1f}% | Opp: {opposition_pct:.1f}%")
        print(f"   📊 Segni TOP5: 1={segno1_pct:.0f}% | X={segnoX_pct:.0f}% | 2={segno2_pct:.0f}%")
        # 🔍 LOGICA SEGNO DOMINANTE INTELLIGENTE
        dominant_sign = max([('1', segno1_pct), ('X', segnoX_pct), ('2', segno2_pct)], key=lambda x: x[1])[0]
        dominant_pct = max(segno1_pct, segnoX_pct, segno2_pct)

        if dominant_pct >= 66:
            # Calcola primo risultato % RISPETTO al SUO segno dominante
            first_sign_results = sum(freq for score, freq in top5_scores 
                                if get_sign(*map(int, score.split("-"))) == first_sign)
            first_dominance = (first_freq / first_sign_results * 100) if first_sign_results > 0 else 0
            
            if first_dominance >= 25:
                primo_color = GREEN + "🟢⭐" + RESET
                print(f"   ⭐ {dominant_sign} DOMINA ({dominant_pct:.0f}%) + Primo leader ({first_dominance:.0f}%)!")
            else:
                print(f"   ⚠️ {dominant_sign} domina ({dominant_pct:.0f}%) MA primo debole ({first_dominance:.0f}%)")

        # NUOVA REGOLA: segno dominante ≥66% → VERDE
        if max(segno1_pct, segnoX_pct, segno2_pct) >= 66:
            primo_color = GREEN + "🟢⭐" + RESET  # Stelletta per "segno dominante"
            print(f"   ⭐ SEGNALE DOMINANTE RILEVATO!")


        for i, (score, freq) in enumerate(top5_scores, 1):
            prob = (freq / total_sims) * 100
            sign = get_sign(*map(int, score.split("-")))
            bar_len = int(prob // 2)
            bar = "█" * bar_len
            
            if prob >= 15: color = GREEN
            elif prob >= 8: color = YELLOW
            else: color = RED
            bar = color + bar + RESET
            
            print(f"   {i}. {score:<6} ({sign}) → {prob:5.2f}% {bar}")


        
        # USA LE PERCENTUALI GIÀ CALCOLATE da dispersion_analysis
        prob_1 = dispersion_analysis['global_signs_pct']['1']
        prob_x = dispersion_analysis['global_signs_pct']['X']
        prob_2 = dispersion_analysis['global_signs_pct']['2']
        
        print(f"\n   📈 PROBABILITÀ 1X2 (dalle simulazioni):")
        print(f"      1 (Vince {match['home']:<12}) → {prob_1:5.1f}%")
        print(f"      X (Pareggio)            → {prob_x:5.1f}%")
        print(f"      2 (Vince {match['away']:<12}) → {prob_2:5.1f}%")
        
        # Distribuzione Under/Over
        under_count = sum(freq for score, freq in scores_counter.items() if sum(map(int, score.split("-"))) <= 2.5)
        over_count = total_sims - under_count
        
        prob_under = (under_count / total_sims) * 100
        prob_over = (over_count / total_sims) * 100
        
        print(f"\n   📉 PROBABILITÀ UNDER/OVER 2.5:")
        print(f"      UNDER 2.5 → {prob_under:5.1f}%")
        print(f"      OVER 2.5  → {prob_over:5.1f}%")
        
        # Distribuzione GG/NG
        gg_count = sum(freq for score, freq in scores_counter.items() if all(int(x) > 0 for x in score.split("-")))
        ng_count = total_sims - gg_count
        
        prob_gg = (gg_count / total_sims) * 100
        prob_ng = (ng_count / total_sims) * 100
        
        print(f"\n   ⚽ PROBABILITÀ GOL/NOGOL:")
        print(f"      GG (Goal/Goal)   → {prob_gg:5.1f}%")
        print(f"      NG (NoGol)       → {prob_ng:5.1f}%")
        
        # ========== CONFRONTO CON BOOKMAKER ==========
        if book_prob_1x2:
            print(f"\n   💰 CONFRONTO IA vs BOOKMAKER:")
            print(f"      {'ESITO':<10} {'IA':<12} {'BOOKMAKER':<12} {'DIFFERENZA':<12} {'VALUE BET'}")
            print(f"      {'-'*60}")
            
            diff_1 = prob_1 - book_prob_1x2['1']
            diff_x = prob_x - book_prob_1x2['X']
            diff_2 = prob_2 - book_prob_1x2['2']
            
            # 1
            value_1 = "⭐ SÌ" if diff_1 > 10 else ""
            print(f"      {'1 (Casa)':<10} {prob_1:>5.1f}%      {book_prob_1x2['1']:>5.1f}%      {diff_1:>+5.1f}%       {value_1}")
            
            # X
            value_x = "⭐ SÌ" if diff_x > 10 else ""
            print(f"      {'X (Pareggio)':<10} {prob_x:>5.1f}%      {book_prob_1x2['X']:>5.1f}%      {diff_x:>+5.1f}%       {value_x}")
            
            # 2
            value_2 = "⭐ SÌ" if diff_2 > 10 else ""
            print(f"      {'2 (Trasferta)':<10} {prob_2:>5.1f}%      {book_prob_1x2['2']:>5.1f}%      {diff_2:>+5.1f}%       {value_2}")
            
            print(f"\n      ℹ️  Value Bet = IA stima probabilità >10% superiore al bookmaker")
        
        # ========== SUGGERIMENTI SCOMMESSE ==========
        print(f"\n" + "="*90)
        print(f"💡 SUGGERIMENTI SCOMMESSE (basati su {total_sims:,} simulazioni):")
        print("="*90)
        
        # Determina segno consigliato
        max_prob = max(prob_1, prob_x, prob_2)
        if max_prob == prob_1:
            rec_sign = '1'
            rec_name = match['home']
            rec_prob = prob_1
        elif max_prob == prob_2:
            rec_sign = '2'
            rec_name = match['away']
            rec_prob = prob_2
        else:
            rec_sign = 'X'
            rec_name = 'Pareggio'
            rec_prob = prob_x
        
        # SCOMMESSA 1X2 - Check dispersione PRIMA
        if dispersion_analysis['conflicting_signs']:
            # Caso CRITICO: algoritmi in conflitto
            print(f"\n   🔴 SCOMMESSA 1X2: FORTEMENTE SCONSIGLIATA")
            print(f"      ⚠️  Algoritmi predicono segni opposti")
            print(f"      ⚠️  Deviazione Standard: {dispersion_analysis['global_std_dev']:.1f}")
            print(f"      ❌ EVITARE questa scommessa")
            
        elif dispersion_analysis['is_dispersed']:
            # Caso MEDIO: risultati dispersi
            print(f"\n   🟡 SCOMMESSA 1X2: RISCHIOSA")
            print(f"      ⚠️  Risultati dispersi (std={dispersion_analysis['global_std_dev']:.1f})")
            print(f"      Esito: {rec_sign} ({rec_name})")
            print(f"      Probabilità IA: {rec_prob:.1f}%")
            print(f"      ⚠️  Procedere con cautela")
            
        else:
            # Caso NORMALE: usa probabilità
            if rec_prob >= 60:
                icon = "🟢"
                level = "CONSIGLIATA"
                conf_label = "ALTA"
            elif rec_prob >= 45:
                icon = "🟡"
                level = "POSSIBILE"
                conf_label = "MEDIA"
            else:
                icon = "🔴"
                level = "SCONSIGLIATA"
                conf_label = "BASSA"
            
            print(f"\n   {icon} SCOMMESSA 1X2: {level}")
            print(f"      Esito: {rec_sign} ({rec_name})")
            print(f"      Probabilità IA: {rec_prob:.1f}%")
            print(f"      Confidenza: {conf_label}")
            print(f"      Deviazione Standard: {dispersion_analysis['global_std_dev']:.1f} (concentrato)")
        
        if book_prob_1x2:
            diff = rec_prob - book_prob_1x2[rec_sign]
            print(f"      Probabilità Bookmaker: {book_prob_1x2[rec_sign]:.1f}%")
            if diff > 10:
                print(f"      ⭐ VALUE BET RILEVATO: +{diff:.1f}% rispetto al bookmaker")
            elif diff > 5:
                print(f"      💡 Lieve vantaggio: +{diff:.1f}% rispetto al bookmaker")
            elif diff < -10:
                print(f"      ⚠️  Bookmaker più ottimista: {diff:.1f}%")
        
        # UNDER/OVER
        print(f"\n   {'🟢' if prob_under >= 60 or prob_over >= 60 else '🟡'} SCOMMESSA UNDER/OVER 2.5:")
        if prob_under > prob_over:
            print(f"      Esito: UNDER 2.5")
            print(f"      Probabilità: {prob_under:.1f}%")
            print(f"      Confidenza: {'ALTA' if prob_under >= 60 else 'MEDIA'}")
        else:
            print(f"      Esito: OVER 2.5")
            print(f"      Probabilità: {prob_over:.1f}%")
            print(f"      Confidenza: {'ALTA' if prob_over >= 60 else 'MEDIA'}")
        
        # GOL/NOGOL
        print(f"\n   {'🟢' if prob_gg >= 60 or prob_ng >= 60 else '🟡'} SCOMMESSA GOL/NOGOL:")
        if prob_gg > prob_ng:
            print(f"      Esito: GG (Goal/Goal)")
            print(f"      Probabilità: {prob_gg:.1f}%")
            print(f"      Confidenza: {'ALTA' if prob_gg >= 60 else 'MEDIA'}")
        else:
            print(f"      Esito: NG (NoGol)")
            print(f"      Probabilità: {prob_ng:.1f}%")
            print(f"      Confidenza: {'ALTA' if prob_ng >= 60 else 'MEDIA'}")
        
        # RISULTATO ESATTO
        best_score, best_freq = top5_scores[0]
        best_exact_prob = (best_freq / total_sims) * 100
        
        if best_exact_prob >= 15:
            print(f"\n   🎯 RISULTATO ESATTO PIÙ PROBABILE:")
            print(f"      {best_score} → {best_exact_prob:.1f}% probabilità")
            if best_exact_prob >= 20:
                print(f"      💎 Probabilità eccezionalmente alta per risultato esatto!")
    
    else:
        # Nessuna simulazione disponibile
        print(f"\n⚠️  ATTENZIONE: Predizioni basate su calcolo singolo")
        print(f"   → Esegui algoritmi con cicli multipli (100+) per analisi statistiche")
        print(f"   → Raccomandato: Monte Carlo con 1000+ simulazioni")
    
    print("\n" + "="*90)


def print_massive_summary(matches_data, algo_name="MonteCarlo"):
    """
    Riepilogo intelligente con statistiche Monte Carlo reali.
    """
    if not matches_data:
        return
    
    print("\n" + "="*95)
    print(f"📊 RIEPILOGO GIORNATA - ALGORITMO: {algo_name.upper()}")
    print("="*95)
    
    # Raggruppa per campionato
    by_league = {}
    for item in matches_data:
        m = item['match']
        league = m.get('league', 'Unknown')
        if league not in by_league:
            by_league[league] = []
        by_league[league].append(item)
    
    # Stampa per ogni campionato
    for league, items in by_league.items():
        print(f"\n🏆 {league}")
        print("-" * 95)
        print(f"{'#':<3} {'PARTITA':<28} {'REALE':<10} {'PRONOSTICO':<10} {'SEGNO':<6} {'CONF%':<7} {'U/O':<8} {'GG/NG':<7} {'STATUS':<8}")
        print("-" * 110)  # ← Aumenta lunghezza
        
        for idx, item in enumerate(items, 1):
            m = item['match']
            ph = item['pred_gh']
            pa = item['pred_ga']
            
            # Nome partita
            match_name = f"{m['home'][:12]} vs {m['away'][:12]}"
            pred_score = f"{ph}-{pa}"
            sign = get_sign(ph, pa)
            
            # CALCOLA CONFIDENZA REALE (se disponibile top3)
            confidence = 0
            if 'top3' in item and item['top3']:
                top3 = item['top3']
                total_votes = sum([f for s, f in top3])
                
                # Confidenza sul segno previsto
                votes_for_sign = sum([f for s, f in top3 if get_sign(*map(int, s.split("-"))) == sign])
                confidence = (votes_for_sign / total_votes * 100) if total_votes > 0 else 0
            else:
                # Fallback: stima basica
                diff = abs(ph - pa)
                if sign == "X":
                    confidence = 30
                elif diff >= 2:
                    confidence = 65
                elif diff >= 1:
                    confidence = 50
                else:
                    confidence = 35
            
            # Under/Over
            total = ph + pa
            uo = "U2.5" if total <= 2.5 else "O2.5"
            
            # GG/NG
            gg = "GG" if (ph > 0 and pa > 0) else "NG"
            
            # Status con emoji
            if confidence >= 55:
                status = "🟢 OK"
            elif confidence >= 40:
                status = "🟡 MID"
            else:
                status = "🔴 LOW"
            
            # Verifica risultato reale
            real_icon = ""
            real_score_str = "-:-"  # Default se non disponibile
            if m.get('has_real'):
                real_score_str = f"{m['real_gh']}-{m['real_ga']}"  # ← AGGIUNGI QUESTO!
                pred_sign = sign
                real_sign = get_sign(m['real_gh'], m['real_ga'])
                real_icon = "✅" if pred_sign == real_sign else "❌"

            print(f"{idx:<3} {match_name:<28} {real_score_str:<10} {pred_score:<10} {sign:<6} {confidence:>5.1f}%  {uo:<8} {gg:<7} {status:<8} {real_icon}")
        
        print("-" * 110)
        
        # Statistiche campionato
        signs_1 = sum(1 for item in items if get_sign(item['pred_gh'], item['pred_ga']) == "1")
        signs_x = sum(1 for item in items if get_sign(item['pred_gh'], item['pred_ga']) == "X")
        signs_2 = sum(1 for item in items if get_sign(item['pred_gh'], item['pred_ga']) == "2")
        
        under = sum(1 for item in items if (item['pred_gh'] + item['pred_ga']) <= 2.5)
        over = sum(1 for item in items if (item['pred_gh'] + item['pred_ga']) > 2.5)
        
        gg_count = sum(1 for item in items if (item['pred_gh'] > 0 and item['pred_ga'] > 0))
        ng_count = len(items) - gg_count
        
        total_matches = len(items)
        
        print(f"📈 STATISTICHE: {total_matches} partite")
        print(f"   1X2: 1={signs_1} ({signs_1/total_matches*100:.0f}%) | X={signs_x} ({signs_x/total_matches*100:.0f}%) | 2={signs_2} ({signs_2/total_matches*100:.0f}%)")
        print(f"   U/O: Under={under} ({under/total_matches*100:.0f}%) | Over={over} ({over/total_matches*100:.0f}%)")
        print(f"   GG/NG: GG={gg_count} ({gg_count/total_matches*100:.0f}%) | NG={ng_count} ({ng_count/total_matches*100:.0f}%)")
        
        # Accuracy se disponibile
        verified = [item for item in items if item['match'].get('has_real')]
        if verified:
            correct = sum(1 for item in verified if get_sign(item['pred_gh'], item['pred_ga']) == get_sign(item['match']['real_gh'], item['match']['real_ga']))
            accuracy = (correct / len(verified)) * 100
            print(f"   ✅ ACCURATEZZA 1X2: {correct}/{len(verified)} ({accuracy:.1f}%)")
    
    print("\n" + "="*95)
    
    # ========== SUGGERIMENTI INTELLIGENTI ==========
    print("\n💡 SUGGERIMENTI INTELLIGENTI (Basati su Monte Carlo):")
    
    all_items = [item for items in by_league.values() for item in items]
    
    # 1. PARTITE PIÙ SICURE (confidenza >= 55%)
    safe_bets = []
    for item in all_items:
        if 'top3' in item and item['top3']:
            top3 = item['top3']
            total_votes = sum([f for s, f in top3])
            sign = get_sign(item['pred_gh'], item['pred_ga'])
            votes_for_sign = sum([f for s, f in top3 if get_sign(*map(int, s.split("-"))) == sign])
            confidence = (votes_for_sign / total_votes * 100) if total_votes > 0 else 0
            
            if confidence >= 55:
                safe_bets.append((item, confidence))
    
    if safe_bets:
        safe_bets.sort(key=lambda x: x[1], reverse=True)  # Ordina per confidenza
        print(f"\n   🟢 SCOMMESSE 1X2 CONSIGLIATE (Confidenza ≥55%):")
        for item, conf in safe_bets[:5]:
            m = item['match']
            sign = get_sign(item['pred_gh'], item['pred_ga'])
            winner = m['home'] if sign == "1" else (m['away'] if sign == "2" else "Pareggio")
            print(f"      • {m['home']} vs {m['away']} → {sign} ({winner}) - {conf:.0f}% confidenza")
    
    # 2. UNDER 2.5 CON ALTA CONFIDENZA
    under_bets = []
    for item in all_items:
        if 'top3' in item and item['top3']:
            top3 = item['top3']
            total_votes = sum([f for s, f in top3])
            
            # Conta voti per under
            votes_under = sum([f for s, f in top3 if sum(map(int, s.split("-"))) <= 2.5])
            conf_under = (votes_under / total_votes * 100) if total_votes > 0 else 0
            
            if conf_under >= 60:
                under_bets.append((item, conf_under))
    
    if under_bets:
        under_bets.sort(key=lambda x: x[1], reverse=True)
        print(f"\n   📉 UNDER 2.5 CONSIGLIATI (Confidenza ≥60%):")
        for item, conf in under_bets[:5]:
            m = item['match']
            total = item['pred_gh'] + item['pred_ga']
            print(f"      • {m['home']} vs {m['away']} → {item['pred_gh']}-{item['pred_ga']} ({total:.1f} gol) - {conf:.0f}%")
    
    # 3. GG CON ALTA CONFIDENZA
    gg_bets = []
    for item in all_items:
        if 'top3' in item and item['top3']:
            top3 = item['top3']
            total_votes = sum([f for s, f in top3])
            
            # Conta voti per GG
            votes_gg = sum([f for s, f in top3 if all(int(x) > 0 for x in s.split("-"))])
            conf_gg = (votes_gg / total_votes * 100) if total_votes > 0 else 0
            
            if conf_gg >= 60:
                gg_bets.append((item, conf_gg))
    
    if gg_bets:
        gg_bets.sort(key=lambda x: x[1], reverse=True)
        print(f"\n   ⚽ GOL/GOL CONSIGLIATI (Confidenza ≥60%):")
        for item, conf in gg_bets[:5]:
            m = item['match']
            print(f"      • {m['home']} vs {m['away']} → {item['pred_gh']}-{item['pred_ga']} - {conf:.0f}%")
    
    # 4. PARTITE DA EVITARE (confidenza bassa)
    avoid = []
    for item in all_items:
        if 'top3' in item and item['top3']:
            top3 = item['top3']
            total_votes = sum([f for s, f in top3])
            sign = get_sign(item['pred_gh'], item['pred_ga'])
            votes_for_sign = sum([f for s, f in top3 if get_sign(*map(int, s.split("-"))) == sign])
            confidence = (votes_for_sign / total_votes * 100) if total_votes > 0 else 0
            
            if confidence < 40:
                avoid.append((item, confidence))
    
    if avoid:
        avoid.sort(key=lambda x: x[1])  # Ordina per confidenza crescente
        print(f"\n   ⚠️  PARTITE DA EVITARE (Confidenza <40%):")
        for item, conf in avoid[:3]:
            m = item['match']
            print(f"      • {m['home']} vs {m['away']} → {item['pred_gh']}-{item['pred_ga']} - {conf:.0f}% (imprevedibile)")
    
    print("\n" + "="*95)
    
# ========================================
# REPORT RIEPILOGO GIORNATA MASSIVA
# ========================================
    
def print_massive_summary(matches_data, algo_name="MonteCarlo"):
    """
    Stampa un riepilogo compatto di tutte le partite simulate.
    matches_data: lista di dict con 'match' e predizioni
    """
    if not matches_data:
        return
    
    print("\n" + "="*90)
    print(f"📊 RIEPILOGO GIORNATA - ALGORITMO: {algo_name.upper()}")
    print("="*90)
    
    # Raggruppa per campionato
    by_league = {}
    for item in matches_data:
        m = item['match']
        league = m.get('league', 'Unknown')
        if league not in by_league:
            by_league[league] = []
        by_league[league].append(item)
    
    # Stampa per ogni campionato
    for league, items in by_league.items():
        print(f"\n🏆 {league}")
        print("-" * 95)
        print(f"{'#':<3} {'PARTITA':<28} {'REALE':<10} {'PRONOSTICO':<10} {'SEGNO':<6} {'CONF%':<7} {'U/O':<8} {'GG/NG':<7} {'STATUS':<8}")
        print("-" * 110)  # ← Aumenta lunghezza
        
        for idx, item in enumerate(items, 1):
            m = item['match']
            ph = item['pred_gh']
            pa = item['pred_ga']
            
            # Nome partita
            match_name = f"{m['home'][:12]} vs {m['away'][:12]}"
            pred_score = f"{ph}-{pa}"
            sign = get_sign(ph, pa)
            
            # CALCOLA CONFIDENZA REALE (se disponibile top3)
            confidence = 0
            if 'top3' in item and item['top3']:
                top3 = item['top3']
                total_votes = sum([f for s, f in top3])
                
                # Confidenza sul segno previsto
                votes_for_sign = sum([f for s, f in top3 if get_sign(*map(int, s.split("-"))) == sign])
                confidence = (votes_for_sign / total_votes * 100) if total_votes > 0 else 0
            else:
                # Fallback: stima basica
                diff = abs(ph - pa)
                if sign == "X":
                    confidence = 30
                elif diff >= 2:
                    confidence = 65
                elif diff >= 1:
                    confidence = 50
                else:
                    confidence = 35
            
            # Under/Over
            total = ph + pa
            uo = "U2.5" if total <= 2.5 else "O2.5"
            
            # GG/NG
            gg = "GG" if (ph > 0 and pa > 0) else "NG"
            
            # Status con emoji
            if confidence >= 55:
                status = "🟢 OK"
            elif confidence >= 40:
                status = "🟡 MID"
            else:
                status = "🔴 LOW"
            
            # Verifica risultato reale
            real_icon = ""
            real_score_str = "-:-"  # Default se non disponibile
            if m.get('has_real'):
                real_score_str = f"{m['real_gh']}-{m['real_ga']}"  # ← AGGIUNGI QUESTO!
                pred_sign = sign
                real_sign = get_sign(m['real_gh'], m['real_ga'])
                real_icon = "✅" if pred_sign == real_sign else "❌"

            print(f"{idx:<3} {match_name:<28} {real_score_str:<10} {pred_score:<10} {sign:<6} {confidence:>5.1f}%  {uo:<8} {gg:<7} {status:<8} {real_icon}")
        
        print("-" * 110)
        
        # Statistiche campionato
        signs_1 = sum(1 for item in items if get_sign(item['pred_gh'], item['pred_ga']) == "1")
        signs_x = sum(1 for item in items if get_sign(item['pred_gh'], item['pred_ga']) == "X")
        signs_2 = sum(1 for item in items if get_sign(item['pred_gh'], item['pred_ga']) == "2")
        
        under = sum(1 for item in items if (item['pred_gh'] + item['pred_ga']) <= 2.5)
        over = sum(1 for item in items if (item['pred_gh'] + item['pred_ga']) > 2.5)
        
        gg_count = sum(1 for item in items if (item['pred_gh'] > 0 and item['pred_ga'] > 0))
        ng_count = sum(1 for item in items if not (item['pred_gh'] > 0 and item['pred_ga'] > 0))
        
        total_matches = len(items)
        
        print(f"📈 STATISTICHE: {total_matches} partite")
        print(f"   1X2: 1={signs_1} ({signs_1/total_matches*100:.0f}%) | X={signs_x} ({signs_x/total_matches*100:.0f}%) | 2={signs_2} ({signs_2/total_matches*100:.0f}%)")
        print(f"   U/O: Under={under} ({under/total_matches*100:.0f}%) | Over={over} ({over/total_matches*100:.0f}%)")
        print(f"   GG/NG: GG={gg_count} ({gg_count/total_matches*100:.0f}%) | NG={ng_count} ({ng_count/total_matches*100:.0f}%)")
        
        # Se ci sono risultati reali, calcola accuracy
        verified = [item for item in items if item['match'].get('has_real')]
        if verified:
            correct = sum(1 for item in verified if get_sign(item['pred_gh'], item['pred_ga']) == get_sign(item['match']['real_gh'], item['match']['real_ga']))
            accuracy = (correct / len(verified)) * 100
            print(f"   ✅ ACCURATEZZA: {correct}/{len(verified)} ({accuracy:.1f}%)")
    
    print("\n" + "="*90)
    
    # SUGGERIMENTI GIORNATA
    print("\n💡 SUGGERIMENTI GIORNATA:")
    
    all_items = [item for items in by_league.values() for item in items]
    
    # Partite più sicure (diff >= 2 gol)
    safe_bets = [item for item in all_items if abs(item['pred_gh'] - item['pred_ga']) >= 2]
    if safe_bets:
        print(f"\n   🟢 PARTITE PIÙ SICURE (diff ≥ 2 gol):")
        for item in safe_bets[:5]:  # Max 5
            m = item['match']
            sign = get_sign(item['pred_gh'], item['pred_ga'])
            winner = m['home'] if sign == "1" else m['away']
            print(f"      • {m['home']} vs {m['away']} → {sign} ({winner})")
    
    # Partite under consigliati
    under_bets = [item for item in all_items if (item['pred_gh'] + item['pred_ga']) <= 1.5]
    if under_bets:
        print(f"\n   📉 UNDER 2.5 CONSIGLIATI:")
        for item in under_bets[:5]:
            m = item['match']
            total = item['pred_gh'] + item['pred_ga']
            print(f"      • {m['home']} vs {m['away']} → {item['pred_gh']}-{item['pred_ga']} ({total:.1f} gol)")
    
    # Partite GG consigliate
    gg_bets = [item for item in all_items if (item['pred_gh'] >= 1 and item['pred_ga'] >= 1)]
    if gg_bets:
        print(f"\n   ⚽ GOL/GOL CONSIGLIATI:")
        for item in gg_bets[:5]:
            m = item['match']
            print(f"      • {m['home']} vs {m['away']} → {item['pred_gh']}-{item['pred_ga']}")
    
    # Partite incerte (evitare)
    uncertain = [item for item in all_items if get_sign(item['pred_gh'], item['pred_ga']) == "X"]
    if uncertain:
        print(f"\n   ⚠️  PARTITE INCERTE (evitare scommesse 1X2):")
        for item in uncertain[:3]:
            m = item['match']
            print(f"      • {m['home']} vs {m['away']} → {item['pred_gh']}-{item['pred_ga']}")
    
    print("\n" + "="*90)


# --- LOGICA CORE ---
def run_universal_simulator():
    global MONTE_CARLO_TOTAL_CYCLES
    deep_analyzer = DeepAnalyzer()  # ← NUOVO!
    while True:
        print(f"\n" + "="*60)
        print(f"🌍 SIMULATORE UNIVERSALE (v6 - Total Edition + SafeGuard)")
        print(f"="*60)
        
        print("\n📅 MENU PRINCIPALE:")
        print("   [0] 💎 TOTAL SIMULATION (Tutti i campionati: SOLO PARTITE FINITE)")
        print("   [1] MASSIVO: Giornata Precedente")
        print("   [2] MASSIVO: Giornata In Corso")
        print("   [3] MASSIVO: Giornata Successiva")
        print("   [4] SINGOLA: Analisi Dettagliata (Nazione -> Lega -> Giornata -> Match)")
        print("   [99] ESCI")
        
        offsets_to_run = []
        MODE_SINGLE = False
        AUTO_ALL_LEAGUES = False
        ONLY_FINISHED = False
        selected_algo_id = 0
        
        try: main_choice = int(input("   Scelta: ").strip())
        except: continue

        if main_choice == 99: sys.exit(0)
        elif main_choice == 0:
            offsets_to_run = [-1, 0, 1] 
            AUTO_ALL_LEAGUES = True
            ONLY_FINISHED = True
            print("\n💎 MODALITÀ TOTAL (VERIFICA): Analisi partite CONCLUSE (con risultato) di Ieri, Oggi e Domani.")
        elif main_choice == 1: offsets_to_run = [-1]
        elif main_choice == 2: offsets_to_run = [0]
        elif main_choice == 3: offsets_to_run = [1]
        elif main_choice == 4: MODE_SINGLE = True
        else: 
            print("❌ Scelta non valida."); continue

        matches_to_process = []
        cycles_per_single_algo = None  # ← NUOVO: variabile per cicli custom

        if MODE_SINGLE:
            result = flow_single_match()
            if result is None or len(result) < 2:
                continue
            
            matches_to_process = result[0]
            selected_algo_id = result[1]
            
            # ✅ MODIFICATO: salva in variabile dedicata
            if len(result) >= 3 and result[2] is not None:
                cycles_per_single_algo = result[2]  # ← CAMBIATO
                print(f"\n⚙️ Configurato: {cycles_per_single_algo:,} cicli per algoritmo")
            else:
                cycles_per_single_algo = None  # ← CAMBIATO
            
            if not matches_to_process: 
                continue
        
        else:
            selected_leagues_names = []
            
            if AUTO_ALL_LEAGUES:
                selected_leagues_names = sorted(db.h2h_by_round.distinct("league"))
                print(f"📦 Caricamento automatico di {len(selected_leagues_names)} campionati...")
            else:
                # ========== MENU GERARCHICO NAZIONE → CAMPIONATO ==========
                while True:
                    print("\n🌍 SELEZIONA NAZIONE (Massivo):")
                    print("   [0] TUTTI I CAMPIONATI")
                    nations_list = list(NATION_GROUPS.keys())
                    for i, n in enumerate(nations_list, 1):
                        print(f"   [{i}] {n}")
                    print("   [99] INDIETRO (Menu Principale)")
                    
                    try:
                        n_choice = int(input("   Scelta: ").strip())
                    except:
                        continue
                    
                    if n_choice == 99:
                        break
                    
                    # Opzione TUTTI I CAMPIONATI
                    if n_choice == 0:
                        selected_leagues_names = sorted(db.h2h_by_round.distinct("league"))
                        print(f"\n📦 Selezionati TUTTI i {len(selected_leagues_names)} campionati disponibili")
                        break
                    
                    # Selezione Nazione
                    if 1 <= n_choice <= len(nations_list):
                        selected_nation = nations_list[n_choice - 1]
                        possible_leagues = NATION_GROUPS[selected_nation]
                        
                        # Menu Campionati della nazione
                        while True:
                            print(f"\n🏆 SELEZIONA CAMPIONATO ({selected_nation}):")
                            print("   [0] TUTTI I CAMPIONATI DI QUESTA NAZIONE")
                            for i, l in enumerate(possible_leagues, 1):
                                print(f"   [{i}] {l}")
                            print("   [99] INDIETRO (Torna a Nazioni)")
                            
                            try:
                                l_choice = int(input("   Scelta: ").strip())
                            except:
                                continue
                            
                            if l_choice == 99:
                                break  # Torna al menu nazioni
                            
                            if l_choice == 0:
                                # Tutti i campionati della nazione
                                selected_leagues_names = possible_leagues.copy()
                                print(f"\n📦 Selezionati tutti i {len(selected_leagues_names)} campionati di {selected_nation}")
                                break
                            
                            if 1 <= l_choice <= len(possible_leagues):
                                # Singolo campionato
                                selected_leagues_names = [possible_leagues[l_choice - 1]]
                                print(f"\n✅ Selezionato: {selected_leagues_names[0]}")
                                break
                        
                        # Se ha scelto un campionato, esci dal loop nazioni
                        if selected_leagues_names:
                            break
                
                if not selected_leagues_names:
                    continue
            
            # ========== MENU SCELTA ALGORITMO (DOPO SCELTA CAMPIONATO) ==========
            print("\n🧠 SCELTA ALGORITMO PER SIMULAZIONE MASSIVA:")
            print("   [0] TUTTI (Report Completo)")
            print("   [1] Statistico Puro")
            print("   [2] Dinamico")
            print("   [3] Tattico")
            print("   [4] Caos")
            print("   [5] Master")
            print("   [6] MonteCarlo (Consigliato)")
            
            try:
                selected_algo_id = int(input("   Scelta: ").strip())
            except:
                selected_algo_id = 6
            
            if selected_algo_id not in [0, 1, 2, 3, 4, 5, 6]:
                print("❌ Scelta non valida. Uso MonteCarlo.")
                selected_algo_id = 6
            
            # ========== MENU CICLI ==========
            cycles_per_single_algo = None
            algo_names = {1: "Statistico Puro", 2: "Dinamico", 3: "Tattico", 4: "Caos", 5: "Master"}
            
            # Algoritmo singolo (1-5)
            if selected_algo_id in [1, 2, 3, 4, 5]:
                algo_name = algo_names[selected_algo_id]
                
                print(f"\n📊 PRESET VELOCITÀ ({algo_name}):")
                print("   [1] ⚡ TURBO       →     100 cicli    ~3 sec/partita")
                print("   [2] 🏃 RAPIDO      →     250 cicli    ~6 sec/partita")
                print("   [3] 🚶 VELOCE      →     500 cicli    ~12 sec/partita")
                print("   [4] ⚖️  STANDARD   →   1,250 cicli    ~30 sec/partita")
                print("   [5] 🎯 ACCURATO    →   2,500 cicli    ~60 sec/partita")
                print("   [6] 🔬 PRECISO     →   5,000 cicli    ~2 min/partita")
                print("   [7] 💎 ULTRA       →  12,500 cicli    ~5 min/partita")
                print("   [8] ✏️  PERSONALIZZATO (Inserisci numero manuale)")
                print("   [99] 🔙 ANNULLA")
                
                try:
                    cycle_choice = int(input("   Scelta: ").strip())
                except:
                    cycle_choice = 3
                
                if cycle_choice == 99:
                    continue
                
                # Gestione cicli
                if cycle_choice == 8:
                    # PERSONALIZZATO
                    while True:
                        print("\n✏️  MODALITÀ PERSONALIZZATA")
                        print("   Inserisci numero cicli (min: 50, max: 20,000)")
                        
                        try:
                            custom_cycles = int(input("\n   Cicli: ").strip())
                        except ValueError:
                            print("❌ Inserisci un numero valido.")
                            continue
                        
                        if custom_cycles < 50:
                            print("❌ Minimo 50 cicli.")
                            continue
                        if custom_cycles > 20000:
                            print("❌ Massimo 20,000 cicli.")
                            continue
                        
                        cycles_per_single_algo = custom_cycles
                        tempo_stimato = custom_cycles // 50
                        
                        print(f"\n📊 Riepilogo:")
                        print(f"   • Cicli: {cycles_per_single_algo:,}")
                        print(f"   • Tempo stimato: ~{tempo_stimato} sec/partita")
                        break
                else:
                    # PRESET
                    cycles_map = {1: 100, 2: 250, 3: 500, 4: 1250, 5: 2500, 6: 5000, 7: 12500}
                    cycles_per_single_algo = cycles_map.get(cycle_choice, 500)
                
                print(f"\n✅ Selezionato: {cycles_per_single_algo:,} cicli per algoritmo {algo_name}")
                confirm = input("   Confermi? [S/n]: ").strip().upper()
                if confirm not in ['', 'S', 'Y', 'SI', 'YES']:
                    print("❌ Operazione annullata.")
                    continue
                
                print(f"\n⚙️  Configurato: {cycles_per_single_algo:,} cicli per {algo_name}")
            
            # Monte Carlo o TUTTI (0, 6)
            elif selected_algo_id in [0, 6]:
                print("\n⚠️  Stai per simulare MOLTE partite con Monte Carlo.")
                print("    Si consiglia modalità RAPIDA (1000 cicli) o VELOCE (2000 cicli)\n")
                
                mc_cycles = ask_monte_carlo_cycles()
                if mc_cycles is None:
                    print("❌ Operazione annullata.")
                    continue
                
                MONTE_CARLO_TOTAL_CYCLES = mc_cycles
                print(f"\n⚙️  Configurato: {MONTE_CARLO_TOTAL_CYCLES:,} cicli Monte Carlo")    
            print(f"\n🔍 Recupero partite (Periodi: {offsets_to_run})...")
            
            for league_name in selected_leagues_names:
                rounds_cursor = db.h2h_by_round.find({"league": league_name})
                rounds_list = list(rounds_cursor)
                if not rounds_list: continue
                rounds_list.sort(key=lambda x: get_round_number(x.get('round_name', '0')))
                
                anchor_index = -1
                for i, r in enumerate(rounds_list):
                    if any(m.get('status') in ['Scheduled', 'Timed'] for m in r.get('matches', [])):
                        anchor_index = i; break
                if anchor_index == -1:
                        for i in range(len(rounds_list) - 1, -1, -1):
                            if has_valid_results(rounds_list[i]): 
                                anchor_index = i; break
                
                for off in offsets_to_run:
                    target_index = anchor_index + off
                    if 0 <= target_index < len(rounds_list):
                        target_round = rounds_list[target_index]
                        r_name = target_round.get('round_name', 'Unknown')
                        
                        for m in target_round.get('matches', []):
                            
                            if ONLY_FINISHED:
                                s = m.get('real_score')
                                if not (s and isinstance(s, str) and ":" in s and s != "null"):
                                    continue

                            m_copy = m.copy()
                            m_copy['league'] = league_name
                            m_copy['round'] = r_name
                            matches_to_process.append(m_copy)

        if not matches_to_process:
            print("❌ Nessuna partita trovata (o nessuna partita conclusa, se in modalità Verifica).")
            continue

        final_matches_list = []
        for m in matches_to_process:
            real_s = m.get('real_score'); has_real = False; rh, ra = 0, 0
            if real_s and isinstance(real_s, str) and ":" in real_s and real_s != "null":
                try: rh, ra = map(int, real_s.split(":")); has_real = True
                except: pass
            
            d_obj = m.get('date_obj')
            d_str = d_obj.strftime("%d/%m %H:%M") if d_obj else "Data N/D"
            d_iso = d_obj.strftime("%Y-%m-%d") if d_obj else str(datetime.now().date())
            
            final_matches_list.append({
                "home": m['home'], "away": m['away'],
                "league": m.get('league', 'Unknown'), "round": m.get('round', '-'),
                "real_gh": rh, "real_ga": ra,
                "real_score_str": f"{rh}-{ra}" if has_real else "-",
                "has_real": has_real, "date_obj": d_obj, "date_str": d_str, "date_iso": d_iso,
                "status": m.get('status', 'Unknown'), "odds": m.get('odds', {}) 
            })

        if not MODE_SINGLE:
            print(f"\n📋 ANTEPRIMA ({len(final_matches_list)} partite):")
            limit_prev = 10 if not AUTO_ALL_LEAGUES else 5
            for m in final_matches_list[:limit_prev]:
                status_txt = f"[FINITA {m['real_score_str']}]" if m['has_real'] else "[DA GIOCARE]"
                print(f"   [{m['date_str']}] {m['home']} vs {m['away']} {status_txt}")
            if len(final_matches_list) > limit_prev:
                print(f"   ... e altre {len(final_matches_list)-limit_prev} partite")

        proceed_with_simulation = False
        save_to_db = False
        manager = None
        
        while True:
            print(f"\n⚙️ CONFIGURAZIONE AVVIO ({len(final_matches_list)} partite):")
            
            if PredictionManager:
                print("   [S] AVVIA e SALVA nel Database (Anti-Duplicati Attivo)")
            print("   [N] AVVIA SENZA salvare (Solo CSV)")
            print("   [99] ANNULLA e TORNA AL MENU")
            
            ans = input("   Scelta: ").strip().upper()
            
            if ans == '99':
                proceed_with_simulation = False
                break
            elif ans == 'N':
                save_to_db = False
                proceed_with_simulation = True
                break
            elif ans == 'S' and PredictionManager:
                save_to_db = True
                proceed_with_simulation = True
                
                if AUTO_ALL_LEAGUES:
                    print("   (Total Mode: Salvataggio automatico su SANDBOX)")
                    choice = '1'
                else:
                    while True:
                        choice = input("   Destinazione? [1] SANDBOX | [2] UFFICIALE: ").strip()
                        if choice in ['1', '2']: break
                        print("❌ Scelta errata.")
                
                manager = PredictionManager()
                manager.collection = db['predictions_official'] if choice == '2' else db['predictions_sandbox']
                break
            else:
                print("❌ Scelta non valida. Inserisci 'S', 'N' o '99'.")

        if not proceed_with_simulation:
            print("🔙 Operazione annullata. Ritorno al menu...")
            continue

        filename = "simulation_report.csv" if not AUTO_ALL_LEAGUES else "total_simulation_report.csv"
        print(f"\n⏳ Elaborazione in corso... Output: {filename}")
        print("DEBUG A - dopo messaggio Elaborazione")
        
        all_algos = ['Stat', 'Din', 'Tat', 'Caos', 'Master', 'MonteCarlo']
        data_by_algo = {name: [] for name in all_algos}
        
        algos_indices = []
        if selected_algo_id == 0: algos_indices = [1, 2, 3, 4, 5, 6]
        elif selected_algo_id == 6: algos_indices = [6]
        else: algos_indices = [selected_algo_id]

        iterator = tqdm(final_matches_list) if not MODE_SINGLE else final_matches_list
        
        for match in iterator:
            print()
            print(f"         INIZIO MATCH: {match['home']} vs {match['away']}")    
            if MODE_SINGLE: 
                print(f"\n⚡ ANALISI: {match['home']} vs {match['away']}...")
            deep_analyzer.start_match(
                home_team=match['home'],
                away_team=match['away'],
                real_result=match.get('real_score_str'),
                league=match.get('league', 'Unknown'),
                date_str=match.get('date_iso')
            )    
            
            with suppress_stdout():
                try: preloaded = preload_match_data(match['home'], match['away'])
                except:
                    print("DEBUG C1 - preload_match_data ha fatto eccezione, passo oltre")
                    continue
            

                            # 🔍 DEBUG NUMPY: Controlla dati preload_match_data
            if 'debug_data' in locals():
                print(f"🔍 preload keys: {list(preloaded.keys())}")
                for key in ['home_attack', 'away_attack', 'home_defense', 'away_defense']:
                    data = preloaded.get(key, [])
                    if not data:
                        print(f"⚠️ VUOTO: {key} = []")
                    elif len(data) == 1 or len(set(data)) == 1:
                        print(f"⚠️ ZERO VARIANZA: {key} = {data[:3]}...")

            # 🔥 SEMPRE - INIZIALIZZA PER TUTTI I CASI
            algo_preds_db = {}
            for aid in [i for i in algos_indices if i <= 5]:
                
                # ✅ LOGICA CICLI CORRETTA (SINGOLA E MASSIVA)
                if cycles_per_single_algo and cycles_per_single_algo > 1:
                    # Sia modalità singola CHE massiva con algoritmo specifico
                    cycles_to_run = cycles_per_single_algo
                    if MODE_SINGLE:
                        print(f"🔍 DEBUG: Uso {cycles_to_run} cicli custom per Algo {aid}")
                elif not MODE_SINGLE and MONTE_CARLO_TOTAL_CYCLES:
                    # Modalità massiva con Monte Carlo
                    cycles_to_run = MONTE_CARLO_TOTAL_CYCLES // 4
                else:
                    # Default: singola simulazione
                    cycles_to_run = 1
                
                # Esegui la simulazione con i cicli corretti
                if cycles_to_run > 1:
                    th, ta, top3, all_results = run_single_algo_montecarlo(
                        aid, preloaded, match['home'], match['away'], 
                        cycles=cycles_to_run, analyzer=deep_analyzer
                    )
                    
                    print(f"   Tipo: {type(all_results)}")
                    print(f"   Lunghezza: {len(all_results) if all_results else 'None'}")
                    if all_results:
                        print(f"   Primi 5: {all_results[:5]}")
                        from collections import Counter
                        debug_counter = Counter(all_results)
                        print(f"   Segni unici: {len(debug_counter)}")
                        signs_debug = {'1': 0, 'X': 0, '2': 0}
                        for score in all_results:
                            s = get_sign(*map(int, score.split("-")))
                            signs_debug[s] += 1
                        print(f"   Distribuzione segni: 1={signs_debug['1']}, X={signs_debug['X']}, 2={signs_debug['2']}")
                    
                    data_by_algo[all_algos[aid-1]].append({
                        'match': match, 
                        'pred_gh': th, 
                        'pred_ga': ta, 
                        'top3': top3,
                        'all_results': all_results  # ← AGGIUNGI
                    })
                else:
                    th, ta = run_single_algo(
                        aid, preloaded, 
                        home_name=match['home'], 
                        away_name=match['away']
                    )
                    data_by_algo[all_algos[aid-1]].append({
                        'match': match, 
                        'pred_gh': th, 
                        'pred_ga': ta
                    })
                
                algo_preds_db[f"Algo_{aid}"] = f"{th}-{ta}"
                
                if deep_analyzer and deep_analyzer.current_match:
                    deep_analyzer.add_result(algo_id=aid, home_goals=th, away_goals=ta)
                
                if MODE_SINGLE:
                    name = all_algos[aid-1]
                    if cycles_to_run > 1:
                        print(f" 🔹 {name}: {th}-{ta} ({get_sign(th, ta)}) [Media su {cycles_to_run:,} cicli]")
                    else:
                        print(f" 🔹 {name}: {th}-{ta} ({get_sign(th, ta)})")


            mh, ma = 0, 0

            pesi_medi = {}
            scontrini_medi = {}
            
            if 6 in algos_indices:
                (mh, ma), algos_stats, global_top3, pesi_medi, scontrini_medi = run_monte_carlo_verdict_detailed(
                    preloaded, match['home'], match['away'], 
                    analyzer=deep_analyzer
                )
                
                data_by_algo['MonteCarlo'].append({
                    'match': match, 
                    'pred_gh': mh, 
                    'pred_ga': ma,
                    'top3': global_top3,
                    'algos_stats': algos_stats
                })
                
                if MODE_SINGLE:
                    print(f"\n   🎲 MONTECARLO: {mh}-{ma} ({get_sign(mh, ma)})")
                    print(f"   📊 Top 3 Globale:")
                    for score, freq in global_top3:
                        pct = round(freq/sum([f for s,f in global_top3])*100, 1)
                        print(f"      • {score} → {pct}% ({freq} voti)")
                    
                    print(f"\n   🔬 Dettaglio per Algoritmo:")
                    algo_names_map = {2: 'Dinamico', 3: 'Tattico', 4: 'Caos', 5: 'Master'}
                    for aid, top3 in algos_stats.items():
                        print(f"      [{algo_names_map[aid]}] Top 3: {top3}")
            
                        
                    # ✨ STAMPA PESI
                    if pesi_medi:
                        print(f"\n   ⚖️  CONFIGURAZIONE PESI PER ALGORITMO:")
                        for aid, dati in pesi_medi.items():
                            print(f"\n      [{algo_names_map[aid]}]")
                            
                            pesi = dati.get('pesi', {})
                            parametri = dati.get('parametri', {})
                            
                            print(f"      📊 PESI VITTORIA:")
                            for nome, info in pesi.items():
                                base = info['base']
                                mult = info['multiplier']
                                final = info['final']
                                disabled = info['disabled_pct']
                                
                                if disabled > 0:
                                    status = f"🔴 DISATTIVATO ({disabled:.0f}%)"
                                elif mult > 1.5:
                                    status = f"🟢 AMPLIFICATO (x{mult:.1f})"
                                elif mult < 0.8:
                                    status = f"🟡 RIDOTTO (x{mult:.1f})"
                                else:
                                    status = f"⚪ NORMALE (x{mult:.1f})"
                                
                                print(f"      ├─ {nome:<18} → Base:{base:.2f} × {mult:.1f} = {final:.3f}  {status}")
                            
                            print(f"\n      ⚙️  PARAMETRI GOL:")
                            for nome, valore in parametri.items():
                                print(f"      ├─ {nome:<18} → {valore:.2f}")
                    
                    # ✨ STAMPA SCONTRINO MEDIO
                    if scontrini_medi:
                        cycles_per_algo = MONTE_CARLO_TOTAL_CYCLES // 4
                        print(f"\n   🧾 SCONTRINO MEDIO (Su {cycles_per_algo:,} simulazioni):")
                        for aid, scontrino in scontrini_medi.items():
                            print(f"\n   [{algo_names_map[aid]}]")
                            
                            # ✅ NOMI CON EMOJI
                            home_name = f"🏠 {match['home'][:10]}"  # Casa
                            away_name = f"✈️  {match['away'][:10]}"  # Trasferta
                            
                            print(f"   {'VOCE':<15} | {home_name + ' (V×P=Pt)':<28} | {away_name + ' (V×P=Pt)':<28}")
                            print("-" * 75)
                            
                            voci = set(list(scontrino.get('casa', {}).keys()) + list(scontrino.get('ospite', {}).keys()))
                            totale_casa = 0
                            totale_ospite = 0
                            
                            for voce in sorted(voci):
                                casa_data = scontrino.get('casa', {}).get(voce, {'valore': 0, 'peso': 0, 'punti': 0})
                                ospite_data = scontrino.get('ospite', {}).get(voce, {'valore': 0, 'peso': 0, 'punti': 0})
                                
                                casa_str = f"{casa_data['valore']:>5.2f} × {casa_data['peso']:>4.2f} = {casa_data['punti']:>6.2f}"
                                ospite_str = f"{ospite_data['valore']:>5.2f} × {ospite_data['peso']:>4.2f} = {ospite_data['punti']:>6.2f}"
                                
                                print(f"   {voce:<15} | {casa_str:<28} | {ospite_str:<28}")
                                
                                totale_casa += casa_data['punti']
                                totale_ospite += ospite_data['punti']
                            
                            print("-" * 75)
                            print(f"   {'TOTALE':<15} | {totale_casa:>28.2f} | {totale_ospite:>28.2f}")
                            print(f"   DIFFERENZA: {abs(totale_casa - totale_ospite):.2f} ({match['home'] if totale_casa > totale_ospite else match['away']} favorita)")
            # ========== REPORT DETTAGLIATO PARTITA SINGOLA ==========
            if MODE_SINGLE:
                # Raccogli tutte le predizioni
                single_predictions = {}
                
                # Predizioni algoritmi 1-5
                for aid in algos_indices:
                    if aid <= 5:
                        algo_name = all_algos[aid-1]
                        pred_data = data_by_algo.get(algo_name, [])
                        if pred_data:
                            last_pred = pred_data[-1]
                            gh = last_pred.get('pred_gh', 0)
                            ga = last_pred.get('pred_ga', 0)
                            top3 = last_pred.get('top3', None)
                            all_res = last_pred.get('all_results', None)  # ← AGGIUNGI QUESTA RIGA
                            
                            print(f"🔍 {algo_name}: all_results={len(all_res) if all_res else 'None'}")
                            
                            single_predictions[algo_name] = (gh, ga, top3, all_res)  # ← 4 VALORI!
                
                # Predizione Monte Carlo (se eseguito)
                mc_data_full = None
                if 6 in algos_indices and 'mh' in locals() and mh is not None:
                    single_predictions['MonteCarlo'] = (mh, ma, global_top3)
                    mc_data_full = (mh, ma, global_top3, algos_stats)
                
                # Stampa il report dettagliato
                if single_predictions:
                # 🔥 POPOLA all_predictions DAI DATI REALI (NOME GIUSTO)
                    all_predictions = {}
                    algo_map_name = {1: 'Statistico', 2: 'Dinamico', 3: 'Tattico', 4: 'Caos', 5: 'Master'}

                    for aid in algos_indices:
                        if aid <= 5:
                            internal_key = all_algos[aid-1]  # 'dynamic_balance', 'tactical_pattern', ecc.
                            if internal_key in data_by_algo and data_by_algo[internal_key]:
                                last_pred = data_by_algo[internal_key][-1]
                                display_name = algo_map_name[aid]
                                all_predictions[display_name] = last_pred  # 'Dinamico', 'Tattico' per la tabella

                    print_single_match_summary(match, all_predictions, mc_data_full)


            
                    
            deep_analyzer.end_match()        
            if save_to_db and manager:
                d_str_iso = match['date_iso']
                
                snap = {
                    "home_att": 0, "away_att": 0,
                    "odds_1": match['odds'].get('1'), "odds_X": match['odds'].get('X'),
                    "odds_2": match['odds'].get('2'), "odds_src": match['odds'].get('src')
                }
                final_score = f"{mh}-{ma}" if 6 in algos_indices else f"{th}-{ta}"
                
                existing_doc = manager.collection.find_one({
                    "home_team": match['home'],
                    "away_team": match['away'],
                    "match_date": d_str_iso 
                })
                
                if existing_doc:
                    if MODE_SINGLE: print("   ♻️  Previsione già presente. Aggiorno record.")
                    manager.collection.update_one(
                        {"_id": existing_doc["_id"]},
                        {"$set": {
                            "prediction_score": final_score,
                            "algorithms_data": algo_preds_db,
                            "snapshot_odds": snap,
                            "last_updated": datetime.now()
                        }}
                    )
                    if match['has_real']:
                         p_s = get_sign(int(final_score.split("-")[0]), int(final_score.split("-")[1]))
                         r_s = get_sign(match['real_gh'], match['real_ga'])
                         manager.collection.update_one(
                            {"_id": existing_doc["_id"]},
                            {"$set": {
                                "real_outcome": match['real_score_str'], 
                                "status": "VERIFIED", 
                                "check_sign": (p_s==r_s)
                            }}
                        )
                else:
                    if MODE_SINGLE: print("   💾 Nuova previsione salvata.")
                    pred_id, _ = manager.save_prediction(
                        home=match['home'], away=match['away'], league=match['league'], date_str=d_str_iso,
                        snapshot_data=snap, algo_data=algo_preds_db, final_verdict_score=final_score 
                    )
                    if match['has_real']:
                        p_s = get_sign(int(final_score.split("-")[0]), int(final_score.split("-")[1]))
                        r_s = get_sign(match['real_gh'], match['real_ga'])
                        manager.collection.update_one(
                            {"_id": pred_id}, 
                            {"$set": {
                                "real_outcome": match['real_score_str'], 
                                "status": "VERIFIED", 
                                "check_sign": (p_s==r_s)
                            }}
                        )

        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, delimiter=CSV_DELIMITER)
            headers = ["League", "Match", "Data", "Q1", "QX", "Q2", "Real Score", 
                       "Real Sign", "PRED Score", "PRED Sign", "1X2 Outcome", 
                       "Exact Score", "U/O 2.5", "GG/NG"]

            for idx in algos_indices:
                algo_name = all_algos[idx-1]
                writer.writerow([])
                writer.writerow([f"=== ALGORITMO: {algo_name.upper()} ==="])
                writer.writerow(headers)
                
                stats = {'1X2': 0, 'Exact': 0, 'UO': 0, 'GG': 0, 'Total': 0}
                rows_data = data_by_algo[algo_name]
                
                for item in rows_data:
                    m = item['match']; ph, pa = item['pred_gh'], item['pred_ga']
                    p_sign = get_sign(ph, pa)
                    
                    out_1x2, out_exact, out_uo, out_gg = "WAITING", "WAITING", "WAITING", "WAITING"
                    if m['has_real']:
                        stats['Total'] += 1
                        rh, ra = m['real_gh'], m['real_ga']
                        out_1x2 = "WIN" if p_sign == get_sign(rh, ra) else "LOSS"
                        if out_1x2=="WIN": stats['1X2'] += 1
                        
                        out_exact = "WIN" if ph == rh and pa == ra else "LOSS"
                        if out_exact=="WIN": stats['Exact'] += 1
                        
                        out_uo = "WIN" if get_under_over(ph, pa) == get_under_over(rh, ra) else "LOSS"
                        if out_uo=="WIN": stats['UO'] += 1
                        
                        out_gg = "WIN" if get_gol_nogol(ph, pa) == get_gol_nogol(rh, ra) else "LOSS"
                        if out_gg=="WIN": stats['GG'] += 1

                    writer.writerow([
                        m['league'], f"{m['home']} vs {m['away']}", m['date_str'],
                        m['odds'].get('1','-'), m['odds'].get('X','-'), m['odds'].get('2','-'),
                        m['real_score_str'], get_sign(m['real_gh'], m['real_ga']) if m['has_real'] else "-",
                        f"{ph}-{pa}", p_sign, out_1x2, out_exact, 
                        get_under_over(ph, pa), get_gol_nogol(ph, pa)
                    ])
                
                if stats['Total'] > 0:
                    t = stats['Total']
                    writer.writerow([
                        "--- PERCENTUALI ---\n(Su partite finite)", "", "", "", "", "", "", "", 
                        f"{round(stats['1X2']/t*100,1)}%", f"{round(stats['Exact']/t*100,1)}%", "",
                        f"{round(stats['UO']/t*100,1)}%", "", f"{round(stats['GG']/t*100,1)}%"
                    ])
                else: 
                    writer.writerow(["Nessuna statistica disponibile"])
                writer.writerow([])
                
        # ✨ REPORT RIEPILOGO GIORNATA (solo per modalità massive)
        if not MODE_SINGLE and 6 in algos_indices:
            print_massive_summary(data_by_algo['MonteCarlo'], "MonteCarlo")
        elif not MODE_SINGLE and algos_indices:
            # Se non c'è Monte Carlo, usa il primo algoritmo disponibile
            first_algo = all_algos[algos_indices[0]-1]
            print_massive_summary(data_by_algo[first_algo], first_algo)

        html_filename = filename.replace(".csv", ".html")
        print(f"\n🎨 Generazione Dashboard HTML: {html_filename}...")
        
        try:
            diagnostics.generate_html_report(html_filename, algos_indices, all_algos, data_by_algo, final_matches_list)
        except Exception as e:
            print(f"⚠️ Errore creazione HTML: {e}")
        # ✨ AGGIUNGI QUI IL SALVATAGGIO DEEP ANALYSIS:
        print(f"\n🔬 Generazione Deep Analysis Report...")
        try:
            deep_filename_base = filename.replace("simulation_report", "deep_analysis").replace(".csv", "")
            deep_analyzer.save_report(
                csv_path=f"{deep_filename_base}.csv",
                html_path=f"{deep_filename_base}.html",
                json_path=f"{deep_filename_base}.json"
            )
            print(f"✅ Deep Analysis salvato:")
            print(f"   📄 CSV:  {deep_filename_base}.csv")
            print(f"   🌐 HTML: {deep_filename_base}.html")
            print(f"   📦 JSON: {deep_filename_base}.json")
        except Exception as e:
            print(f"⚠️ Errore creazione Deep Analysis: {e}")

        if MODE_SINGLE: 
            print(f"\n✅ Analisi completata! Risultati salvati in {filename}")
        else: 
            print(f"\n✅ REPORT GENERATO: {filename} + {html_filename} + Deep Analysis")
        if MODE_SINGLE: 
            print(f"\n✅ Analisi completata! Risultati salvati in {filename}")
        else: 
            print(f"\n✅ REPORT GENERATO: {filename} + {html_filename}")
        
        input("\nPremi INVIO per tornare al menu principale...")

if __name__ == "__main__":
    run_universal_simulator()