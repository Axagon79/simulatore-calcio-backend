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


# --- CONFIGURAZIONI ---
MONTE_CARLO_TOTAL_CYCLES = 5000
CSV_DELIMITER = ';'


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


# --- NUOVA FUNZIONE ANALISI QUOTE ---
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
        
        # Colora la quota più bassa
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
    gh, ga, _, _, _ = calculate_goals_from_engine(s_h, s_a, r_h, r_a, algo_mode=algo_id)
    return gh, ga


def run_monte_carlo_verdict_detailed(preloaded_data):
    """
    Versione dettagliata con logica CORRETTA del File 1:
    - Ogni algoritmo vota solo con i suoi top 3 risultati più frequenti
    - Elimina il rumore statistico
    - Ritorna: (gh, ga), stats_per_algo
    """
    nominees = []
    algos_stats = {}  # Statistiche per algoritmo
    algos_full_results = {}  # ← NUOVO: Tutti i risultati grezzi
    algos = [2, 3, 4, 5]
    cycles_per_algo = MONTE_CARLO_TOTAL_CYCLES // 4
    
    for aid in algos:
        local_results = []  # ← Lista locale per ogni algoritmo
        for _ in range(cycles_per_algo): 
            s_h, s_a, r_h, r_a = predict_match("", "", mode=aid, preloaded_data=preloaded_data)
            if s_h is None: continue
            gh, ga, _, _, _ = calculate_goals_from_engine(s_h, s_a, r_h, r_a, algo_mode=aid)
            local_results.append(f"{gh}-{ga}")
        
        if not local_results: continue
        
        # ✅ SALVA TUTTI I RISULTATI GREZZI
        algos_full_results[aid] = local_results.copy()  # ← NUOVO
        
        # ✅ PRENDE SOLO I TOP 3 RISULTATI (filtra il rumore)
        top_3 = Counter(local_results).most_common(3)
        algos_stats[aid] = top_3  # Salva per output dettagliato
        
        # Aggiunge i top 3 al pool finale con peso
        for sc, freq in top_3:
            w = int(freq) 
            nominees.extend([sc] * w)
    
    if not nominees: return (0, 0), algos_stats, []
    
    # Scelta finale pesata
    final_verdict = random.choice(nominees)
    gh, ga = map(int, final_verdict.split("-"))
    
    # Calcola top 3 globale per display
    global_top3 = Counter(nominees).most_common(3)
    
    # ========== SALVATAGGIO DEBUG FILE ========== 
    import json
    import os
    from datetime import datetime
    
    debug_data = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'match': preloaded_data.get('match_info', 'Unknown'),  # Se hai info partita
        'risultato_finale': f"{gh}-{ga}",
        'algoritmi': {}
    }
    
    algo_names = {2: 'Dinamico', 3: 'Tattico', 4: 'Caos', 5: 'Master'}
    
    for aid in algos:
        if aid not in algos_full_results:
            continue
            
        all_results = algos_full_results[aid]
        freq_counter = Counter(all_results)
        
        debug_data['algoritmi'][algo_names[aid]] = {
            'totale_simulazioni': len(all_results),
            'risultati_completi': all_results,
            'top_10': freq_counter.most_common(10),
            'top_3_usati': algos_stats.get(aid, [])
        }
    
    # Salva in JSON
    debug_file = "monte_carlo_debug_NEW2.json"
    with open(debug_file, "w", encoding="utf-8") as f:
        json.dump(debug_data, f, indent=2, ensure_ascii=False)
    
    #print(f"\n💾 [DEBUG] Dati Monte Carlo salvati in: {debug_file}")
    # ============================================
    
    return (gh, ga), algos_stats, global_top3


# --- LOGICA NAVIGAZIONE GERARCHICA ---


