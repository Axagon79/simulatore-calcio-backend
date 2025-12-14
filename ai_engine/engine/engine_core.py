import os
import sys
import json
import random
import numpy as np

# (** MOTORE MATEMATICO CENTRALE V2.0: SUPPORTO GRANULARE MULTI-ALGORITMO **)
# ( Legge il JSON a scompartimenti, crea 5 profili di pesi in memoria e li usa dinamicamente )

# --- 1. CONFIGURAZIONE PATH E IMPORT DB ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR)) 
sys.path.append(PROJECT_ROOT)

# Aggiungo path per i calcolatori
CALCULATORS_DIR = os.path.join(os.path.dirname(CURRENT_DIR), 'calculators')
sys.path.append(CALCULATORS_DIR)

try:
    from config import db
    print("✅ [ENGINE] Connessione DB importata da config.")
except ImportError:
    try:
        sys.path.append(os.path.dirname(CURRENT_DIR)) 
        from config import db
        print("✅ [ENGINE] Connessione DB importata (fallback).")
    except ImportError:
        print("❌ [ENGINE] Errore: config.py non trovato! Verifica i path.")
        db = None

# --- IMPORT LIBRERIE CALCOLO ---
try: import calculate_team_rating as rating_lib
except: rating_lib = None
try: import calculator_affidabilità as reliability_lib
except: reliability_lib = None
try: import calculator_bvs as bvs_lib
except: bvs_lib = None
try: import calculator_fattore_campo as field_lib
except: field_lib = None
try: import calculator_lucifero as lucifero_lib
except: lucifero_lib = None

# --- 2. CONFIGURAZIONE LEGHE ---
AI_ENGINE_DIR = os.path.dirname(CURRENT_DIR) 
STATS_FILE = os.path.join(AI_ENGINE_DIR, "league_stats.json")
LEAGUE_STATS = {}
CACHE_FILE = os.path.join(CURRENT_DIR, "last_match_data.json")

# --- 3. CARICAMENTO TUNING (SISTEMA GRANULARE) ---
TUNING_FILE = os.path.join(CURRENT_DIR, "tuning_settings.json")

