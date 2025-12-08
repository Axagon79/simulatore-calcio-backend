import sys
import os
import contextlib
from datetime import datetime
from collections import Counter
from tqdm import tqdm 

# --- SETUP PERCORSI ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
sys.path.append(PROJECT_ROOT)

# --- IMPORT DATABASE ---
try:
    from config import db
except ImportError:
    sys.path.append(os.path.dirname(CURRENT_DIR))
    from config import db

# --- IMPORT MOTORE ---
from engine_core import predict_match, preload_match_data
from goals_converter import calculate_goals_from_engine

# --- ZITTIRE IL TERMINALE (FIX WINDOWS EMOJI) ---
@contextlib.contextmanager
def suppress_stdout():
    # FIX: Aggiunto encoding="utf-8" per non far crashare Windows con le emoji 🤖
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:  
            yield
        finally:
            sys.stdout = old_stdout

# --- MAPPA NAZIONI ---
NATION_MAP = {
    "Italia": ["Serie A", "Serie B", "Serie C", "Coppa Italia"],
    "Inghilterra": ["Premier League", "Championship", "FA Cup", "League One"],
    "Spagna": ["La Liga", "Segunda", "Copa del Rey"],
    "Germania": ["Bundesliga", "DFB"],
    "Francia": ["Ligue 1", "Ligue 2"],
    "Europa": ["Champions", "Europa League", "Conference"]
}

def get_leagues_from_db():
    if db is None: return []
    return sorted(db.h2h_by_round.distinct("league"))

def filter_leagues_by_nation(all_leagues, nation_choice):
    filtered = []
    keywords = NATION_MAP.get(nation_choice, [])
    if nation_choice == "Altro":
        all_known = [item for sublist in NATION_MAP.values() for item in sublist]
        for l in all_leagues:
            if not any(k in l for k in all_known): filtered.append(l)
    else:
        for l in all_leagues:
            if any(k in l for k in keywords): filtered.append(l)
    return filtered

def format_date(date_obj):
    if not date_obj: return "Data N/A"
    try:
        return date_obj.strftime("%d/%m %H:%M")
    except: return str(date_obj)[:16]

def get_calendar_view(league_name):
    cursor = db.h2h_by_round.find({"league": league_name})
    rounds = []
    for doc in cursor: rounds.append(doc)
        
    def sort_key(r):
        try:
            import re
            num = re.search(r'\d+', r.get('round_name', '0'))
            return int(num.group()) if num else 999
        except: return 999
    rounds.sort(key=sort_key)
    
    active_idx = -1
    for i, r in enumerate(rounds):
        matches = r.get("matches", [])
        has_future = any(m.get("status") in ["Scheduled", "Timed"] for m in matches)
        if has_future:
            active_idx = i
            break
    
    if active_idx == -1: return []
    target_rounds = [rounds[active_idx]]
    if active_idx + 1 < len(rounds): target_rounds.append(rounds[active_idx + 1])
        
    display_list = []
    for r in target_rounds:
        r_name = r.get("round_name", "Giornata ?")
        display_list.append({"type": "HEADER", "text": f"--- {r_name} ---"})
        matches = r.get("matches", [])
        matches.sort(key=lambda x: x.get("date_obj") or datetime.max)
        for m in matches:
            status = m.get("status")
            is_playable = status in ["Scheduled", "Timed"]
            date_str = format_date(m.get("date_obj"))
            if is_playable:
                label = f"[{date_str}] {m['home']} vs {m['away']}"
            else:
                score = m.get("real_score", "Ris. N/A") or "- -"
                if score == "null": score = "- -"
                label = f"[{date_str}] {m['home']} {score} {m['away']} (FINITA)"
            display_list.append({"type": "MATCH", "label": label, "home": m["home"], "away": m["away"], "playable": is_playable})
    return display_list