def flow_single_match():
    """Gestisce il flusso Nazione -> Lega -> Giornata -> Partita -> Algoritmo."""
    
    # 1. LOOP NAZIONE
    while True:
        print("\n🌍 SELEZIONA NAZIONE:")
        nations_list = list(NATION_GROUPS.keys())
        for i, n in enumerate(nations_list):
            print(f"   [{i+1}] {n}")
        print("   [99] INDIETRO (Menu Principale)")
        
        try: n_sel = int(input("   Scelta: ").strip())
        except: continue
        
        if n_sel == 99: return None, None
        if n_sel < 1 or n_sel > len(nations_list): continue
        selected_nation = nations_list[n_sel-1]
        
        # 2. LOOP LEGA
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


            # 3. LOOP GIORNATA
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
            
                # 4. LOOP PARTITE
                while True:
                    print(f"\n⚽ RECUPERO PARTITE PER: {selected_league_name}...")
                    rounds_cursor = db.h2h_by_round.find({"league": selected_league_name})
                    rounds_list = list(rounds_cursor)
                    if not rounds_list:
                        print("❌ Nessun dato trovato.")
                        break


                    rounds_list.sort(key=lambda x: get_round_number(x.get('round_name', '0')))
                    
                    # Logica Anchor
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
                    
                    # 5. SCELTA ALGORITMO
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
                    
                    return [selected_match], algo_sel

