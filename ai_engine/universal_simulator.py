import os
import sys
import csv
import re
from datetime import datetime, date
from collections import Counter
from tqdm import tqdm
import contextlib
import random
import diagnostics

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
                print("   Inserisci numero cicli totali (min: 100, max: 100,000)")
                print("   Nota: Verrà arrotondato al multiplo di 4 più vicino")
                
                try:
                    custom = int(input("\n   Cicli totali: ").strip())
                except ValueError:
                    print("❌ Inserisci un numero valido.")
                    continue
                
                if custom < 100:
                    print("❌ Minimo 100 cicli.")
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
def run_single_algo(algo_id, preloaded_data):
    s_h, s_a, r_h, r_a = predict_match("", "", mode=algo_id, preloaded_data=preloaded_data)
    if s_h is None: return 0, 0
    gh, ga, *_ = calculate_goals_from_engine(s_h, s_a, r_h, r_a, algo_mode=algo_id)
    return gh, ga


def run_monte_carlo_verdict_detailed(preloaded_data, home_team, away_team):
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
                    
                    try: algo_sel = int(input("   Scelta: ").strip())
                    except: algo_sel = 0
                    
                    monte_carlo_cycles = None
                    if algo_sel == 6:
                        monte_carlo_cycles = ask_monte_carlo_cycles()
                        if monte_carlo_cycles is None:
                            continue
                    
                    return [selected_match], algo_sel, monte_carlo_cycles


# --- LOGICA CORE ---
def run_universal_simulator():
    global MONTE_CARLO_TOTAL_CYCLES
    
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

        if MODE_SINGLE:
            result = flow_single_match()
            if result is None or len(result) < 2:
                continue
            
            matches_to_process = result[0]
            selected_algo_id = result[1]
            
            if len(result) >= 3 and result[2] is not None:
                MONTE_CARLO_TOTAL_CYCLES = result[2]
                print(f"\n⚙️  Configurato: {MONTE_CARLO_TOTAL_CYCLES:,} cicli Monte Carlo")
            else:
                MONTE_CARLO_TOTAL_CYCLES = 5000
            
            if not matches_to_process: 
                continue
        
        else:
            selected_leagues_names = []
            
            if AUTO_ALL_LEAGUES:
                selected_leagues_names = sorted(db.h2h_by_round.distinct("league"))
                print(f"📦 Caricamento automatico di {len(selected_leagues_names)} campionati...")
            else:
                while True:
                    print("\n🏆 SELEZIONE CAMPIONATI (Massivo):")
                    print("   [0] TUTTI I CAMPIONATI")
                    all_leagues = sorted(db.h2h_by_round.distinct("league"))
                    for i, l in enumerate(all_leagues): 
                        print(f"   [{i+1}] {l}")
                    print("   [99] INDIETRO (Menu Principale)")
                    
                    try:
                        l_choice = int(input("   Scelta: ").strip())
                        if l_choice == 99: break
                        if l_choice == 0: 
                            selected_leagues_names = all_leagues
                            break
                        elif 1 <= l_choice <= len(all_leagues): 
                            selected_leagues_names = [all_leagues[l_choice-1]]
                            break
                        else: continue
                    except: continue

                if not selected_leagues_names: continue
            
            if not MODE_SINGLE:
                will_use_montecarlo = False
                
                if selected_algo_id == 0:
                    will_use_montecarlo = True
                elif selected_algo_id == 6:
                    will_use_montecarlo = True
                
                if will_use_montecarlo:
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
        
        all_algos = ['Stat', 'Din', 'Tat', 'Caos', 'Master', 'MonteCarlo']
        data_by_algo = {name: [] for name in all_algos}
        
        algos_indices = []
        if selected_algo_id == 0: algos_indices = [1, 2, 3, 4, 5, 6]
        elif selected_algo_id == 6: algos_indices = [6]
        else: algos_indices = [selected_algo_id]

        iterator = tqdm(final_matches_list) if not MODE_SINGLE else final_matches_list
        
        for match in iterator:
            if MODE_SINGLE: 
                print(f"\n⚡ ANALISI: {match['home']} vs {match['away']}...")
            
            with suppress_stdout():
                try: preloaded = preload_match_data(match['home'], match['away'])
                except: continue
            
            algo_preds_db = {}
            
            for aid in [i for i in algos_indices if i <= 5]:
                th, ta = run_single_algo(aid, preloaded)
                name = all_algos[aid-1]
                data_by_algo[name].append({'match': match, 'pred_gh': th, 'pred_ga': ta})
                algo_preds_db[f"Algo_{aid}"] = f"{th}-{ta}"
                
                if MODE_SINGLE:
                    print(f"   🔹 {name}: {th}-{ta} ({get_sign(th, ta)})")

            mh, ma = 0, 0
            pesi_medi = {}
            scontrini_medi = {}
            
            if 6 in algos_indices:
                (mh, ma), algos_stats, global_top3, pesi_medi, scontrini_medi = run_monte_carlo_verdict_detailed(
                    preloaded, match['home'], match['away']
                )
                data_by_algo['MonteCarlo'].append({'match': match, 'pred_gh': mh, 'pred_ga': ma})
                
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
                            print(f"   {'VOCE':<15} | {'CASA (V×P=Pt)':<25} | {'OSPITE (V×P=Pt)':<25}")
                            print("-" * 70)
                            
                            voci = set(list(scontrino.get('casa', {}).keys()) + list(scontrino.get('ospite', {}).keys()))
                            totale_casa = 0
                            totale_ospite = 0
                            
                            for voce in sorted(voci):
                                casa_data = scontrino.get('casa', {}).get(voce, {'valore': 0, 'peso': 0, 'punti': 0})
                                ospite_data = scontrino.get('ospite', {}).get(voce, {'valore': 0, 'peso': 0, 'punti': 0})
                                
                                casa_str = f"{casa_data['valore']:>5.1f} × {casa_data['peso']:>4.2f} = {casa_data['punti']:>6.2f}"
                                ospite_str = f"{ospite_data['valore']:>5.1f} × {ospite_data['peso']:>4.2f} = {ospite_data['punti']:>6.2f}"
                                
                                print(f"   {voce:<15} | {casa_str:<25} | {ospite_str:<25}")
                                
                                totale_casa += casa_data['punti']
                                totale_ospite += ospite_data['punti']
                            
                            print("-" * 70)
                            print(f"   {'TOTALE':<15} | {totale_casa:>25.2f} | {totale_ospite:>25.2f}")
                            print(f"   DIFFERENZA: {abs(totale_casa - totale_ospite):.2f} " + 
                                  f"({'CASA' if totale_casa > totale_ospite else 'OSPITE'} favorita)")

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

        html_filename = filename.replace(".csv", ".html")
        print(f"\n🎨 Generazione Dashboard HTML: {html_filename}...")
        try:
            diagnostics.generate_html_report(html_filename, algos_indices, all_algos, data_by_algo, final_matches_list)
        except Exception as e:
            print(f"⚠️ Errore creazione HTML: {e}")

        if MODE_SINGLE: 
            print(f"\n✅ Analisi completata! Risultati salvati in {filename}")
        else: 
            print(f"\n✅ REPORT GENERATO: {filename} + {html_filename}")
        
        input("\nPremi INVIO per tornare al menu principale...")

if __name__ == "__main__":
    run_universal_simulator()