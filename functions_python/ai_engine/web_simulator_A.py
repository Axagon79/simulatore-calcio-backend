#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# --- 1. SPOSTA QUESTO BLOCCO PRIMA DI OGNI ALTRO IMPORT ---
# Determiniamo il percorso assoluto della cartella corrente (ai_engine)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Aggiungiamo la cartella corrente ai percorsi di ricerca di Python
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Aggiungiamo anche la radice (functions_python) per sicurezza
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# --- 2. ORA PUOI IMPORTARE IL TUO MODULO SENZA ERRORI ---
import json
import random
from betting_logic import analyze_betting_data
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

def genera_cronaca_live_densa(gh, ga, team_h, team_a, h2h_data):
    """
    Genera 35-40 eventi live usando i pool di commenti realistici.
    Sincronizza ESATTAMENTE gh gol per casa e ga per ospite.
    VERSIONE CORRETTA: Elimina duplicati alla fonte.
    """
    import random
    
    cronaca = []
    minuti_usati = set()
    
    # ✅ GESTIONE ROBUSTA: Accetta sia dict che stringhe
    if isinstance(team_h, dict):
        h = team_h.get('name', 'Home').upper()
    else:
        h = str(team_h).upper()
    
    if isinstance(team_a, dict):
        a = team_a.get('name', 'Away').upper()
    else:
        a = str(team_a).upper()
    
    def rand(lista):
        return random.choice(lista)
    
    # ✅ POOL COMPLETI
    pool_attacco = [
        "tenta la magia in rovesciata, il pallone viene bloccato dal portiere.",
        "scappa sulla fascia e mette un cross teso: la difesa libera in affanno.",
        "grande azione personale, si incunea in area ma viene murato al momento del tiro.",
        "cerca la palla filtrante per la punta, ma il passaggio è leggermente lungo.",
        "prova la conclusione dalla distanza: palla che sibila sopra la traversa.",
        "duello vinto sulla trequarti, palla a rimorchio ma nessuno arriva per il tap-in.",
        "serie di batti e ribatti nell'area piccola, alla fine il portiere blocca a terra.",
        "parte in contropiede fulmineo, ma l'ultimo tocco è impreciso.",
        "palla filtrante geniale! L'attaccante controlla male e sfuma l'occasione.",
        "colpo di testa imperioso su azione d'angolo: palla fuori di un soffio.",
        "scambio stretto al limite dell'area, tiro a giro che non inquadra lo specchio.",
        "insiste nella pressione offensiva, costringendo gli avversari al rinvio lungo.",
        "si libera bene per il tiro, ma la conclusione è debole e centrale.",
        "schema su punizione che libera l'ala, il cross è però troppo alto per tutti."
    ]
    
    pool_difesa = [
        "grande intervento in scivolata! Il difensore legge benissimo la traiettoria.",
        "muro difensivo invalicabile: respinta la conclusione a botta sicura.",
        "chiusura provvidenziale in diagonale, l'attaccante era già pronto a calciare.",
        "anticipo netto a centrocampo, la squadra può ripartire in transizione.",
        "fa buona guardia sul cross da destra, svettando più in alto di tutti.",
        "riesce a proteggere l'uscita del pallone sul fondo nonostante la pressione.",
        "vince il duello fisico spalla a spalla e riconquista il possesso.",
        "intervento pulito sul pallone, sventata una ripartenza pericolosissima.",
        "chiusura millimetrica in area di rigore, brivido per i tifosi."
    ]
    
    pool_portiere = [
        "grande intervento! Il portiere si allunga alla sua sinistra e mette in corner.",
        "salva sulla linea! Riflesso felino su un colpo di testa ravvicinato.",
        "attento in uscita bassa, anticipa la punta lanciata a rete con coraggio.",
        "si oppone con i pugni a una botta violenta dal limite. Sicurezza tra i pali.",
        "vola all'incrocio dei pali! Parata incredibile che salva il risultato.",
        "blocca in due tempi un tiro velenoso che era rimbalzato davanti a lui.",
        "esce con tempismo perfetto fuori dall'area per sventare il lancio lungo.",
        "deviazione d'istinto su una deviazione improvvisa, corner per gli avversari."
    ]
    
    pool_atmosfera = [
        "ritmi ora altissimi, le squadre si allungano e i ribaltamenti sono continui.",
        "gara ora su ritmi bassissimi, si avverte la stanchezza in campo.",
        "atmosfera elettrica sugli spalti, i tifosi spingono i propri beniamini.",
        "fraseggio prolungato a centrocampo, le squadre cercano il varco giusto.",
        "si intensifica il riscaldamento sulla panchina, pronti nuovi cambi tattici.",
        "errore banale in fase di impostazione, brivido per l'allenatore in panchina.",
        "il pressing alto inizia a dare i suoi frutti, avversari chiusi nella propria metà campo.",
        "gioco momentaneamente fermo per un contrasto a centrocampo."
    ]
    
    # --- 1. EVENTI SISTEMA ---
    cronaca.append({"minuto": 0, "squadra": "casa", "tipo": "info", "testo": f"🏁 [SISTEMA] FISCHIO D'INIZIO! Inizia {h} vs {a}!"})
    
    recupero_pt = random.randint(1, 4)
    cronaca.append({"minuto": 45, "squadra": "casa", "tipo": "info", "testo": f"⏱️ [SISTEMA] Segnalati {recupero_pt} minuti di recupero nel primo tempo."})
    cronaca.append({"minuto": 45 + recupero_pt, "squadra": "casa", "tipo": "info", "testo": "☕ [SISTEMA] FINE PRIMO TEMPO. Squadre negli spogliatoi."})
    
    recupero_st = random.randint(2, 7)
    cronaca.append({"minuto": 90, "squadra": "casa", "tipo": "info", "testo": f"⏱️ [SISTEMA] Il quarto uomo indica {recupero_st} minuti di recupero."})
    
    minuti_usati.update([0, 45, 45 + recupero_pt, 90])
    
    # --- 2. GOL SINCRONIZZATI (ESATTAMENTE gh per casa, ga per ospite) ---
    # GOL CASA
    for i in range(gh):
        min_gol = random.randint(5, 85)
        tentativi = 0
        while min_gol in minuti_usati and tentativi < 100:
            min_gol = random.randint(5, 85)
            tentativi += 1
        
        if tentativi >= 100:
            continue
        
        minuti_usati.add(min_gol)
        
        is_penalty = random.random() > 0.85
        
        if is_penalty:
            cronaca.append({"minuto": min_gol, "squadra": "casa", "tipo": "rigore_fischio", "testo": f"📢 [{h}] CALCIO DI RIGORE! Il direttore di gara indica il dischetto!"})
            if min_gol + 1 not in minuti_usati:
                cronaca.append({"minuto": min_gol + 1, "squadra": "casa", "tipo": "gol", "testo": f"🎯 [{h}] GOAL SU RIGORE! Esecuzione perfetta dal dischetto!"})
                minuti_usati.add(min_gol + 1)
        else:
            tipo_gol = rand(["Conclusione potente!", "Di testa su cross!", "Azione corale!", "Tap-in vincente!"])
            cronaca.append({"minuto": min_gol, "squadra": "casa", "tipo": "gol", "testo": f"⚽ [{h}] GOOOL! {tipo_gol}"})
    
    # GOL OSPITE
    for i in range(ga):
        min_gol = random.randint(5, 85)
        tentativi = 0
        while min_gol in minuti_usati and tentativi < 100:
            min_gol = random.randint(5, 85)
            tentativi += 1
        
        if tentativi >= 100:
            continue
        
        minuti_usati.add(min_gol)
        
        is_penalty = random.random() > 0.85
        
        if is_penalty:
            cronaca.append({"minuto": min_gol, "squadra": "ospite", "tipo": "rigore_fischio", "testo": f"📢 [{a}] CALCIO DI RIGORE! Massima punizione per gli ospiti!"})
            if min_gol + 1 not in minuti_usati:
                cronaca.append({"minuto": min_gol + 1, "squadra": "ospite", "tipo": "gol", "testo": f"🎯 [{a}] GOAL SU RIGORE! Freddissimo dagli undici metri!"})
                minuti_usati.add(min_gol + 1)
        else:
            tipo_gol = rand(["Zittisce lo stadio!", "Contropiede micidiale!", "Incredibile girata!", "Palla nel sette!"])
            cronaca.append({"minuto": min_gol, "squadra": "ospite", "tipo": "gol", "testo": f"⚽ [{a}] GOOOL! {tipo_gol}"})
    
    # --- 3. CARTELLINI (3-6 casuali) ---
    num_gialli = random.randint(3, 6)
    for _ in range(num_gialli):
        min_cart = random.randint(10, 88)
        tentativi = 0
        while min_cart in minuti_usati and tentativi < 100:
            min_cart = random.randint(10, 88)
            tentativi += 1
        
        if tentativi >= 100:
            continue
        
        minuti_usati.add(min_cart)
        sq = random.choice(["casa", "ospite"])
        team = h if sq == "casa" else a
        cronaca.append({"minuto": min_cart, "squadra": sq, "tipo": "cartellino", "testo": f"🟨 [{team}] Giallo per un fallo tattico a centrocampo."})
    
    # --- 4. EVENTI DAI POOL (35-40 eventi distribuiti) ---
    eventi_per_tempo = 18
    
    for tempo in [1, 2]:
        min_base = 1 if tempo == 1 else 46
        min_max = 45 if tempo == 1 else 90
        intervallo = (min_max - min_base) / eventi_per_tempo
        
        for i in range(eventi_per_tempo):
            min_evento = int(min_base + (i * intervallo) + random.uniform(0, intervallo - 1))
            
            if min_evento in minuti_usati:
                continue
            
            minuti_usati.add(min_evento)
            
            sq = random.choice(["casa", "ospite"])
            team = h if sq == "casa" else a
            
            # Scelta pool equilibrata
            roll = random.random()
            if roll > 0.75:
                txt = rand(pool_portiere)
            elif roll > 0.50:
                txt = rand(pool_attacco)
            elif roll > 0.25:
                txt = rand(pool_difesa)
            else:
                txt = rand(pool_atmosfera)
            
            cronaca.append({"minuto": min_evento, "squadra": sq, "tipo": "info", "testo": f"[{team}] {txt}"})
    
    # ✅ ORDINA PER MINUTO
    cronaca.sort(key=lambda x: x["minuto"])
    
    # ✅ RIMUOVI DUPLICATI: Tieni solo la prima occorrenza di ogni evento
    cronaca_unica = []
    eventi_visti = set()
    
    for evento in cronaca:
        # Crea una chiave unica (minuto + tipo + testo)
        chiave = f"{evento['minuto']}-{evento['tipo']}-{evento['testo']}"
        
        if chiave not in eventi_visti:
            eventi_visti.add(chiave)
            cronaca_unica.append(evento)
    
    return cronaca_unica

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

    # ✅ NUOVO: USA LA FUNZIONE DENSA
    cronaca = genera_cronaca_live_densa(gh, ga, team_h, team_a, h2h_data)

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
    # ✅ AGGIUNGI QUESTE VARIABILI DI TRACKING ALL'INIZIO
    actual_cycles_executed = 0
    start_time = datetime.now()
    try:
        from ai_engine.deep_analysis import DeepAnalyzer
        analyzer = DeepAnalyzer()
        team_h_doc = db.teams.find_one({"name": home_team}) or {}
        team_a_doc = db.teams.find_one({"name": away_team}) or {}
        
        league_clean = league.replace('_', ' ').title()
        h2h_doc = db.h2h_by_round.find_one({"league": league_clean})
        match_data = next((m for m in h2h_doc.get('matches', []) if m['home'] == home_team), {})
        h2h_data = match_data.get('h2h_data', {})

        # 1. ESECUZIONE ALGORITMO E CREAZIONE sim_list
        sim_list = [] 
        preloaded_data = preload_match_data(home_team, away_team)
        
        from ai_engine.deep_analysis import DeepAnalyzer
        analyzer = DeepAnalyzer()
        analyzer.start_match(home_team, away_team, league=league)
        
        if algo_id == 6:
        # ✅ PASSA ESPLICITAMENTE cycles e algo_id alla funzione
            res = run_monte_carlo_verdict_detailed(
                preloaded_data, 
                home_team, 
                away_team,
                analyzer=analyzer,  # ✅ Passa l'analyzer
                cycles=cycles,      # ✅ Passa i cicli REALI
                algo_id=algo_id     # ✅ Passa l'ID algoritmo
            )
            gh, ga = res[0]
            
            # ✅ LOG DI VERIFICA
            print(f"🎯 MONTE CARLO ESEGUITO: {cycles} cicli richiesti", file=sys.stderr)
            
            # ✅ STAMPA DI DEBUG (rimuovi dopo il test)
            print(f"🎯 RISULTATO FINALE: {gh}-{ga}", file=sys.stderr)
            
            # ✅ TRACKING CICLI REALI (dal risultato Monte Carlo)
            if len(res) > 4 and isinstance(res[4], dict):
                # Conta i risultati reali eseguiti da tutti gli algoritmi
                for algo_results in res[4].values():
                    if isinstance(algo_results, list):
                        actual_cycles_executed += len(algo_results)
            else:
                actual_cycles_executed = cycles  # Fallback
            
            # Creazione sim_list dai risultati grezzi
            if len(res) > 4 and isinstance(res[4], list):
                sim_list = [f"{r[0]}-{r[1]}" for r in res[4]]
            else:
                sim_list = [f"{gh}-{ga}"] * cycles
            top3 = [x[0] for x in res[2]]
            cronaca = res[1] if len(res) > 1 else [] # Recupero cronaca se disponibile
        else:
            # ✅ LOG DI VERIFICA
            print(f"🎯 ALGORITMO {algo_id} ESEGUITO: {cycles} cicli richiesti", file=sys.stderr)
            
            # ✅ ESEGUI IL SINGOLO ALGORITMO "cycles" VOLTE
            sim_list = []
            for i in range(cycles):
                gh_temp, ga_temp = run_single_algo(algo_id, preloaded_data, home_team, away_team)
                sim_list.append(f"{gh_temp}-{ga_temp}")
                
                # Aggiungi al deep analyzer
                if analyzer:
                    analyzer.add_result(algo_id, gh_temp, ga_temp)
            
            # Calcola il risultato più frequente
            from collections import Counter
            most_common = Counter(sim_list).most_common(1)[0][0]
            gh, ga = map(int, most_common.split("-"))
            top3 = [x[0] for x in Counter(sim_list).most_common(3)]
            cronaca = []
            actual_cycles_executed = cycles

        
        for score in sim_list:
            h, a = map(int, score.split('-'))
            analyzer.add_result(algo_id, h, a)
        analyzer.end_match()
        
        # DEFINIZIONE DI deep_stats
        deep_stats = analyzer.matches[-1]['algorithms'][algo_id]['stats']

        # 3. GENERAZIONE REPORT
        # Usiamo la tua funzione esistente
        anatomy = genera_match_report_completo(gh, ga, h2h_data, team_h_doc, team_a_doc, sim_list, deep_stats)

        # PULIZIA FINALE: Rimuove i NaN prima di inviare al frontend
        #
        quote_match = {
            "1": team_h_doc.get('odds', {}).get('1'),
            "X": team_h_doc.get('odds', {}).get('X'),
            "2": team_h_doc.get('odds', {}).get('2')
        }

        # 2. CHIAMATA AL CERVELLO (Betting Logic)
        # Passiamo la 'sim_list' (la lista di tutti i 1000+ risultati) e le quote
        report_pro = analyze_betting_data(sim_list, quote_match)

        # 3. INTEGRAZIONE NEL RISULTATO FINALE
        raw_result = {
            "success": True,
            "predicted_score": f"{gh}-{ga}",
            "gh": gh,
            "ga": ga,
            "algo_name": ALGO_NAMES.get(algo_id, "Custom"),
            
            # ✅ AGGIUNGI QUESTI CAMPI NUOVI
            "algo_id": algo_id,  # ✅ ID algoritmo reale
            "cycles_requested": cycles,  # ✅ Cicli richiesti dall'utente
            "cycles_executed": actual_cycles_executed,  # ✅ Cicli REALMENTE eseguiti
            "execution_time": (datetime.now() - start_time).total_seconds(),  # ✅ Tempo reale
            
            "statistiche": anatomy["statistiche"],
            "cronaca": anatomy["cronaca"],
            # AGGIUNGIAMO IL REPORT PROFESSIONALE QUI
            "report_scommesse_pro": report_pro, 
            "info_extra": {
                "valore_mercato": f"{team_h_doc.get('stats', {}).get('marketValue', 0) // 1000000}M €",
                "motivazione": "Analisi Monte Carlo con rilevamento Value Bet e Dispersione."
            }
        }
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