# --- MONTE CARLO OTTIMIZZATO (CON ANALISI X-RAY 🩻) ---
def esegui_monte_carlo_smart(casa, trasferta):
    
    print(f"\n🔮 AVVIO MONTE CARLO (Camaleonte No-Zavorra + X-RAY)...")
    
    # 1. PRELOAD DATI
    print("📥 Recupero dati squadre (Eseguito 1 volta)...")
    try:
        with suppress_stdout():
            dati_pronti = preload_match_data(casa, trasferta)
        
        # 🔍 DEBUG: Verifica valori attacco/difesa caricati
        print(f"\n🔍 DEBUG DATI CARICATI:")
        print(f"   {casa} att_home: {dati_pronti['home_raw']['attack']:.1f} (dovrebbe essere ~14 per top team)")
        print(f"   {casa} def_home: {dati_pronti['home_raw']['defense']:.1f} (dovrebbe essere ~9 per top team)")
        print(f"   {casa} power: {dati_pronti['home_raw']['power']:.1f} (dovrebbe essere ~23 per top team)")
        print(f"   {trasferta} att_away: {dati_pronti['away_raw']['attack']:.1f} (dovrebbe essere ~7 per team medio)")
        print(f"   {trasferta} def_away: {dati_pronti['away_raw']['defense']:.1f} (dovrebbe essere ~4-5 per team debole)")
        print(f"   {trasferta} power: {dati_pronti['away_raw']['power']:.1f} (dovrebbe essere ~11-12 per team medio)\n")
        
    except Exception as e:
        print(f"❌ Errore nel recupero dati: {e}")
        return


    # Dizionario per raccogliere i risultati separati per algoritmo
    results_by_algo = {2: [], 3: [], 4: [], 5: []}
    all_scores_total = []
    
    algoritmi = [(2,"Dinamico"), (3,"Tattico"), (4,"Caos"), (5,"Master")]


    # 2. SIMULAZIONE VELOCE
    print("🚀 Esecuzione 5000 simulazioni...")
    
    with tqdm(total=4, desc="Calcolo", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} Algo") as pbar:
        for algo_id, algo_nome in algoritmi:
            try:
                for _ in range(10000):
                    # Calcolo Potenza
                    s_h, s_a, r_h, r_a = predict_match(casa, trasferta, mode=algo_id, preloaded_data=dati_pronti)
                    
                    if s_h is None: continue
                    
                    # Calcolo Gol (con parametro algo_mode)
                    gh, ga, _, _, _ = calculate_goals_from_engine(s_h, s_a, r_h, r_a, algo_mode=algo_id)
                    score_str = f"{gh}-{ga}"
                    
                    # Salva nel totale
                    all_scores_total.append(score_str)
                    # Salva nello specifico dell'algoritmo
                    results_by_algo[algo_id].append(score_str)


            except Exception as e:
                sys.stderr.write(f"Err: {e}")
            
            pbar.update(1)


    if not all_scores_total:
        print("❌ Errore: Nessun risultato generato.")
        return


    total_sims = len(all_scores_total)


    # --- CALCOLO STATISTICHE FINALI (TOTALE) ---
    cnt_wins_h = 0; cnt_wins_a = 0; cnt_draws = 0
    cnt_goal = 0; cnt_over25 = 0
    
    for score in all_scores_total:
        h, a = map(int, score.split('-'))
        tot = h + a
        if h > a: cnt_wins_h += 1
        elif a > h: cnt_wins_a += 1
        else: cnt_draws += 1
        if h > 0 and a > 0: cnt_goal += 1
        if tot > 2.5: cnt_over25 += 1


    p_1 = (cnt_wins_h / total_sims) * 100
    p_x = (cnt_draws / total_sims) * 100
    p_2 = (cnt_wins_a / total_sims) * 100
    p_goal = (cnt_goal / total_sims) * 100
    p_over25 = (cnt_over25 / total_sims) * 100


    # --- STAMPA REPORT TOTALE ---
    print("\n" + "="*65)
    print(f"📊 REPORT SCOMMESSE AI: {casa} vs {trasferta}")
    print(f"   (5000 Simulazioni Totali)")
    print("="*65)


    print(f"\n🎯 MEDIE GLOBALI")
    print(f"   1: {p_1:.1f}% | X: {p_x:.1f}% | 2: {p_2:.1f}%")
    print(f"   GOL: {p_goal:.1f}% | OVER 2.5: {p_over25:.1f}%")


    # --- 🕵️‍♂️ ANALISI X-RAY PER ALGORITMO ---
    print("\n" + "="*65)
    print("🩻 ANALISI X-RAY: COSA PENSANO I SINGOLI ALGORITMI?")
    print("="*65)
    
    algo_names = {2: "DINAMICO (Standard)", 3: "TATTICO (Goleade)", 4: "CAOS (Sorprese)", 5: "MASTER (Mix)"}
    
    for aid, scores in results_by_algo.items():
        if not scores: continue
        
        # Trova i 3 risultati più frequenti per questo algoritmo
        top_3 = Counter(scores).most_common(3)
        sims_algo = len(scores)
        
        print(f"\n🔹 {algo_names.get(aid, 'Algo ?')}")
        row_str = "   "
        for sc, freq in top_3:
            perc = (freq / sims_algo) * 100
            row_str += f"[{sc}: {perc:.1f}%]  "
        print(row_str)
            # --- 🧠 IL VERDETTO INTELLIGENTE (Consiglio degli Esperti) ---
    print(f"\n🧠 IL VERDETTO DELL'INTELLIGENZA ARTIFICIALE")
    print("="*65)
    
    import random
    from colorama import Fore, Style, init
    init(autoreset=True)

    # 1. Recuperiamo le "nomination" dagli esperti (Top 3 di ogni algo)
    nominees = []
    
    # Raccogli i migliori risultati da ogni algoritmo
    for aid, scores in results_by_algo.items():
        if scores:
            top_3_local = Counter(scores).most_common(3)
            # Aggiungi i risultati alla lista dei candidati (ponderati per frequenza locale)
            for sc, freq in top_3_local:
                # Aggiungiamo il risultato tante volte quanto è il suo "peso" (frequenza relativa)
                # per dare più chance ai risultati solidi
                weight = int((freq / len(scores)) * 10) # Peso da 1 a 10
                nominees.extend([sc] * max(1, weight))

    # 2. Estrazione Finale (L'AI sceglie un risultato dalla lista dei migliori)
    if nominees:
        final_verdict = random.choice(nominees)
        fh, fa = map(int, final_verdict.split("-"))
        
        print(f"\n🎲 DOPO AVER ASCOLTATO GLI ESPERTI, L'AI SCOMMETTE SU:")
        print(f"   {Fore.YELLOW}🏆 {casa}  {fh} - {fa}  {trasferta} {Style.RESET_ALL}")
        
        # Pronostici Derivati
        segno = "X"
        if fh > fa: segno = "1"
        elif fa > fh: segno = "2"
        
        print(f"\n📉 SCHEDINA GENERATA:")
        print(f"   ✅ Segno Fisso: {segno}")
        print(f"   ✅ Under/Over: {'Over 2.5' if (fh+fa)>=3 else 'Under 2.5'}")
        print(f"   ✅ Gol/NoGol: {'GOL' if fh>0 and fa>0 else 'NO GOL'}")
        
        # Doppia Chance (solo se il distacco è minimo)
        if abs(fh - fa) == 1 or segno == "X":
            dc = "1X" if segno == "1" else ("X2" if segno == "2" else "1X o X2")
            print(f"   ✅ Copertura: {dc}")
    else:
        print("   ⚠️ Dati insufficienti per un verdetto.")



    print("\n" + "="*65 + "\n")



