#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import random
import math
import time
from datetime import datetime

# --- CONFIGURAZIONE PERCORSI (UNA VOLTA SOLA) ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- IMPORT MOTORE E DB ---
try:
    from ai_engine.universal_simulator import (
        preload_match_data,
        run_single_algo,
        run_monte_carlo_verdict_detailed,
        get_sign,
        get_round_number,
        has_valid_results,
        load_tuning
    )
    from ai_engine.calculators.bulk_manager import get_all_data_bulk
    from config import db
    from ai_engine.deep_analysis import DeepAnalyzer
    from betting_logic import analyze_betting_data
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
        if math.isnan(data) or math.isinf(data):
            return 0.0
    return data

def ottieni_nomi_giocatori(h2h_data):
    """Estrae nomi giocatori dalle formazioni database"""
    formazioni = h2h_data.get('formazioni', {})
    titolari_h = formazioni.get('home_squad', {}).get('titolari', [])
    titolari_a = formazioni.get('away_squad', {}).get('titolari', [])
    
    def filtra_marcatori(squad):
        nomi = []
        for p in squad:
            ruolo = p.get('role', '')
            if ruolo in ['ATT', 'MID']:
                nome = p.get('player', 'Giocatore')
                nomi.append(nome)
        return nomi if nomi else ['Attaccante', 'Centrocampista', 'Ala']
    
    return filtra_marcatori(titolari_h), filtra_marcatori(titolari_a)

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

    # ✅ FUNZIONI PER RECUPERO REALISTICO
    def get_recupero_primo_tempo():
        """Recupero PT: 1-6 minuti, media ~2, raro dopo 4"""
        rand_val = random.random() * 100
        if rand_val < 25: return 1
        if rand_val < 55: return 2
        if rand_val < 80: return 3
        if rand_val < 92: return 4
        if rand_val < 98: return 5
        return 6

    def get_recupero_secondo_tempo():
        """Recupero ST: 2-10 minuti, media ~4, raro dopo 6"""
        rand_val = random.random() * 100
        if rand_val < 10: return 2
        if rand_val < 30: return 3
        if rand_val < 55: return 4
        if rand_val < 75: return 5
        if rand_val < 88: return 6
        if rand_val < 95: return 7
        if rand_val < 98: return 8
        if rand_val < 99.5: return 9
        return 10

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

    # --- 1. EVENTI SISTEMA E FORMAZIONI ---
    formazioni = h2h_data.get('formazioni', {})
    home_squad = formazioni.get('home_squad', {})
    away_squad = formazioni.get('away_squad', {})

    if home_squad and away_squad:
        modulo_h = home_squad.get('modulo', '4-3-3')
        titolari_h = home_squad.get('titolari', [])
        modulo_a = away_squad.get('modulo', '4-3-3')
        titolari_a = away_squad.get('titolari', [])

        formazione_h_str = f"📋 [{h}] ({modulo_h}): "
        giocatori_h = []
        for p in titolari_h:
            nome = p.get('player', 'N/A')
            cognome = nome.split()[-1] if nome else 'N/A'
            giocatori_h.append(cognome)
        formazione_h_str += ", ".join(giocatori_h)

        formazione_a_str = f"📋 [{a}] ({modulo_a}): "
        giocatori_a = []
        for p in titolari_a:
            nome = p.get('player', 'N/A')
            cognome = nome.split()[-1] if nome else 'N/A'
            giocatori_a.append(cognome)
        formazione_a_str += ", ".join(giocatori_a)

        cronaca.append({"minuto": -2, "squadra": "casa", "tipo": "formazione", "testo": formazione_h_str})
        cronaca.append({"minuto": -1, "squadra": "ospite", "tipo": "formazione", "testo": formazione_a_str})

    cronaca.append({"minuto": 0, "squadra": "casa", "tipo": "info", "testo": f"🏁 [SISTEMA] FISCHIO D'INIZIO! Inizia {h} vs {a}!"})

    recupero_pt = get_recupero_primo_tempo()
    cronaca.append({"minuto": 45, "squadra": "casa", "tipo": "info", "testo": f"⏱️ [SISTEMA] Segnalati {recupero_pt} minuti di recupero nel primo tempo."})
    cronaca.append({"minuto": 45 + recupero_pt, "squadra": "casa", "tipo": "info", "testo": "☕ [SISTEMA] FINE PRIMO TEMPO. Squadre negli spogliatoi."})

    recupero_st = get_recupero_secondo_tempo()
    cronaca.append({"minuto": 90, "squadra": "casa", "tipo": "info", "testo": f"⏱️ [SISTEMA] Il quarto uomo indica {recupero_st} minuti di recupero."})

    minuti_usati.update([0, 45, 45 + recupero_pt, 90])

    # --- 2. GOL SINCRONIZZATI (ESATTAMENTE gh per casa, ga per ospite) ---
    marcatori_casa, marcatori_ospite = ottieni_nomi_giocatori(h2h_data)

    def gol_nel_recupero():
        """12% di probabilità che un gol sia nei minuti di recupero"""
        return random.random() < 0.12

    def trova_minuto_libero(minuti_usati_local, min_range=(5, 89), allow_recupero=False):
        """Trova SEMPRE un minuto libero, espandendo il range se necessario"""
        min_val, max_val = min_range

        for _ in range(100):
            min_gol = random.randint(min_val, max_val)
            if min_gol not in minuti_usati_local:
                return min_gol

        tutti_minuti = set(range(1, 90))
        disponibili = tutti_minuti - minuti_usati_local
        if disponibili:
            return random.choice(list(disponibili))

        if allow_recupero:
            for m in range(46, 46 + recupero_pt):
                if m not in minuti_usati_local:
                    return m
            for m in range(91, 91 + recupero_st):
                if m not in minuti_usati_local:
                    return m

        return random.randint(1, 89)

    def format_minuto(min_gol):
        if 46 <= min_gol <= 45 + recupero_pt:
            return f"45+{min_gol - 45}"
        elif 91 <= min_gol <= 90 + recupero_st:
            return f"90+{min_gol - 90}"
        else:
            return str(min_gol)

    # GOL CASA
    for i in range(gh):
        if gol_nel_recupero():
            if random.random() < 0.7 and recupero_st > 0:
                min_gol = random.randint(91, 90 + recupero_st)
            elif recupero_pt > 0:
                min_gol = random.randint(46, 45 + recupero_pt)
            else:
                min_gol = trova_minuto_libero(minuti_usati, allow_recupero=True)
            
            while min_gol in minuti_usati:
                min_gol = trova_minuto_libero(minuti_usati, allow_recupero=True)
        else:
            min_gol = trova_minuto_libero(minuti_usati, allow_recupero=True)
        
        minuti_usati.add(min_gol)

        is_penalty = random.random() < 0.15
        marcatore = rand(marcatori_casa)
        min_display = format_minuto(min_gol)
        
        prefisso = ""
        frasi_recupero_pt = [
            "⏱️ ALLO SCADERE DEL PRIMO TEMPO! ",
            "🔥 IN PIENO RECUPERO! ",
            "⚡ PRIMA DELL'INTERVALLO! "
        ]
        frasi_recupero = [
            "🔥 IN PIENO RECUPERO! ",
            "⏱️ AL FOTOFINISH! ",
            "⚡ ALL'ULTIMO RESPIRO! ",
            "🚨 CLAMOROSO NEL RECUPERO! "
        ]

        if "+" in min_display:
            if min_display.startswith("45+"):
                prefisso = rand(frasi_recupero_pt)
            elif min_display.startswith("90+"):
                prefisso = rand(frasi_recupero)

        if is_penalty:
            cronaca.append({"minuto": min_gol, "squadra": "casa", "tipo": "rigore_fischio", "testo": f"{min_display}' 📢 {prefisso}[{h}] CALCIO DI RIGORE! Il direttore di gara indica il dischetto!"})
            min_gol_rigore = min_gol + 1
            if min_gol_rigore in minuti_usati:
                min_gol_rigore = trova_minuto_libero(minuti_usati, (min_gol + 1, min_gol + 3), allow_recupero=True)
            minuti_usati.add(min_gol_rigore)
            min_rig_display = format_minuto(min_gol_rigore)
            cronaca.append({"minuto": min_gol_rigore, "squadra": "casa", "tipo": "gol", "testo": f"{min_rig_display}' 🎯 {prefisso}[{h}] GOAL SU RIGORE! {marcatore} - Freddissimo dagli undici metri!"})
        else:
            tipo_gol = rand(["Conclusione potente!", "Di testa su cross!", "Azione corale!", "Tap-in vincente!"])
            cronaca.append({"minuto": min_gol, "squadra": "casa", "tipo": "gol", "testo": f"{min_display}' ⚽ {prefisso}[{h}] GOOOL! {marcatore} - {tipo_gol}"})

    # GOL OSPITE
    for i in range(ga):
        if gol_nel_recupero():
            if random.random() < 0.7 and recupero_st > 0:
                min_gol = random.randint(91, 90 + recupero_st)
            elif recupero_pt > 0:
                min_gol = random.randint(46, 45 + recupero_pt)
            else:
                min_gol = trova_minuto_libero(minuti_usati, allow_recupero=True)
            
            while min_gol in minuti_usati:
                min_gol = trova_minuto_libero(minuti_usati, allow_recupero=True)
        else:
            min_gol = trova_minuto_libero(minuti_usati, allow_recupero=True)
        
        minuti_usati.add(min_gol)

        is_penalty = random.random() < 0.15
        marcatore = rand(marcatori_ospite)
        min_display = format_minuto(min_gol)
        
        prefisso = ""
        frasi_recupero_pt = [
            "⏱️ ALLO SCADERE DEL PRIMO TEMPO! ",
            "🔥 IN PIENO RECUPERO! ",
            "⚡ PRIMA DELL'INTERVALLO! "
        ]
        frasi_recupero = [
            "🔥 IN PIENO RECUPERO! ",
            "⏱️ AL FOTOFINISH! ",
            "⚡ ALL'ULTIMO RESPIRO! ",
            "🚨 CLAMOROSO NEL RECUPERO! "
        ]

        if "+" in min_display:
            if min_display.startswith("45+"):
                prefisso = rand(frasi_recupero_pt)
            elif min_display.startswith("90+"):
                prefisso = rand(frasi_recupero)

        if is_penalty:
            cronaca.append({"minuto": min_gol, "squadra": "ospite", "tipo": "rigore_fischio", "testo": f"{min_display}' 📢 {prefisso}[{a}] CALCIO DI RIGORE! Massima punizione per gli ospiti!"})
            min_gol_rigore = min_gol + 1
            if min_gol_rigore in minuti_usati:
                min_gol_rigore = trova_minuto_libero(minuti_usati, (min_gol + 1, min_gol + 3), allow_recupero=True)
            minuti_usati.add(min_gol_rigore)
            min_rig_display = format_minuto(min_gol_rigore)
            cronaca.append({"minuto": min_gol_rigore, "squadra": "ospite", "tipo": "gol", "testo": f"{min_rig_display}' 🎯 {prefisso}[{a}] GOAL SU RIGORE! {marcatore} - Freddissimo dagli undici metri!"})
        else:
            tipo_gol = rand(["Zittisce lo stadio!", "Contropiede micidiale!", "Incredibile girata!", "Palla nel sette!"])
            cronaca.append({"minuto": min_gol, "squadra": "ospite", "tipo": "gol", "testo": f"{min_display}' ⚽ {prefisso}[{a}] GOOOL! {marcatore} - {tipo_gol}"})

    # --- 3. CARTELLINI (3-6 casuali, con possibilità rosso) ---
    num_cartellini = random.randint(3, 6)
    for _ in range(num_cartellini):
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

        is_rosso = random.random() < 0.12

        if is_rosso:
            motivo_rosso = rand(["Fallo da ultimo uomo!", "Condotta violenta!", "Doppio giallo!", "Grave fallo di gioco!"])
            cronaca.append({"minuto": min_cart, "squadra": sq, "tipo": "rosso", "testo": f"{min_cart}' 🟥 [{team}] ESPULSO! {motivo_rosso}"})
        else:
            motivo_giallo = rand(["Fallo tattico a centrocampo.", "Trattenuta su ripartenza.", "Proteste verso l'arbitro.", "Intervento in ritardo."])
            cronaca.append({"minuto": min_cart, "squadra": sq, "tipo": "cartellino", "testo": f"{min_cart}' 🟨 [{team}] Giallo! {motivo_giallo}"})

    # --- 4. EVENTI DAI POOL (distribuiti nei due tempi) ---
    eventi_per_tempo = 10

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

            roll = random.random()
            if roll > 0.75:
                txt = rand(pool_portiere)
            elif roll > 0.50:
                txt = rand(pool_attacco)
            elif roll > 0.25:
                txt = rand(pool_difesa)
            else:
                txt = rand(pool_atmosfera)

            cronaca.append({"minuto": min_evento, "squadra": sq, "tipo": "info", "testo": f"{min_evento}' [{team}] {txt}"})

    cronaca.sort(key=lambda x: x["minuto"])

    cronaca_unica = []
    eventi_visti = set()

    for evento in cronaca:
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
    
    tec_h, tec_a = dna_h.get('tec', 50), dna_a.get('tec', 50)
    att_h, att_a = dna_h.get('att', 50), dna_a.get('att', 50)
    def_h, def_a = dna_h.get('def', 50), dna_a.get('def', 50)

    pos_h = max(35, min(65, int(50 + (tec_h - tec_a)/3 + random.randint(-2, 2))))
    pass_h = int(pos_h * 9.2) + random.randint(-20, 20)
    pass_a = int((100 - pos_h) * 8.8) + random.randint(-20, 20)
    
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

    cronaca = genera_cronaca_live_densa(gh, ga, team_h, team_a, h2h_data)

    tot = len(simulazioni_raw)
    v_h = sum(1 for r in simulazioni_raw if int(str(r).split('-')[0]) > int(str(r).split('-')[1]))
    par = sum(1 for r in simulazioni_raw if int(str(r).split('-')[0]) == int(str(r).split('-')[1]))
    v_a = sum(1 for r in simulazioni_raw if int(str(r).split('-')[0]) < int(str(r).split('-')[1]))
    over = sum(1 for r in simulazioni_raw if sum(map(int, str(r).split('-'))) > 2.5)
    gg = sum(1 for r in simulazioni_raw if all(int(x) > 0 for x in str(r).split('-')))

    from collections import Counter
    top5 = Counter(simulazioni_raw).most_common(5)

    uo = deep_stats.get('under_over', {})
    conf = deep_stats.get('confidence', {})

    report_scommesse = {
        "Bookmaker": {
            "1": f"{deep_stats['sign_1']['pct']}%",
            "X": f"{deep_stats['sign_x']['pct']}%",
            "2": f"{deep_stats['sign_2']['pct']}%",
            "1X": f"{round(deep_stats['sign_1']['pct'] + deep_stats['sign_x']['pct'], 1)}%",
            "X2": f"{round(deep_stats['sign_2']['pct'] + deep_stats['sign_x']['pct'], 1)}%",
            "12": f"{round(deep_stats['sign_1']['pct'] + deep_stats['sign_2']['pct'], 1)}%",
            "U 2.5": f"{uo.get('U2.5', {}).get('pct', 0)}%",
            "O 2.5": f"{uo.get('O2.5', {}).get('pct', 0)}%",
            "GG": f"{deep_stats['gg']['pct']}%",
            "NG": f"{deep_stats['ng']['pct']}%"
        },
        "Analisi_Profonda": {
            "Confidence_Globale": f"{conf.get('global_confidence', 0)}%",
            "Deviazione_Standard_Totale": conf.get('total_std', 0),
            "Affidabilita_Previsione": f"{conf.get('total_confidence', 0)}%"
        },
        "risultati_esatti_piu_probabili": [
            {"score": s, "pct": f"{round(c/deep_stats['total_simulations']*100, 1)}%"} 
            for s, c in deep_stats.get('top_10_scores', [])[:5]
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
    
    tec_h, tec_a = dna_h.get('tec', 50), dna_a.get('tec', 50)
    att_h, att_a = dna_h.get('att', 50), dna_a.get('att', 50)
    
    pos_h = max(35, min(65, int(50 + (tec_h - tec_a)/3 + random.randint(-2, 2))))
    
    tiri_h = int(att_h / 5) + random.randint(2, 8)
    tiri_a = int(att_a / 5) + random.randint(2, 8)
    
    sog_h = min(tiri_h, gh + random.randint(1, 4))
    sog_a = min(tiri_a, ga + random.randint(1, 4))

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

    tot = len(sim_list)
    if tot == 0:
        tot = 1
    
    v_h = sum(1 for r in sim_list if int(str(r).split('-')[0]) > int(str(r).split('-')[1]))
    par = sum(1 for r in sim_list if int(str(r).split('-')[0]) == int(str(r).split('-')[1]))
    v_a = sum(1 for r in sim_list if int(str(r).split('-')[0]) < int(str(r).split('-')[1]))
    over = sum(1 for r in sim_list if sum(map(int, str(r).split('-'))) > 2.5)
    gg = sum(1 for r in sim_list if all(int(x) > 0 for x in str(r).split('-')))
    
    report_bet = {
        "Bookmaker": {
            "1": f"{round(v_h/tot*100, 1)}%",
            "X": f"{round(par/tot*100, 1)}%",
            "2": f"{round(v_a/tot*100, 1)}%",
            "U 2.5": f"{round((tot-over)/tot*100, 1)}%",
            "O 2.5": f"{round(over/tot*100, 1)}%",
            "GG": f"{round(gg/tot*100, 1)}%",
            "NG": f"{round((tot-gg)/tot*100, 1)}%",
            "1X": f"{round((v_h+par)/tot*100, 1)}%",
            "12": f"{round((v_h+v_a)/tot*100, 1)}%",
            "X2": f"{round((v_a+par)/tot*100, 1)}%"
        },
        "risultati_esatti_piu_probabili": [
            {"score": s, "pct": f"{round(f/tot*100, 1)}%"} 
            for s, f in Counter(sim_list).most_common(5)
        ]
    }
    
    return stats, report_bet

def run_single_simulation(home_team: str, away_team: str, algo_id: int, cycles: int, league: str, main_mode: int, bulk_cache=None) -> dict:
    """Esegue la simulazione e arricchisce il risultato con i dati del DB."""
    
    t_inizio_funzione = time.time()
    start_full_process = time.time()
    start_time = datetime.now()
    
    sim_list = []
    quote_match = {"1": 2.5, "X": 3.0, "2": 2.8}
    report_pro = None
    cronaca = []
    xg_info = None
    pesi = None
    params = None
    sc_h = None
    sc_a = None
    odds_real = {}
    team_h_doc = {}
    team_a_doc = {}
    h2h_doc = None
    matchdata = None
    h2h_data = {}
    actual_cycles_executed = 0
    gh = 0
    ga = 0
    top3 = []
    deep_stats = {}
    
    print(f"\n🚀 [START] Richiesta ricevuta alle: {datetime.now().strftime('%H:%M:%S.%f')}", file=sys.stderr)
    debug_logs = []
    
    def log_debug(msg):
        """Helper per loggare sia su stderr che nella lista"""
        print(msg, file=sys.stderr)
        debug_logs.append(msg)
    
    try:
        # ═══════════════════════════════════════════════════════════
        # 1. INIZIALIZZAZIONE ANALYZER
        # ═══════════════════════════════════════════════════════════
        t_init = time.time()
        #log_debug("🔍 [DEBUG 1] Importazione DeepAnalyzer...")
        from ai_engine.deep_analysis import DeepAnalyzer
        
        #log_debug("🔍 [DEBUG 2] Creazione istanza analyzer...")
        analyzer = DeepAnalyzer()
        
        #log_debug(f"🔍 [DEBUG 3] Chiamata start_match(home={home_team}, away={away_team}, league={league})...")
        analyzer.start_match(home_team, away_team, league=league)
        
        #log_debug(f"⏱️ [1. INIT] Analyzer pronto in: {time.time() - t_init:.3f}s")
        
        # ═══════════════════════════════════════════════════════════
        # 2. RISOLUZIONE ALIAS SQUADRE
        # ═══════════════════════════════════════════════════════════
        t_alias = time.time()
        #log_debug("🔍 [DEBUG 4] Query MongoDB per team_h_doc...")
        
        team_h_doc = db.teams.find_one({
            "$or": [
                {"name": home_team},
                {"aliases": home_team},
                {"aliases_transfermarkt": home_team}
            ]
        })
        
        #log_debug(f"🔍 [DEBUG 5] team_h_doc trovato: {team_h_doc is not None}")
        if team_h_doc is None:
            team_h_doc = {"name": home_team}
            #log_debug(f"⚠️ [DEBUG 5.1] team_h_doc era None, usato fallback")

        #log_debug("🔍 [DEBUG 6] Query MongoDB per team_a_doc...")
        team_a_doc = db.teams.find_one({
            "$or": [
                {"name": away_team},
                {"aliases": away_team},
                {"aliases_transfermarkt": away_team}
            ]
        })
        
        #log_debug(f"🔍 [DEBUG 7] team_a_doc trovato: {team_a_doc is not None}")
        if team_a_doc is None:
            team_a_doc = {"name": away_team}
            #log_debug(f"⚠️ [DEBUG 7.1] team_a_doc era None, usato fallback")
        
        #log_debug(f"⏱️ [2. ALIAS] Nomi risolti in: {time.time() - t_alias:.3f}s")
        
        # ═══════════════════════════════════════════════════════════
        # 3. RICERCA MATCH NEL DATABASE (H2H)
        # ═══════════════════════════════════════════════════════════
        t_h2h = time.time()
        ##log_debug("🔍 [DEBUG 8] Pulizia nome lega...")
        
        league_clean = league.replace('_', ' ').title()

        # Normalizzazione nomi leghe (SOLO quelle presenti nel simulatore)
        league_map = {
            "Serie A": "Serie A",
            "Serie B": "Serie B",
            "Serie C - Girone A": "Serie C - Girone A",
            "Serie C - Girone B": "Serie C - Girone B",
            "Serie C - Girone C": "Serie C - Girone C",
            "Premier League": "Premier League",
            "La Liga": "La Liga",
            "Bundesliga": "Bundesliga",
            "Ligue 1": "Ligue 1",
            "Eredivisie": "Eredivisie",
            "Liga Portugal": "Liga Portugal"
        }

        league_clean = league_map.get(league_clean, league_clean)
        
        #log_debug(f"🔍 [DEBUG 9] League: '{league}' -> '{league_clean}'")
        #log_debug(f"🔍 [DEBUG 10] Costruzione pipeline aggregation...")
        
        pipeline = [
            {"$unwind": "$matches"},
            {"$match": {
                "league": league_clean,
                "$or": [
                    {
                        "matches.home": home_team,
                        "matches.away": away_team,
                        "matches.h2h_data": {"$exists": True}
                    },
                    {
                        "matches.home": {"$regex": f"^{home_team}$", "$options": "i"},
                        "matches.away": {"$regex": f"^{away_team}$", "$options": "i"},
                        "matches.h2h_data": {"$exists": True}
                    }
                ]
            }},
            {"$sort": {"last_updated": -1}},
            {"$limit": 1},
            {"$project": {"match": "$matches"}}
        ]

        #log_debug("🔍 [DEBUG 11] Esecuzione aggregation query...")
        result = list(db["h2h_by_round"].aggregate(pipeline))
        
        #log_debug(f"🔍 [DEBUG 12] Risultati trovati: {len(result)}")
        
        if result:
            #log_debug("🔍 [DEBUG 13] Estrazione matchdata dal result[0]...")
            matchdata = result[0].get("match") if result[0] else None
            
            #log_debug(f"🔍 [DEBUG 14] matchdata è None? {matchdata is None}")
            
            if matchdata:
                h2h_data = matchdata.get("h2h_data", {})
                #log_debug(f"✅ Match trovato: {matchdata.get('home', 'N/A')} vs {matchdata.get('away', 'N/A')}")
                #log_debug(f"🔍 [DEBUG 15] h2h_data keys: {list(h2h_data.keys()) if h2h_data else 'VUOTO'}")
            else:
                log_debug(f"⚠️ [DEBUG 14.1] matchdata era None dopo estrazione!")
        else:
            log_debug(f"⚠️ Match non trovato in h2h_by_round per {home_team} vs {away_team}")

        log_debug(f"⏱️ [3. DB SEARCH] H2H trovato in: {time.time() - t_h2h:.3f}s")

        # ═══════════════════════════════════════════════════════════
        # 4. PRELOAD DATI E BULK_CACHE
        # ═══════════════════════════════════════════════════════════
        t_preload = time.time()
       # log_debug("🔍 [DEBUG 16] Verifica bulk_cache...")
        
        if bulk_cache is None:
            #log_debug("📦 Caricamento preloaded_data da zero...")
            preloaded_data = preload_match_data(home_team, away_team)
            
            if preloaded_data is None:
                raise ValueError("❌ preload_match_data ha restituito None!")
            
            bulk_cache = preloaded_data.get('bulk_cache')
            #log_debug(f"✅ bulk_cache caricato, keys: {list(bulk_cache.keys()) if bulk_cache else 'None'}")
        else:
            #log_debug("♻️ Riutilizzo bulk_cache già caricato")
            preloaded_data = preload_match_data(home_team, away_team, bulk_cache=bulk_cache)
            
            if preloaded_data is None:
                raise ValueError("❌ preload_match_data ha restituito None!")
        
        #log_debug(f"🔍 [DEBUG 22] Estrazione real_home/real_away...")
        real_home = preloaded_data.get('home_team', home_team)
        real_away = preloaded_data.get('away_team', away_team)
        
        #log_debug(f"🔍 [DEBUG 23] real_home='{real_home}', real_away='{real_away}'")
        #log_debug(f"⏱️ [4. PRELOAD] Dati caricati in: {time.time() - t_preload:.3f}s")

        # ═══════════════════════════════════════════════════════════
        # 5. ESECUZIONE ALGORITMO
        # ═══════════════════════════════════════════════════════════
        t_exec_start = time.time()
        #log_debug(f"🎯 SIMULAZIONE: Algo {algo_id}, Cicli {cycles}")
        
        if algo_id == 6:
            # ─────────────────────────────────────────────────────────
            # ALGORITMO MONTE CARLO
            # ─────────────────────────────────────────────────────────
            #log_debug('🔵 MODALITÀ MONTE CARLO ATTIVATA')
            
            if not isinstance(bulk_cache, dict) or 'MASTER_DATA' not in bulk_cache or 'ALL_ROUNDS' not in bulk_cache:
                #log_debug("📦 Ricarico bulk_cache per MonteCarlo...")
                bulk_cache = get_all_data_bulk(home_team, away_team, league)
                if not isinstance(bulk_cache, dict):
                    raise ValueError(f"❌ get_all_data_bulk ha restituito {type(bulk_cache)}!")
            
            team_h_scores = bulk_cache.get('MASTER_DATA', {}).get(home_team, {})
            team_a_scores = bulk_cache.get('MASTER_DATA', {}).get(away_team, {})
            h2h_stats = bulk_cache.get('H2H_HISTORICAL')
            
            # Cerca matchdata in ALL_ROUNDS
            for round_doc in bulk_cache.get("ALL_ROUNDS", []):
                if isinstance(round_doc, dict):
                    for match in round_doc.get("matches", []):
                        if isinstance(match, dict):
                            if match.get("home") == home_team and match.get("away") == away_team:
                                matchdata = match
                                h2h_data = match.get("h2h_data", {})
                                break
                if matchdata:
                    break
            
            if matchdata is None:
                raise ValueError(f"❌ Match {home_team} vs {away_team} non trovato in ALL_ROUNDS!")
            
            res = run_monte_carlo_verdict_detailed(
                preloaded_data, 
                home_team, 
                away_team, 
                analyzer=analyzer, 
                cycles=cycles, 
                algo_id=algo_id,
                bulk_cache=bulk_cache
            )

            gh, ga = res[0]
            actual_cycles_executed = res[5] if len(res) > 5 else cycles
            
            if len(res) > 4 and isinstance(res[4], dict):
                for algo_res_list in res[4].values():
                    if isinstance(algo_res_list, list):
                        sim_list.extend(algo_res_list)
            elif len(res) > 4 and isinstance(res[4], list):
                sim_list = [f"{r[0]}-{r[1]}" for r in res[4]]
            else:
                sim_list = [f"{gh}-{ga}"] * cycles
            
            top3 = [x[0] for x in res[2]] if len(res) > 2 else []
            cronaca = res[1] if len(res) > 1 else []
            
            #log_debug(f"✅ MONTE CARLO: {actual_cycles_executed} cicli, risultato {gh}-{ga}")
        
        else:
# ─────────────────────────────────────────────────────────
            # ALGORITMI SINGOLI (1-5)
            # ─────────────────────────────────────────────────────────
            #log_debug(f"🟢 ALGORITMO SINGOLO {algo_id} ATTIVATO")
            
            if not isinstance(bulk_cache, dict) or 'MASTER_DATA' not in bulk_cache or 'ALL_ROUNDS' not in bulk_cache:
                #log_debug("📦 Ricarico bulk_cache...")
                bulk_cache = get_all_data_bulk(home_team, away_team, league)
                if not isinstance(bulk_cache, dict):
                    raise ValueError(f"❌ get_all_data_bulk ha restituito {type(bulk_cache)}!")
            
            team_h_scores = bulk_cache.get('MASTER_DATA', {}).get(home_team, {})
            team_a_scores = bulk_cache.get('MASTER_DATA', {}).get(away_team, {})
            h2h_stats = bulk_cache.get('H2H_HISTORICAL')
            
            for round_doc in bulk_cache.get("ALL_ROUNDS", []):
                if isinstance(round_doc, dict):
                    for match in round_doc.get("matches", []):
                        if isinstance(match, dict):
                            if match.get("home") == home_team and match.get("away") == away_team:
                                matchdata = match
                                h2h_data = match.get("h2h_data", {})
                                break
                if matchdata:
                    break
            
            if matchdata is None:
                raise ValueError(f"❌ Match non trovato!")
            
            settings_in_ram = load_tuning(algo_id)
            
            for i in range(cycles):
                result = run_single_algo(algo_id, preloaded_data, real_home, real_away, 
                                        settings_cache=settings_in_ram, debug_mode=False)
                
                if len(result) == 9:
                    gh_temp, ga_temp, lambda_h, lambda_a, xg_info, pesi, params, sc_h, sc_a = result
                    
                    if analyzer:
                        odds = bulk_cache.get('MATCH_H2H', {}).get('odds')
                        analyzer.add_result(
                            algo_id, gh_temp, ga_temp, 
                            lambda_h=lambda_h, lambda_a=lambda_a,
                            odds_real=odds,
                            odds_qt={'1': h2h_data.get('qt_1'), 'X': h2h_data.get('qt_X'), '2': h2h_data.get('qt_2')},
                            team_scores={'home': team_h_scores, 'away': team_a_scores},
                            h2h_stats=h2h_stats
                        )
                
                elif len(result) == 2:
                    gh_temp, ga_temp = result
                    if analyzer:
                        analyzer.add_result(algo_id, gh_temp, ga_temp)
                else:
                    raise ValueError(f"run_single_algo ritorna {len(result)} valori, attesi 2 o 9")
                
                sim_list.append(f"{gh_temp}-{ga_temp}")
            
            from collections import Counter
            most_common = Counter(sim_list).most_common(1)[0][0]
            gh, ga = map(int, most_common.split("-"))
            top3 = [x[0] for x in Counter(sim_list).most_common(3)]
            cronaca = []
            actual_cycles_executed = cycles
            
            #log_debug(f"✅ ALGORITMO {algo_id}: {cycles} cicli, risultato {gh}-{ga}")
        
        #log_debug(f"⏱️ [5. EXEC] Simulazione completata in: {time.time() - t_exec_start:.3f}s")

        # ═══════════════════════════════════════════════════════════
        # 6. CHIUSURA ANALYZER E ESTRAZIONE DEEP_STATS
        # ═══════════════════════════════════════════════════════════
        t_final = time.time()
        analyzer.end_match()
        #log_debug(f"🔍 [AFTER end_match] analyzer.matches length: {len(analyzer.matches) if analyzer.matches else 0}")
        
        # ✅ GENERA L'HTML DEL REPORT
        report_html = analyzer.get_html_report()
        
        # ✅ Genera Confidence Report
        from confidence_html_builder import ConfidenceHTMLBuilder
        confidence_builder = ConfidenceHTMLBuilder()
        confidence_html = confidence_builder.get_html_report(analyzer.matches)
        log_debug(f"📄 Report HTML generato: {len(report_html)} caratteri")

        if analyzer.matches and len(analyzer.matches) > 0:
            #log_debug(f"🔍 [AFTER end_match] last_match keys: {list(analyzer.matches[-1].keys())}")
            
            last_match = analyzer.matches[-1]
            if 'algorithms' in last_match and algo_id in last_match['algorithms']:
              #  log_debug(f"🔍 [AFTER end_match] algo {algo_id} trovato in algorithms")
                deep_stats = last_match['algorithms'][algo_id]['stats']
                
                if deep_stats is None:
                    log_debug(f"⚠️ deep_stats è None dopo estrazione, uso fallback")
                    deep_stats = {
                        'sign_1': {'pct': 33.3},
                        'sign_x': {'pct': 33.3},
                        'sign_2': {'pct': 33.3},
                        'gg': {'pct': 50},
                        'ng': {'pct': 50},
                        'under_over': {'U2.5': {'pct': 50}, 'O2.5': {'pct': 50}},
                        'confidence': {'global_confidence': 50, 'total_std': 0, 'total_confidence': 50},
                        'top_10_scores': [],
                        'total_simulations': cycles
                    }
                else:
                    log_debug(f"✅ deep_stats estratto correttamente con {len(deep_stats)} chiavi")
            else:
                log_debug(f"⚠️ [AFTER end_match] algo {algo_id} NON trovato, uso fallback")
                deep_stats = {
                    'sign_1': {'pct': 33.3},
                    'sign_x': {'pct': 33.3},
                    'sign_2': {'pct': 33.3},
                    'gg': {'pct': 50},
                    'ng': {'pct': 50},
                    'under_over': {'U2.5': {'pct': 50}, 'O2.5': {'pct': 50}},
                    'confidence': {'global_confidence': 50, 'total_std': 0, 'total_confidence': 50},
                    'top_10_scores': [],
                    'total_simulations': cycles
                }
        else:
            log_debug(f"⚠️ [AFTER end_match] analyzer.matches è vuoto, uso fallback completo")
            deep_stats = {
                'sign_1': {'pct': 33.3},
                'sign_x': {'pct': 33.3},
                'sign_2': {'pct': 33.3},
                'gg': {'pct': 50},
                'ng': {'pct': 50},
                'under_over': {'U2.5': {'pct': 50}, 'O2.5': {'pct': 50}},
                'confidence': {'global_confidence': 50, 'total_std': 0, 'total_confidence': 50},
                'top_10_scores': [],
                'total_simulations': cycles
            }

# ═══════════════════════════════════════════════════════════
        # 7. CARICAMENTO QUOTE E REPORT BETTING
        # ═══════════════════════════════════════════════════════════
        odds_real = matchdata.get('odds', {}) if isinstance(matchdata, dict) else {}
        
        bulk_quotes = bulk_cache.get("MATCH_H2H", {}).get("quotes", {}) if bulk_cache else {}
        if not bulk_quotes or not any(bulk_quotes.values()):
            bulk_quotes = team_h_doc.get('odds', {})
        
        if bulk_quotes and any(bulk_quotes.values()):
            quote_match["1"] = bulk_quotes.get('1', 2.5)
            quote_match["X"] = bulk_quotes.get('X', 3.0)
            quote_match["2"] = bulk_quotes.get('2', 2.8)
        
        log_debug(f"📊 Quote caricate: {quote_match}")
        
        # ✅ AGGIUNGI QUESTO PRIMA DI analyze_betting_data():
        if algo_id == 6:
            # Per MonteCarlo: estrai results dagli algoritmi 2,3,4,5
            sim_list = []
            if deep_stats and 'exact_scores' in deep_stats:
                # Ricostruisci sim_list dalle frequenze
                for score, count in deep_stats['exact_scores'].items():
                    sim_list.extend([score] * count)
            
            log_debug(f"🎲 sim_list creato per MonteCarlo: {len(sim_list)} risultati")
        else:
            # sim_list già esiste per algoritmi singoli
            pass

        log_debug(f"📊 Quote caricate: {quote_match}")

        report_pro = analyze_betting_data(sim_list, quote_match)
        
        anatomy = genera_match_report_completo(gh, ga, h2h_data, team_h_doc, team_a_doc, sim_list, deep_stats)
        
        log_debug(f"⏱️ [6. FINAL] Report generato in: {time.time() - t_final:.3f}s")

        # ═══════════════════════════════════════════════════════════
        # 8. COSTRUZIONE RISULTATO FINALE
        # ═══════════════════════════════════════════════════════════
        debug_info = {
            "1_league_ricevuta": league,
            "2_league_pulita": league_clean,
            "3_h2h_doc_trovato": bool(matchdata),
            "4_num_partite": 1 if matchdata else 0,
            "5_prime_partite": [(matchdata.get('home'), matchdata.get('away'))] if matchdata else [],
            "6_match_cercato": f"{home_team} vs {away_team}",
            "7_match_trovato": f"{matchdata.get('home', 'N/A')} vs {matchdata.get('away', 'N/A')}" if matchdata else "N/A",
            "8_h2h_data_keys": list(h2h_data.keys()) if h2h_data else [],
            "9_formazioni_presenti": bool(h2h_data.get('formazioni')),
            "10_marcatori_casa": ottieni_nomi_giocatori(h2h_data)[0] if h2h_data.get('formazioni') else [],
            "11_marcatori_ospite": ottieni_nomi_giocatori(h2h_data)[1] if h2h_data.get('formazioni') else []
        }

        raw_result = {
            "success": True,
            "debug": debug_info,
            "predicted_score": f"{gh}-{ga}",
            "gh": gh,
            "ga": ga,
            "algo_name": ALGO_NAMES.get(algo_id, "Custom"),
            "algo_id": algo_id,
            "cycles_requested": cycles,
            "cycles_executed": actual_cycles_executed,
            "execution_time": (time.time() - start_full_process),
            "statistiche": anatomy["statistiche"],
            "cronaca": anatomy["cronaca"],
            "report_scommesse_pro": report_pro,
            "report_html": report_html,  # ✅ AGGIUNGI QUESTA RIGA
            "confidence_html": confidence_html,  # ✅ AGGIUNGI
            "debug_blending": {
                "h2h_historical": h2h_stats if 'h2h_stats' in locals() else None,
                "team_home_power": team_h_scores.get('power') if 'team_h_scores' in locals() and team_h_scores else None,
                "team_away_power": team_a_scores.get('power') if 'team_a_scores' in locals() and team_a_scores else None,
                "quotes_available": bool(bulk_cache.get('MATCH_H2H', {}).get('quotes')) if bulk_cache else False,
                "deep_stats_exists": bool(deep_stats)
            },
            "deep_analysis": {
                "global_confidence": {
                    "score": round(deep_stats['confidence']['global_confidence'] / 10, 1),
                    "label": (
                        "ALTISSIMO" if deep_stats['confidence']['global_confidence'] > 85 else
                        "ALTO" if deep_stats['confidence']['global_confidence'] > 70 else
                        "MEDIO" if deep_stats['confidence']['global_confidence'] > 50 else
                        "BASSO"
                    ),
                    "color": (
                        "#00ff88" if deep_stats['confidence']['global_confidence'] > 85 else
                        "#00f0ff" if deep_stats['confidence']['global_confidence'] > 70 else
                        "#ffcc00" if deep_stats['confidence']['global_confidence'] > 50 else
                        "#ff0044"
                    )
                },
                "dispersione": {
                    "std_dev": round(deep_stats['confidence']['total_std'], 2),
                    "risk_level": (
                        "BASSO" if deep_stats['confidence']['total_std'] < 1.5 else
                        "MEDIO" if deep_stats['confidence']['total_std'] < 2.5 else
                        "ALTO"
                    )
                },
                "money_management": {
                    "recommended_stake": (
                        "10%" if deep_stats['confidence']['global_confidence'] > 85 else
                        "7%" if deep_stats['confidence']['global_confidence'] > 70 else
                        "5%" if deep_stats['confidence']['global_confidence'] > 50 else
                        "2%"
                    ),
                    "kelly_criterion": round(
                        (deep_stats['confidence']['global_confidence'] / 100) * 0.10, 
                        3
                    )
                },
                "algo_details": {
                    f"Algoritmo {algo_id}": {
                        "prediction": f"{gh}-{ga}",
                        "probability": round(
                            deep_stats.get('top_10_scores', [[None, 0]])[0][1] / deep_stats.get('total_simulations', 1) * 100,
                            1
                        ) if deep_stats.get('top_10_scores') and len(deep_stats['top_10_scores']) > 0 else 0.0,
                        "metodo": "Poisson + Blending Multi-Source"
                    }
                }
            },
            "info_extra": {
                "valore_mercato": f"{team_h_doc.get('stats', {}).get('marketValue', 0) // 1000000}M €",
                "motivazione": "Analisi Monte Carlo con rilevamento Value Bet e Dispersione."
            }
        }

        #log_debug(f"🏁 [FINISH] Processo completato in: {time.time() - start_full_process:.3f}s\n")
        return sanitize_data(raw_result)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        log_debug(f"❌ ERRORE CRITICO: {str(e)}")
        log_debug(tb)
        return {
            "success": False, 
            "error": str(e),
            "traceback": tb,
            "debug_logs": debug_logs,
            "timestamp": datetime.now().isoformat(),
            "execution_time": time.time() - t_inizio_funzione
        }

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
            bulk_cache = get_all_data_bulk(home_team, away_team, league)
            result = run_single_simulation(home_team, away_team, algo_id, cycles, league, main_mode, bulk_cache=bulk_cache)
        else:
            result = {"success": False, "error": "Solo modalità Singola (4) supportata"}

        final_output = {
            "success": result.get("success", False),
            "timestamp": datetime.now().isoformat(),
            "execution_time": (datetime.now() - start_time).total_seconds(),
            **{k: v for k, v in result.items() if k != "success"} 
        }
        
        print(json.dumps(final_output, ensure_ascii=False), flush=True)

    except Exception as e:
        print(json.dumps({"success": False, "error": f"Critico: {str(e)}"}), flush=True)

if __name__ == "__main__":
    main()