def load_tuning_db():
    try:
        if os.path.exists(TUNING_FILE):
            with open(TUNING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Errore lettura tuning: {e}")
    return {}

# 1. Carichiamo tutto il DB grezzo (Global + Algos)
RAW_DB = load_tuning_db()

# 2. Mappa nomi chiavi
JSON_KEYS_MAP = {
    1: "ALGO_1",   # Statistica
    2: "ALGO_2",   # Dinamico
    3: "ALGO_3",   # Complesso
    4: "ALGO_4",   # Caos
    5: "GLOBAL"    # Master
}

# 3. Funzione costruttrice del compartimento pesi
def build_weights_compartment(algo_id):
    # A. Carichiamo GLOBAL (Base)
    global_data = RAW_DB.get("GLOBAL", {})
    
    # B. Carichiamo SPECIFICI (Override)
    key_name = JSON_KEYS_MAP.get(algo_id, "GLOBAL")
    specific_data = RAW_DB.get(key_name, {})
    
    # C. Funzione interna per estrarre valore (Specifico > Globale > Default)
    def get_w(key, default=1.0):
        # 1. Cerco nello specifico (Override) - SOLO SE non c'è lucchetto bloccante (se implementato in futuro)
        if key in specific_data and "valore" in specific_data[key]:
            return specific_data[key]["valore"]
        # 2. Cerco nel globale (Fallback)
        if key in global_data and "valore" in global_data[key]:
            return global_data[key]["valore"]
        return default

    return {
        "H2H":        get_w("PESO_STORIA_H2H", 1.0),
        "MOTIVATION": get_w("PESO_MOTIVAZIONE", 1.0),
        "RATING":     get_w("PESO_RATING_ROSA", 1.0),
        "ROSA_VAL":   get_w("PESO_VALORE_ROSA", 1.0),
        "RELIABILITY":get_w("PESO_AFFIDABILITA", 1.0),
        "BVS":        get_w("PESO_BVS_QUOTE", 1.0),
        "FIELD":      get_w("PESO_FATTORE_CAMPO", 1.0),
        "LUCIFERO":   get_w("PESO_FORMA_RECENTE", 1.0),
        
        "DIVISORE_GOL": get_w("DIVISORE_MEDIA_GOL", 2.0),
        "WINSHIFT":     get_w("POTENZA_FAVORITA_WINSHIFT", 0.40),
        "IMPATTO_DIF":  get_w("IMPATTO_DIFESA_TATTICA", 15.0),
        "MAX_GOL":      get_w("TETTO_MAX_GOL_ATTESI", 4.5)
    }

# 4. CREAZIONE DEGLI SCOMPARTIMENTI (CACHE)
WEIGHTS_CACHE = {
    algo_id: build_weights_compartment(algo_id) 
    for algo_id in [1, 2, 3, 4, 5]
}

print(f"🎛️ [ENGINE] Tuning Granulare Caricato: {len(WEIGHTS_CACHE)} profili attivi.")

ALGO_MODE = 5
ALGO_NAMES = {
    1: "STATISTICA PURA",
    2: "DINAMICO (Base)",
    3: "COMPLESSO (Tattico)",
    4: "CAOS (Estremo)",
    5: "MASTER (Ensemble)"
}


try:
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            LEAGUE_STATS = json.load(f)
        print(f"✅ [ENGINE] Medie caricate.")
    else:
        if os.path.exists(os.path.join(CURRENT_DIR, "league_stats.json")):
             with open(os.path.join(CURRENT_DIR, "league_stats.json"), "r", encoding="utf-8") as f:
                LEAGUE_STATS = json.load(f)
             print(f"✅ [ENGINE] Medie caricate (path locale).")
        else:
             print(f"⚠️ [ENGINE] File league_stats.json mancante.")
except Exception as e:
    print(f"❌ [ENGINE] Errore JSON: {e}")

DEFAULT_LEAGUE_AVG = 2.50


def calculate_base_goals(league_name):
    league_data = LEAGUE_STATS.get(league_name, {})
    if isinstance(league_data, dict):
        avg_total = league_data.get("avg_goals", DEFAULT_LEAGUE_AVG)
    else:
        avg_total = league_data if league_data else DEFAULT_LEAGUE_AVG
    avg_team = avg_total / 2
    base_value = ((avg_team / 10) * 2) + (avg_team / 10)
    return round(base_value, 4), avg_total

def get_identity_card(db_conn, input_name):
    """
    Risolve l'identità della squadra cercando nel DB Teams.
    Restituisce un dizionario 'Passaporto' con:
    - official_name: Nome nel DB Teams (es. 'AC Milan')
    - aliases: Lista alias (es. ['Milan', 'Milan AC'])
    - input_name: Il nome usato dall'utente
    """
    if db_conn is None: return {"official_name": input_name, "aliases": [], "input_name": input_name}
    
    # 1. Cerca per nome esatto (Case insensitive) o Alias
    try:
        query = {
            "$or": [
                {"name": {"$regex":f"^{input_name}$", "$options": "i"}},
                {"aliases": {"$regex":f"^{input_name}$", "$options": "i"}}
            ]
        }
        doc = db_conn.teams.find_one(query)
        
        if doc:
            return {
                "official_name": doc.get("name"),
                "aliases": doc.get("aliases", []),
                "input_name": input_name
            }
    except Exception as e:
        print(f"⚠️ Errore ricerca identità {input_name}: {e}")
    
    # Fallback: Nessuna corrispondenza trovata
    return {"official_name": input_name, "aliases": [], "input_name": input_name}


def get_team_data(db_conn, team_identity):
    """
    Recupera i dati tecnici (stats, scores) usando l'identità risolta.
    team_identity può essere una stringa (vecchio modo) o un dict (nuovo ID Card).
    """
    if db_conn is None: return {}
    
    # Retro-compatibilità: se passiamo solo il nome stringa
    target_name = team_identity
    if isinstance(team_identity, dict):
        target_name = team_identity.get("official_name")
        
    team = db_conn.teams.find_one({"name": target_name})
    
    if not team: return {}
    
    data = team.get("scores", {})
    stats = team.get("stats", {})
    
    data['motivation'] = stats.get("motivation", 10.0)
    data['strength_score'] = stats.get("strengthScore09", 5.0)
    
    # Recuperiamo anche Rating se salvato
    data['rating_stored'] = team.get('rating_5_25', None) 
    
    return data


def get_h2h_data_from_db(db_conn, home_team, away_team):
    if db_conn is None: return 0, 0, "Nessun Dato", {}
    doc = db_conn.h2h_by_round.find_one(
        {"matches": {"$elemMatch": {"home": home_team, "away": away_team}}},
        {"matches.$": 1}
    )
    if doc and "matches" in doc and len(doc["matches"]) > 0:
        h2h = doc["matches"][0].get("h2h_data", {})
        if h2h.get("status") == "No Data": return 0, 0, "Dati Insufficienti", {}
        
        extra = {
            "avg_goals_home": h2h.get("avg_goals_home", 1.2), 
            "avg_goals_away": h2h.get("avg_goals_away", 1.0)
        }
        return h2h.get("home_score", 0), h2h.get("away_score", 0), h2h.get("history_summary", ""), extra
        
    return 0, 0, "Match non trovato in H2H DB", {}

def get_dynamic_rating(team_name):
    if rating_lib is None: return 12.5, {}  # ← Default 12.5 (centro scala 5-25)
    try:
        result = rating_lib.calculate_team_rating(team_name)
        if result:
            return result.get('rating_5_25', 12.5), result  # ← USA rating_5_25!
        return 12.5, {}  # ← Default 12.5
    except Exception as e:
        print(f"⚠️ Errore calcolo rating {team_name}: {e}")
        return 12.5, {}  # ← Default 12.5


def apply_randomness(value):
    if value == 0: return 0, 0
    fluctuation = random.uniform(-0.15, 0.15)
    adjusted = value * (1 + fluctuation)
    return round(adjusted, 4), fluctuation

# --- CORE CALCOLO SINGOLO (CON PESI DINAMICI) ---

def calculate_match_score(home_raw, away_raw, h2h_scores, base_val, algo_mode):
    
    # A. SELEZIONE PROFILO PESI
    # Se l'algo_mode è valido (1-5), usa quel profilo. Altrimenti usa GLOBAL (5).
    safe_mode = algo_mode if algo_mode in WEIGHTS_CACHE else 5
    W = WEIGHTS_CACHE[safe_mode]

    # Dati BASE
    h_power = home_raw['power']
    a_power = away_raw['power']
    h_att, h_def = home_raw['attack'], home_raw['defense']
    a_att, a_def = away_raw['attack'], away_raw['defense']
    
    # Dati Extra
    h_h2h_val, a_h2h_val = h2h_scores
    h_motiv = home_raw.get('motivation', 10.0)
    a_motiv = away_raw.get('motivation', 10.0)
    h_rating = home_raw.get('rating', 5.0)
    a_rating = away_raw.get('rating', 5.0)
    h_rosa = home_raw.get('strength_score', 5.0)
    a_rosa = away_raw.get('strength_score', 5.0)
    h_rel = home_raw.get('reliability', 5.0)
    a_rel = away_raw.get('reliability', 5.0)
    h_bvs = home_raw.get('bvs', 0.0)
    a_bvs = away_raw.get('bvs', 0.0)
    h_field = home_raw.get('field_factor', 3.5)
    a_field = away_raw.get('field_factor', 3.5)
    h_luc = home_raw.get('lucifero', 0.0)
    a_luc = away_raw.get('lucifero', 0.0)

    # ALGO 4: Random Totale (Caos) - Fluttua gli input PRIMA del calcolo
    if algo_mode == 4:
        h_power, _ = apply_randomness(h_power)
        a_power, _ = apply_randomness(a_power)
        h_motiv, _ = apply_randomness(h_motiv)
        a_motiv, _ = apply_randomness(a_motiv)
        h_rating, _ = apply_randomness(h_rating)
        a_rating, _ = apply_randomness(a_rating)
        # ... (Applicato a tutti per brevità del caos) ...

    # --- CALCOLO POWER LORDO (USANDO I PESI W) ---
    bonus_h = (
        (h_h2h_val * W["H2H"]) +
        (h_motiv * W["MOTIVATION"]) +
        (h_rating * W["RATING"]) +
        (h_rosa * W["ROSA_VAL"]) +
        (h_rel * W["RELIABILITY"]) +
        (h_bvs * W["BVS"]) +
        (h_field * W["FIELD"]) +
        (h_luc * W["LUCIFERO"])
    )
    
    bonus_a = (
        (a_h2h_val * W["H2H"]) +
        (a_motiv * W["MOTIVATION"]) +
        (a_rating * W["RATING"]) +
        (a_rosa * W["ROSA_VAL"]) +
        (a_rel * W["RELIABILITY"]) +
        (a_bvs * W["BVS"]) +
        (a_field * W["FIELD"]) +
        (a_luc * W["LUCIFERO"])
    )
    
    h_power_total = h_power + bonus_h
    a_power_total = a_power + bonus_a

    # --- SCENARI ---
    # Scenario BASE
    freno_base_home = a_def 
    freno_base_away = h_def
    
    gross_base_home = base_val + h_power_total
    gross_base_away = base_val + a_power_total
    
    net_base_home = max(0, gross_base_home - freno_base_home)
    net_base_away = max(0, gross_base_away - freno_base_away)

    # Scenario DINAMICO
    h_tactical_diff = h_def - h_att
    a_tactical_diff = a_def - a_att
    
    # Uso IMPATTO_DIFESA specifico dell'algoritmo
    # (Per ora manteniamo la logica originale per non rompere i calcoli base)
    
    freno_dyn_home = a_def + a_tactical_diff 
    freno_dyn_away = h_def + h_tactical_diff 
    
    gross_dyn_home = base_val + h_power_total 
    gross_dyn_away = base_val + a_power_total
    
    net_dyn_home = max(0, gross_dyn_home - freno_dyn_home)
    net_dyn_away = max(0, gross_dyn_away - freno_dyn_away)

    # --- SELEZIONE (MEDIA TRE STRATI) ---
    final_home = (h_power_total + net_base_home + net_dyn_home) / 3
    final_away = (a_power_total + net_base_away + net_dyn_away) / 3

    # --- RANDOM FINALE (Solo per Algo 2 e 3) ---
    if algo_mode in [2, 3]:
        final_home, _ = apply_randomness(final_home)
        final_away, _ = apply_randomness(final_away)

    return final_home, final_away



# --- MOTORE PRINCIPALE (MODIFICATO PER PRELOAD) ---

def predict_match(home_team, away_team, mode=ALGO_MODE, preloaded_data=None):
    """
    NUOVO PARAMETRO: preloaded_data
    Se passato, SALTA il caricamento DB e usa i dati pronti.
    """
    # --- 1. RISOLUZIONE IDENTITÀ (FIX NOMI) ---
    # Creiamo subito i 'passaporti' corretti per le squadre
    h_id = get_identity_card(db, home_team)
    a_id = get_identity_card(db, away_team)

    if not preloaded_data:
        print(f"\n🤖 [ENGINE] Analisi: {home_team} vs {away_team}")
        print(f"⚙️ Algoritmo: {ALGO_NAMES.get(mode, mode)}")
        # Avviso se abbiamo corretto il nome
        if h_id['official_name'] != home_team: 
            print(f"   🔍 Identità Risolta: '{home_team}' -> '{h_id['official_name']}'")
        if a_id['official_name'] != away_team: 
            print(f"   🔍 Identità Risolta: '{away_team}' -> '{a_id['official_name']}'")

    if preloaded_data:
        # FAST TRACK ⚡ (Usiamo i dati passati da fuori)
        home_raw = preloaded_data['home_raw']
        away_raw = preloaded_data['away_raw']
        h2h_h = preloaded_data['h2h_h']
        h2h_a = preloaded_data['h2h_a']
        base_val = preloaded_data['base_val']
        # Per compatibilità, definiamo H_OFF anche qui (anche se non usati in fast track)
        H_OFF, A_OFF = h_id['official_name'], a_id['official_name']
    else:
        # SLOW TRACK 🐢 (Caricamento classico dal DB)
        if db is None:
            print("❌ DB non connesso.")
            return

        # Definiamo i NOMI UFFICIALI da usare per le ricerche
        H_OFF = h_id['official_name']
        A_OFF = a_id['official_name']

        # Cerchiamo il match usando i nomi ufficiali
        match = db.matches.find_one({"home_team": H_OFF, "away_team": A_OFF})
        # Tentativo di fallback col nome originale se fallisce
        if not match: match = db.matches.find_one({"home_team": home_team, "away_team": away_team})
        
        competition = match.get("competition", "Sconosciuto") if match else "Sconosciuto"
        base_val, _ = calculate_base_goals(competition)

        # Recupero Dati Interni (Passiamo il passaporto intero)
        h_data = get_team_data(db, h_id)
        a_data = get_team_data(db, a_id)

        # Rating Live (Usa NOME UFFICIALE)
        h_rating_val, h_rating_full = get_dynamic_rating(H_OFF)
        a_rating_val, a_rating_full = get_dynamic_rating(A_OFF)
        
    if not preloaded_data:


        # Salvataggio Flash Cache (Solo in slow track)
        def clean_roster(team_data_full):
            if not team_data_full or "starters" not in team_data_full: return "N/A"
            return {
                "Squadra": team_data_full.get("team"),
                "Modulo": team_data_full.get("formation"),
                "Rating": f"{team_data_full.get('rating_5_25', 'N/A')}/25",  # ← Mostra scala /25
                "1_TITOLARI": [f"{p['role']} - {p['player']} ({p.get('rating',0):.1f})" for p in team_data_full["starters"]],
                "2_PANCHINA": [f"{p['role']} - {p['player']} ({p.get('rating',0):.1f})" for p in team_data_full.get("bench", [])]
            }

        flash_data = {
            "MATCH": f"{home_team} vs {away_team}",
            "CASA": clean_roster(h_rating_full),
            "OSPITE": clean_roster(a_rating_full)
        }
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(flash_data, f, indent=4)
            print(f"💾 Dati Flash (Clean) salvati in: {CACHE_FILE}")
        except Exception as e:
            print(f"⚠️ Errore salvataggio Flash: {e}")

                # Calcoli Extra Librerie (Usa NOMI UFFICIALI H_OFF/A_OFF)
        if reliability_lib:
            h_rel = reliability_lib.calculate_reliability(H_OFF)
            a_rel = reliability_lib.calculate_reliability(A_OFF)
        else: h_rel, a_rel = 5.0, 5.0

        if bvs_lib:
            h_bvs, a_bvs = bvs_lib.get_bvs_score(H_OFF, A_OFF)
        else: h_bvs, a_bvs = 0.0, 0.0

        if field_lib:
            h_field, a_field = field_lib.calculate_field_factor(H_OFF, A_OFF, competition)
        else: h_field, a_field = 3.5, 3.5

        if lucifero_lib:
            h_luc = lucifero_lib.get_lucifero_score(H_OFF)
            a_luc = lucifero_lib.get_lucifero_score(A_OFF)
        else: h_luc, a_luc = 0.0, 0.0


        # Creazione Strutture RAW
        home_raw = {
            'power': h_data.get("home_power", 0), 
            'attack': h_data.get("attack_home", 0), 
            'defense': h_data.get("defense_home", 0),
            'motivation': h_data.get("motivation", 5.0),
            'strength_score': h_data.get("strength_score", 5.0),
            'rating': h_rating_val,
            'reliability': h_rel,
            'bvs': h_bvs,
            'field_factor': h_field,
            'lucifero': h_luc
        }
        away_raw = {
            'power': a_data.get("away_power", 0), 
            'attack': a_data.get("attack_away", 0), 
            'defense': a_data.get("defense_away", 0),
            'motivation': a_data.get("motivation", 5.0),
            'strength_score': a_data.get("strength_score", 5.0),
            'rating': a_rating_val,
            'reliability': a_rel,
            'bvs': a_bvs,
            'field_factor': a_field,
            'lucifero': a_luc
        }
        
        # Stampe info (Solo in slow track)
        print(f"📊 Motivazioni: {home_team}={home_raw['motivation']} | {away_team}={away_raw['motivation']}")
        print(f"⭐ Rating Rosa: {home_team}={h_rating_val:.2f}/25 | {away_team}={a_rating_val:.2f}/25")
        print(f"⚔️  Attacco/Difesa: {home_team}={home_raw['attack']:.1f}/{home_raw['defense']:.1f} | {away_team}={away_raw['attack']:.1f}/{away_raw['defense']:.1f}")
        print(f"💎 Valore Rosa: {home_team}={home_raw['strength_score']} | {away_team}={away_raw['strength_score']}")
        print(f"🍀 Affidabilità: {home_team}={h_rel} | {away_team}={a_rel}")
        print(f"🏟️  Fattore Campo:{home_team}={h_field} | {away_team}={a_field}")
        print(f"🔥 Lucifero:     {home_team}={h_luc:.2f} | {away_team}={a_luc:.2f}")
        print(f"🔮 BVS Bonus:    {home_team}={h_bvs:+} | {away_team}={a_bvs:+}")

        h2h_h, h2h_a, h2h_msg, h2h_extra = get_h2h_data_from_db(db, H_OFF, A_OFF)

        print(f"📜 H2H Info: {h2h_msg} [Bonus: {h2h_h:.2f} - {h2h_a:.2f}]")
        
        home_raw['h2h_avg_goals'] = h2h_extra.get('avg_goals_home', 1.2)
        away_raw['h2h_avg_goals'] = h2h_extra.get('avg_goals_away', 1.0)


    # --- 2. CALCOLO DELLO SCORE (Applicazione Algoritmi + Random) ---
    
    if mode == 5:
        if not preloaded_data: print("✨ Esecuzione ENSEMBLE (1-4 + GLOBAL)...")
        results_h = []
        results_a = []
        
        # A. Esegui Algo 1, 2, 3, 4
        for i in range(1, 5):
            nh, na = calculate_match_score(home_raw, away_raw, (h2h_h, h2h_a), base_val, i)
            results_h.append(nh)
            results_a.append(na)
            
        # B. Esegui Algo GLOBAL (Mode 5) - IL VOTO DEL PRESIDENTE
        nh_global, na_global = calculate_match_score(home_raw, away_raw, (h2h_h, h2h_a), base_val, 5)
        results_h.append(nh_global)
        results_a.append(na_global)
        
        # C. Media Totale (diviso 5 voti)
        avg_h = sum(results_h) / 5
        avg_a = sum(results_a) / 5
        
        final_h, r_h = apply_randomness(avg_h)
        final_a, r_a = apply_randomness(avg_a)
        net_home, net_away = final_h, final_a
    else:
        # Modalità Singola (1, 2, 3 o 4)
        net_home, net_away = calculate_match_score(home_raw, away_raw, (h2h_h, h2h_a), base_val, mode)

    # Stampe risultato (Solo se non stiamo simulando massivamente)
    if not preloaded_data:
        # TOTALE MASSIMO TEORICO = (Rating 5-25 invece di 0-10: +15 punti)
        MAX_THEORETICAL_SCORE = 131.00
        perc_h = (net_home / MAX_THEORETICAL_SCORE) * 100
        perc_a = (net_away / MAX_THEORETICAL_SCORE) * 100

        print("-" * 55)
        print(f"🏁 RISULTATO FINALE ({ALGO_NAMES.get(mode)}):")
        print(f"   🏠 {home_team:<15}: {net_home:6.2f} / 131.00 ({perc_h:.1f}%)")
        print(f"   ✈️ {away_team:<15}: {net_away:6.2f} / 131.00 ({perc_a:.1f}%)")
        print("-" * 55)
    
    return net_home, net_away, home_raw, away_raw



# Funzione Helper per caricare i dati 1 volta sola (per Monte Carlo)
def preload_match_data(home_team, away_team):
    """
    Esegue una 'finta' simulazione in modalità 1 (Statistica) 
    solo per estrarre i dati RAW e restituirli puliti.
    """
    _, _, home_raw, away_raw = predict_match(home_team, away_team, mode=1)
    
    # Recuperiamo anche h2h e base_val (che sono nascosti dentro)
    # Per farlo pulito, li ricalcoliamo velocemente qui perché predict_match li ha già usati
    # ma non restituiti esplicitamente. 
    # Trucco: Usiamo predict_match che ci ha dato home_raw/away_raw completi.
    
    # Ma ci mancano h2h_h e h2h_a puri per passarli al calcolatore.
    # Quindi li ripeschiamo velocemente dal DB (è l'unico modo pulito senza rompere tutto)
    
    match = db.matches.find_one({"home_team": home_team, "away_team": away_team})
    competition = match.get("competition", "Sconosciuto") if match else "Sconosciuto"
    base_val, _ = calculate_base_goals(competition)
    h2h_h, h2h_a, _, _ = get_h2h_data_from_db(db, home_team, away_team)

    return {
        'home_raw': home_raw,
        'away_raw': away_raw,
        'h2h_h': h2h_h,
        'h2h_a': h2h_a,
        'base_val': base_val
    }

# --- AREA TEST ESECUZIONE DIRETTA ---
if __name__ == "__main__":
    print("\n--- ⚽ ENGINE CORE V9 - TEST MODE ---")
    print("1-5: Algoritmi Singoli")
    print("6:  SIMULAZIONE MONTE CARLO (500 match RAPIDO)")
    
    try:
        raw_input = input("Scegli Opzione (1-6): ").strip()
        mode = int(raw_input)
    except ValueError:
        mode = 5

    home = "Milan"
    away = "Inter"

    if mode == 6:
        print(f"\n🎲 AVVIO MONTE CARLO: {home} vs {away}")
        print("⏳ Pre-caricamento dati...")
        
        try:
            static_data = preload_match_data(home, away)
        except Exception as e:
            print(f"❌ Errore preload: {e}")
            exit()
        
        simulations = 500  # ← RIDOTTO per test veloce
        
        results_h = []
        results_a = []
        wins_h = wins_a = draws = 0
        
        # ✅ BARRA + TRY/EXCEPT + NO DEBUG SPAM
        print(f"🚀 {simulations} simulazioni...")
        for i in range(simulations):
            try:
                s_h, s_a, _, _ = predict_match(home, away, mode=5, preloaded_data=static_data)
                if s_h is None: continue
                
                results_h.append(s_h)
                results_a.append(s_a)
                
                if s_h > s_a + 0.5: wins_h += 1
                elif s_a > s_h + 0.5: wins_a += 1
                else: draws += 1
                
                # ✅ BARRA SEMPLICE (ogni 50 cicli)
                if i % 50 == 0 or i == simulations-1:
                    pct = (i+1)/simulations*100
                    print(f"\r🎲 {pct:.0f}% ({i+1}/{simulations}) | {s_h:.1f}-{s_a:.1f}", end="")
                    
            except:
                continue  # Skip errori DB
        
        print()  # Nuova riga
        
        # Report
        if results_h:
            avg_h = sum(results_h) / len(results_h)
            avg_a = sum(results_a) / len(results_a)
            
            print("\n" + "="*50)
            print(f"📊 MONTE CARLO FINITO ({len(results_h)} iterazioni valide)")
            print("="*50)
            print(f"Media Gol Casa:   {avg_h:.2f}")
            print(f"Media Gol Ospite: {avg_a:.2f}")
            print("-"*25)
            print(f"1: {wins_h} ({wins_h/simulations*100:.1f}%)")
            print(f"X: {draws} ({draws/simulations*100:.1f}%)")
            print(f"2: {wins_a} ({wins_a/simulations*100:.1f}%)")
            print("="*50)
        else:
            print("❌ Nessun risultato valido!")
    
    else:
        predict_match(home, away, mode=mode)