def simula_match(casa, trasferta):
    print(f"\n🚀 PREPARAZIONE: {casa} vs {trasferta}")
    print("1-5. Simulazione Singola")
    print("6.   🔮 MONTE CARLO (Report Scommesse)")
    try:
        scelta = int(input("Scelta (Invio per 5): ").strip() or 5)
    except: scelta = 5
    
    if scelta == 6:
        esegui_monte_carlo_smart(casa, trasferta)
        return

    print(f"\n⚽ AVVIO SIMULAZIONE SINGOLA...")
    try:
        s_h, s_a, r_h, r_a = predict_match(casa, trasferta, mode=scelta)
        if r_h is None:
            print("\n🚨 Dati mancanti. Lancia 'calcolatore_h2h_v2.py'.")
            return
        g_h, g_a, xg_h, xg_a, chaos = calculate_goals_from_engine(s_h, s_a, r_h, r_a , algo_mode=scelta)
        print(f"\n🏁 RISULTATO: {casa} {g_h} - {g_a} {trasferta}")
        print(f"   📊 xG: {xg_h:.2f} - {xg_a:.2f}")
        print(f"   🎲 Metodo: {chaos}")
    except Exception as e:
        print(f"❌ Errore: {e}")

def menu_gerarchico():
    while True:
        print("\n🌍 SELETTORE CAMPIONATI")
        nazioni = list(NATION_MAP.keys()) + ["Altro"]
        for i, n in enumerate(nazioni): print(f"{i+1}. {n}")
        print("0. Esci")
        try:
            raw = input("> ").strip()
            if raw == "0": break
            nazione = nazioni[int(raw)-1]
        except: continue

        all_leagues = get_leagues_from_db()
        filtered = filter_leagues_by_nation(all_leagues, nazione)
        if not filtered: continue
            
        print(f"\n🏆 LEGA:")
        for i, l in enumerate(filtered): print(f"{i+1}. {l}")
        print("0. Indietro")
        try:
            sel = int(input("> ")) - 1
            if sel < 0: continue
            lega = filtered[sel]
        except: continue

        items = get_calendar_view(lega)
        if not items: continue
        
        print(f"\n📅 CALENDARIO {lega}")
        sel_map = {}
        cnt = 1
        for it in items:
            if it["type"] == "HEADER": print(f"\n{it['text']}")
            else:
                pre = f"{cnt}." if it['playable'] else "  "
                print(f"{pre} {it['label']}")
                if it['playable']: sel_map[cnt] = it; cnt += 1
        
        print("\n0. Indietro")
        try:
            sel = int(input("> "))
            if sel in sel_map:
                m = sel_map[sel]
                simula_match(m['home'], m['away'])
                input("Invio...")
        except: continue

if __name__ == "__main__":
    menu_gerarchico()
