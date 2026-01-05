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
import time
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
        has_valid_results,
        load_tuning
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
                nomi.append(nome)  # ✅ Nome completo
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
        if rand_val < 25: return 1       # 25% → 1 min
        if rand_val < 55: return 2       # 30% → 2 min
        if rand_val < 80: return 3       # 25% → 3 min
        if rand_val < 92: return 4       # 12% → 4 min
        if rand_val < 98: return 5       # 6%  → 5 min
        return 6                          # 2%  → 6 min (raro)

    def get_recupero_secondo_tempo():
        """Recupero ST: 2-10 minuti, media ~4, raro dopo 6"""
        rand_val = random.random() * 100
        if rand_val < 10: return 2       # 10% → 2 min
        if rand_val < 30: return 3       # 20% → 3 min
        if rand_val < 55: return 4       # 25% → 4 min
        if rand_val < 75: return 5       # 20% → 5 min
        if rand_val < 88: return 6       # 13% → 6 min
        if rand_val < 95: return 7       # 7%  → 7 min
        if rand_val < 98: return 8       # 3%  → 8 min
        if rand_val < 99.5: return 9     # 1.5% → 9 min
        return 10                         # 0.5% → 10 min (molto raro)

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

    # ✅ FORMAZIONI PRE-PARTITA
    formazioni = h2h_data.get('formazioni', {})
    home_squad = formazioni.get('home_squad', {})
    away_squad = formazioni.get('away_squad', {})

    if home_squad and away_squad:
        # Modulo e titolari CASA
        modulo_h = home_squad.get('modulo', '4-3-3')
        titolari_h = home_squad.get('titolari', [])

        # Modulo e titolari OSPITE
        modulo_a = away_squad.get('modulo', '4-3-3')
        titolari_a = away_squad.get('titolari', [])

        # Costruisci stringa formazione CASA
        formazione_h_str = f"📋 [{h}] ({modulo_h}): "
        giocatori_h = []
        for p in titolari_h:
            nome = p.get('player', 'N/A')
            cognome = nome.split()[-1] if nome else 'N/A'
            giocatori_h.append(cognome)
        formazione_h_str += ", ".join(giocatori_h)

        # Costruisci stringa formazione OSPITE
        formazione_a_str = f"📋 [{a}] ({modulo_a}): "
        giocatori_a = []
        for p in titolari_a:
            nome = p.get('player', 'N/A')
            cognome = nome.split()[-1] if nome else 'N/A'
            giocatori_a.append(cognome)
        formazione_a_str += ", ".join(giocatori_a)

        # Aggiungi alla cronaca (minuto -2 e -1 per apparire prima del fischio)
        cronaca.append({"minuto": -2, "squadra": "casa", "tipo": "formazione", "testo": formazione_h_str})
        cronaca.append({"minuto": -1, "squadra": "ospite", "tipo": "formazione", "testo": formazione_a_str})

    cronaca.append({"minuto": 0, "squadra": "casa", "tipo": "info", "testo": f"🏁 [SISTEMA] FISCHIO D'INIZIO! Inizia {h} vs {a}!"})

    # ✅ USA LA NUOVA LOGICA PER IL RECUPERO
    recupero_pt = get_recupero_primo_tempo()
    cronaca.append({"minuto": 45, "squadra": "casa", "tipo": "info", "testo": f"⏱️ [SISTEMA] Segnalati {recupero_pt} minuti di recupero nel primo tempo."})
    cronaca.append({"minuto": 45 + recupero_pt, "squadra": "casa", "tipo": "info", "testo": "☕ [SISTEMA] FINE PRIMO TEMPO. Squadre negli spogliatoi."})

    recupero_st = get_recupero_secondo_tempo()
    cronaca.append({"minuto": 90, "squadra": "casa", "tipo": "info", "testo": f"⏱️ [SISTEMA] Il quarto uomo indica {recupero_st} minuti di recupero."})

    minuti_usati.update([0, 45, 45 + recupero_pt, 90])

    # --- 2. GOL SINCRONIZZATI (ESATTAMENTE gh per casa, ga per ospite) ---
    # ✅ Estrai nomi REALI dai dati del database
    marcatori_casa, marcatori_ospite = ottieni_nomi_giocatori(h2h_data)

    # ✅ FUNZIONE PER DECIDERE SE UN GOL VA NEL RECUPERO
    def gol_nel_recupero():
        """12% di probabilità che un gol sia nei minuti di recupero"""
        return random.random() < 0.12

    # ✅ FUNZIONE HELPER: Trova un minuto libero garantito
    def trova_minuto_libero(minuti_usati_local, min_range=(5, 89), allow_recupero=False):
        """Trova SEMPRE un minuto libero, espandendo il range se necessario"""
        min_val, max_val = min_range

        # Prima prova nel range normale
        for _ in range(100):
            min_gol = random.randint(min_val, max_val)
            if min_gol not in minuti_usati_local:
                return min_gol

        # Se non trova, cerca QUALSIASI minuto libero tra 1 e 89
        tutti_minuti = set(range(1, 90))
        disponibili = tutti_minuti - minuti_usati_local
        if disponibili:
            return random.choice(list(disponibili))

        # Se allow_recupero, prova nei minuti di recupero
        if allow_recupero:
            # Recupero primo tempo (46, 47... fino a 45+recupero_pt)
            for m in range(46, 46 + recupero_pt):
                if m not in minuti_usati_local:
                    return m
            # Recupero secondo tempo (91, 92... fino a 90+recupero_st)
            for m in range(91, 91 + recupero_st):
                if m not in minuti_usati_local:
                    return m

        # Ultima risorsa
        return random.randint(1, 89)

    # ✅ FUNZIONE PER FORMATTARE IL MINUTO (es. 45+2, 90+5)
    def format_minuto(min_gol):
        if 46 <= min_gol <= 45 + recupero_pt:
            return f"45+{min_gol - 45}"
        elif 91 <= min_gol <= 90 + recupero_st:
            return f"90+{min_gol - 90}"
        else:
            return str(min_gol)

    # GOL CASA
    for i in range(gh):
        # Decidi se questo gol va nel recupero (12% probabilità)
        if gol_nel_recupero():
            # 70% nel recupero ST, 30% nel recupero PT
            if random.random() < 0.7 and recupero_st > 0:
                min_gol = random.randint(91, 90 + recupero_st)
            elif recupero_pt > 0:
                min_gol = random.randint(46, 45 + recupero_pt)
            else:
                min_gol = trova_minuto_libero(minuti_usati, allow_recupero=True)
            
            # Assicurati che non sia già usato
            while min_gol in minuti_usati:
                min_gol = trova_minuto_libero(minuti_usati, allow_recupero=True)
        else:
            min_gol = trova_minuto_libero(minuti_usati, allow_recupero=True)
        
        minuti_usati.add(min_gol)

        is_penalty = random.random() < 0.15  # 15% probabilità rigore
        marcatore = rand(marcatori_casa)
        min_display = format_minuto(min_gol)
        
        # 🔥 PREFISSO SPECIALE PER GOL NEL RECUPERO
        prefisso = ""

        # Definisci le frasi PRIMA dell'if
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

        # Ora usa le liste
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
        # Decidi se questo gol va nel recupero (12% probabilità)
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
        
        # 🔥 PREFISSO SPECIALE PER GOL NEL RECUPERO
        prefisso = ""

        # Definisci le frasi PRIMA dell'if
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

        # Ora usa le liste
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

        # 12% probabilità cartellino rosso
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

            cronaca.append({"minuto": min_evento, "squadra": sq, "tipo": "info", "testo": f"{min_evento}' [{team}] {txt}"})

    # ✅ ORDINA PER MINUTO
    cronaca.sort(key=lambda x: x["minuto"])

    # ✅ RIMUOVI DUPLICATI: Tieni solo la prima occorrenza di ogni evento
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
    actual_cycles_executed = 0
    start_time = datetime.now()
    
    try:
        # ✅ CREA ANALYZER ALL'INIZIO (PRIMA DI USARLO)
        from ai_engine.deep_analysis import DeepAnalyzer
        analyzer = DeepAnalyzer()
        analyzer.start_match(home_team, away_team, league=league)
        
        # ✅ CERCA OVUNQUE: Nome principale, Alias o Alias Transfermarkt
        team_h_doc = db.teams.find_one({
            "$or": [
                {"name": home_team},                  # 1. Nome esatto (es. "AC Milan")
                {"aliases": home_team},               # 2. Lista alias (es. "Milan")
                {"aliases_transfermarkt": home_team}  # 3. Alias TM (es. "AC Milan")
            ]
        }) or {"name": home_team}

        team_a_doc = db.teams.find_one({
            "$or": [
                {"name": away_team},
                {"aliases": away_team},
                {"aliases_transfermarkt": away_team}
            ]
        }) or {"name": away_team}
        
        # ✅ FIX: Pulizia nome lega
        league_clean = league.replace('_', ' ').title()
        if league_clean == "Serie A":
            league_clean = "Serie A"
        
        # ✅ RICERCA IBRIDA (VELOCE + FALLBACK)
        match_data = {}
        h2h_data = {}
        h2h_doc = db.h2h_by_round.find_one({
            "league": league_clean,
            "matches": { "$elemMatch": { "home": home_team, "away": away_team } }
        })

        if h2h_doc:
            # Metodo Veloce riuscito
            match_data = next((m for m in h2h_doc['matches'] if m['home'] == home_team and m['away'] == away_team), None)
            h2h_data = match_data.get('h2h_data', {}) if match_data else {}
            print(f"🚀 Metodo Veloce: Match trovato in {h2h_doc.get('round_name')}", file=sys.stderr)
        else:
            # Fallback lento se il veloce fallisce
            print(f"⚠️ Metodo veloce fallito, avvio scansione completa...", file=sys.stderr)
            all_rounds = db.h2h_by_round.find({"league": league_clean})
            for round_doc in all_rounds:
                for m in round_doc.get('matches', []):
                    if m.get('home') == home_team and m.get('away') == away_team:
                        match_data = m
                        h2h_data = m.get('h2h_data', {})
                        h2h_doc = round_doc
                        break
                if match_data: break
        
        # ✅ DEBUG
        print(f"🔍 LEAGUE RICEVUTA: '{league}' -> PULITA: '{league_clean}'", file=sys.stderr)
        print(f"🔍 H2H_DOC TROVATO: {bool(h2h_doc)}", file=sys.stderr)
        
        if not h2h_doc:
            # Prova a cercare con regex case-insensitive
            import re
            h2h_doc = db.h2h_by_round.find_one({"league": {"$regex": f"^{league_clean}$", "$options": "i"}})
            print(f"🔍 TENTATIVO REGEX: {bool(h2h_doc)}", file=sys.stderr)
        
        
        print(f"🔍 MATCH: {match_data.get('home', 'N/A')} vs {match_data.get('away', 'N/A')}", file=sys.stderr)
        print(f"🔍 FORMAZIONI: {bool(h2h_data.get('formazioni'))}", file=sys.stderr)
        
        # ✅ DEBUG: Log per verificare cosa viene caricato
        print(f"🔍 MATCH CERCATO: {home_team} vs {away_team}", file=sys.stderr)
        print(f"🔍 MATCH TROVATO: {match_data.get('home', 'N/A')} vs {match_data.get('away', 'N/A')}", file=sys.stderr)
        print(f"🔍 FORMAZIONI PRESENTI: {'SI' if h2h_data.get('formazioni') else 'NO'}", file=sys.stderr)

        # 1. ESECUZIONE ALGORITMO E CREAZIONE sim_list
        sim_list = [] 
        t1 = time.time()
        preloaded_data = preload_match_data(home_team, away_team)
        print(f"⏱️ PRELOAD DATI: {time.time() - t1:.2f}s", file=sys.stderr)
        
        # ✅ LOG INIZIALE
        print(f"🎯 SIMULAZIONE RICHIESTA: Algo {algo_id}, Cicli {cycles}", file=sys.stderr)
        
        if algo_id == 6:
            # MONTE CARLO
            print(f"🔵 MODALITÀ MONTE CARLO ATTIVATA", file=sys.stderr)
            
            res = run_monte_carlo_verdict_detailed(
                preloaded_data, 
                home_team, 
                away_team,
                analyzer=analyzer,
                cycles=cycles,
                algo_id=algo_id
            )
            gh, ga = res[0]
            
            actual_cycles_executed = res[5]
            
            # Tracking cicli Monte Carlo
            if len(res) > 4 and isinstance(res[4], dict):
                for algo_results in res[4].values():
                    if isinstance(algo_results, list):
                        actual_cycles_executed += len(algo_results)
            else:
                actual_cycles_executed = cycles
            
            # Creazione sim_list dai risultati grezzi
            if len(res) > 4 and isinstance(res[4], dict):
                for algo_res_list in res[4].values():
                    if isinstance(algo_res_list, list):
                        sim_list.extend(algo_res_list)
            elif len(res) > 4 and isinstance(res[4], list):
                sim_list = [f"{r[0]}-{r[1]}" for r in res[4]]
            else:
                sim_list = [f"{gh}-{ga}"] * cycles
            
            top3 = [x[0] for x in res[2]]
            cronaca = res[1] if len(res) > 1 else []
            
            print(f"✅ MONTE CARLO COMPLETATO: {actual_cycles_executed} cicli eseguiti", file=sys.stderr)
            print(f"✅ RISULTATO FINALE: {gh}-{ga}", file=sys.stderr)
        
        else:
            # ✅ ALGORITMI SINGOLI (1-5)
            print(f"🟢 MODALITÀ SINGOLO ALGORITMO {algo_id} ATTIVATA", file=sys.stderr)
            
            # 1. CARICAMENTO TUNING UNA VOLTA SOLA
            settings_in_ram = load_tuning(algo_id)
            
            # 2. RISOLUZIONE NOMI FUORI DAL CICLO (Fondamentale per la velocità)
            # Prendiamo i nomi già puliti che il sistema ha trovato durante il preload
            real_home = preloaded_data.get('home_team', home_team)
            real_away = preloaded_data.get('away_team', away_team)
            
            t2 = time.time()
            sim_list = []
            
            print(f"🚀 Avvio simulazione veloce per: {real_home} vs {real_away}", file=sys.stderr)

            for i in range(cycles):
                # Usiamo real_home e real_away: il motore non deve più cercarli nel DB o negli Alias ad ogni giro
                gh_temp, ga_temp = run_single_algo(
                    algo_id, 
                    preloaded_data, 
                    real_home, 
                    real_away, 
                    settings_cache=settings_in_ram, 
                    debug_mode=False
                )
                
                sim_list.append(f"{gh_temp}-{ga_temp}")
                analyzer.add_result(algo_id, gh_temp, ga_temp)
                
                # Log progresso ogni 10% (mantenuto come richiesto)
                if cycles >= 10 and (i + 1) % max(1, cycles // 10) == 0:
                    pct = int((i + 1) / cycles * 100)
                    print(f"  📊 Progresso: {pct}% ({i + 1}/{cycles})", file=sys.stderr)
            
            # 3. CALCOLO RISULTATO FINALE
            from collections import Counter
            most_common = Counter(sim_list).most_common(1)[0][0]
            gh, ga = map(int, most_common.split("-"))
            
            print(f"⏱️ CALCOLO COMPLETATO IN: {time.time() - t2:.2f}s", file=sys.stderr)
            
            # Calcola risultato più frequente
            from collections import Counter
            most_common = Counter(sim_list).most_common(1)[0][0]
            gh, ga = map(int, most_common.split("-"))
            top3 = [x[0] for x in Counter(sim_list).most_common(3)]
            cronaca = []
            actual_cycles_executed = cycles
            print(f"⏱️ CICLI SIMULAZIONE: {time.time() - t2:.2f}s", file=sys.stderr)
            print(f"✅ ALGORITMO {algo_id} COMPLETATO: {cycles} cicli eseguiti", file=sys.stderr)
            print(f"✅ RISULTATO FINALE: {gh}-{ga}", file=sys.stderr)
        
        # ✅ CHIUDI ANALYZER
        analyzer.end_match()

        # OTTIENI DEEP STATS (le stats sono dentro matches dopo end_match)
        if analyzer.matches and len(analyzer.matches) > 0:
            last_match = analyzer.matches[-1]
            if 'algorithms' in last_match and algo_id in last_match['algorithms']:
                deep_stats = last_match['algorithms'][algo_id]['stats']
            else:
                # Fallback se non ci sono stats
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
            # Fallback completo
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

        # 3. GENERAZIONE REPORT
        anatomy = genera_match_report_completo(gh, ga, h2h_data, team_h_doc, team_a_doc, sim_list, deep_stats)

        # QUOTE MATCH
        quote_match = {
            "1": team_h_doc.get('odds', {}).get('1'),
            "X": team_h_doc.get('odds', {}).get('X'),
            "2": team_h_doc.get('odds', {}).get('2')
        }

        # BETTING LOGIC
        report_pro = analyze_betting_data(sim_list, quote_match)

        # ✅ DEBUG INFO COMPLETO
        debug_info = {
            "1_league_ricevuta": league,
            "2_league_pulita": league_clean,
            "3_h2h_doc_trovato": bool(h2h_doc),
            "4_num_partite": len(h2h_doc.get('matches', [])) if h2h_doc else 0,
            "5_prime_partite": [(m.get('home'), m.get('away')) for m in (h2h_doc.get('matches', []) if h2h_doc else [])[:3]],
            "6_match_cercato": f"{home_team} vs {away_team}",
            "7_match_trovato": f"{match_data.get('home', 'N/A')} vs {match_data.get('away', 'N/A')}",
            "8_h2h_data_keys": list(h2h_data.keys()) if h2h_data else [],
            "9_formazioni_presenti": bool(h2h_data.get('formazioni')),
            "10_marcatori_casa": ottieni_nomi_giocatori(h2h_data)[0] if h2h_data.get('formazioni') else [],
            "11_marcatori_ospite": ottieni_nomi_giocatori(h2h_data)[1] if h2h_data.get('formazioni') else []
        }

        # RISULTATO FINALE
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
            "execution_time": (datetime.now() - start_time).total_seconds(),
            "statistiche": anatomy["statistiche"],
            "cronaca": anatomy["cronaca"],
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