# --- LOGICA CORE ---
def run_universal_simulator():
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
        ONLY_FINISHED = False  # <--- AGGIUNGI QUESTA RIGA QUI
        selected_algo_id = 0
        
        try: main_choice = int(input("   Scelta: ").strip())
        except: continue


        if main_choice == 99: sys.exit(0)
        elif main_choice == 0:
            # 💎 CONFIGURAZIONE SUPER TOTAL (SOLO FINITE)
            offsets_to_run = [-1, 0, 1] 
            AUTO_ALL_LEAGUES = True
            ONLY_FINISHED = True # <--- ATTIVIAMO IL FILTRO
            print("\n💎 MODALITÀ TOTAL (VERIFICA): Analisi partite CONCLUSE (con risultato) di Ieri, Oggi e Domani.")
        elif main_choice == 1: offsets_to_run = [-1]
        elif main_choice == 2: offsets_to_run = [0]
        elif main_choice == 3: offsets_to_run = [1]
        elif main_choice == 4: MODE_SINGLE = True
        else: 
            print("❌ Scelta non valida."); continue


        matches_to_process = []


        if MODE_SINGLE:
            matches_to_process, selected_algo_id = flow_single_match()
            if not matches_to_process: continue
        
        else:
            # --- FLUSSO MASSIVO INTELLIGENTE ---
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


            print(f"\n🔍 Recupero partite (Periodi: {offsets_to_run})...")
            
            # --- LOOP INTELLIGENTE SU LEGHE E OFFSETS ---
            for league_name in selected_leagues_names:
                rounds_cursor = db.h2h_by_round.find({"league": league_name})
                rounds_list = list(rounds_cursor)
                if not rounds_list: continue
                rounds_list.sort(key=lambda x: get_round_number(x.get('round_name', '0')))
                
                # Trova Anchor
                anchor_index = -1
                for i, r in enumerate(rounds_list):
                    if any(m.get('status') in ['Scheduled', 'Timed'] for m in r.get('matches', [])):
                        anchor_index = i; break
                if anchor_index == -1:
                        for i in range(len(rounds_list) - 1, -1, -1):
                            if has_valid_results(rounds_list[i]): 
                                anchor_index = i; break
                
                # Cicla su tutti gli offsets richiesti (Super Total o singolo)
                for off in offsets_to_run:
                    target_index = anchor_index + off
                    if 0 <= target_index < len(rounds_list):
                        target_round = rounds_list[target_index]
                        r_name = target_round.get('round_name', 'Unknown')
                        
                        for m in target_round.get('matches', []):
                            
                            # --- MODIFICA: FILTRO SOLO PARTITE FINITE ---
                            # Se siamo in modalità Total/Verifica, prendiamo SOLO quelle con risultato reale
                            if ONLY_FINISHED:
                                s = m.get('real_score')
                                # Se il risultato è nullo, vuoto o non ha il formato "X:Y", SALTA la partita
                                if not (s and isinstance(s, str) and ":" in s and s != "null"):
                                    continue
                            # --------------------------------------------

                            m_copy = m.copy()
                            m_copy['league'] = league_name
                            m_copy['round'] = r_name
                            matches_to_process.append(m_copy)


        if not matches_to_process:
            print("❌ Nessuna partita trovata (o nessuna partita conclusa, se in modalità Verifica).")
            continue


        # --- FORMATTAZIONE DATI ---
        final_matches_list = []
        for m in matches_to_process:
            real_s = m.get('real_score'); has_real = False; rh, ra = 0, 0
            if real_s and isinstance(real_s, str) and ":" in real_s and real_s != "null":
                try: rh, ra = map(int, real_s.split(":")); has_real = True
                except: pass
            
            d_obj = m.get('date_obj')
            d_str = d_obj.strftime("%d/%m %H:%M") if d_obj else "Data N/D"
            # Importante per Anti-Duplicati: data normalizzata ISO
            d_iso = d_obj.strftime("%Y-%m-%d") if d_obj else str(datetime.now().date())
            
            final_matches_list.append({
                "home": m['home'], "away": m['away'],
                "league": m.get('league', 'Unknown'), "round": m.get('round', '-'),
                "real_gh": rh, "real_ga": ra,
                "real_score_str": f"{rh}-{ra}" if has_real else "-",
                "has_real": has_real, "date_obj": d_obj, "date_str": d_str, "date_iso": d_iso,
                "status": m.get('status', 'Unknown'), "odds": m.get('odds', {}) 
            })


        # --- ANTEPRIMA ---
        if not MODE_SINGLE:
            print(f"\n📋 ANTEPRIMA ({len(final_matches_list)} partite):")
            limit_prev = 10 if not AUTO_ALL_LEAGUES else 5
            for m in final_matches_list[:limit_prev]:
                status_txt = f"[FINITA {m['real_score_str']}]" if m['has_real'] else "[DA GIOCARE]"
                print(f"   [{m['date_str']}] {m['home']} vs {m['away']} {status_txt}")
            if len(final_matches_list) > limit_prev:
                print(f"   ... e altre {len(final_matches_list)-limit_prev} partite")


        # --- BLOCCO DI CONTROLLO RIGIDO 🛡️ ---
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
                
                # Se è Total, forza Sandbox per sicurezza, altrimenti chiedi
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


        # --- ELABORAZIONE ---
        filename = "simulation_report.csv" if not AUTO_ALL_LEAGUES else "total_simulation_report.csv"
        print(f"\n⏳ Elaborazione in corso... Output: {filename}")
        
        all_algos = ['Stat', 'Din', 'Tat', 'Caos', 'Master', 'MonteCarlo']
        data_by_algo = {name: [] for name in all_algos}
        
        # Filtra algoritmi da eseguire
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
            
            # Esegui algoritmi standard (1-5)
            for aid in [i for i in algos_indices if i <= 5]:
                th, ta = run_single_algo(aid, preloaded)
                name = all_algos[aid-1]
                data_by_algo[name].append({'match': match, 'pred_gh': th, 'pred_ga': ta})
                algo_preds_db[f"Algo_{aid}"] = f"{th}-{ta}"
                
                if MODE_SINGLE:
                    print(f"   🔹 {name}: {th}-{ta} ({get_sign(th, ta)})")


            # Esegui MonteCarlo (6)
            mh, ma = 0, 0
            if 6 in algos_indices:
                (mh, ma), algos_stats, global_top3 = run_monte_carlo_verdict_detailed(preloaded)
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


            # --- SALVATAGGIO INTELLIGENTE (ANTI-DUPLICATI) ---
            if save_to_db and manager:
                d_str_iso = match['date_iso'] # Usa formato ISO per DB check
                
                snap = {
                    "home_att": 0, "away_att": 0,
                    "odds_1": match['odds'].get('1'), "odds_X": match['odds'].get('X'),
                    "odds_2": match['odds'].get('2'), "odds_src": match['odds'].get('src')
                }
                final_score = f"{mh}-{ma}" if 6 in algos_indices else f"{th}-{ta}"
                
                # 1. CHECK ESISTENZA
                existing_doc = manager.collection.find_one({
                    "home_team": match['home'],
                    "away_team": match['away'],
                    "match_date": d_str_iso 
                })
                
                if existing_doc:
                    # 2A. AGGIORNA
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
                    # Gestione verifica se finita
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
                    # 2B. INSERISCI NUOVO
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


                # --- CSV EXPORT ---
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

        # --- GENERAZIONE DASHBOARD HTML (Fuori dal blocco CSV) ---
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

