import os
import sys
import json
import random

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

# 1. Rating (Titolari)
try:
    import calculate_team_rating as rating_lib
    print("✅ [ENGINE] Libreria Rating caricata.")
except ImportError as e:
    print(f"❌ [ENGINE] Errore import rating lib: {e}")
    rating_lib = None

# 2. Affidabilità (Quote Storiche)
try:
    import calculator_affidabilità as reliability_lib
    print("✅ [ENGINE] Libreria Affidabilità caricata.")
except ImportError as e:
    print(f"❌ [ENGINE] Errore import affidabilità lib: {e}")
    reliability_lib = None

# 3. BVS (Picchetto vs Bookmaker)
try:
    import calculator_bvs as bvs_lib
    print("✅ [ENGINE] Libreria BVS caricata.")
except ImportError as e:
    print(f"❌ [ENGINE] Errore import BVS lib: {e}")
    bvs_lib = None

# 4. Fattore Campo (Punti Casa/Fuori)
try:
    import calculator_fattore_campo as field_lib
    print("✅ [ENGINE] Libreria Fattore Campo caricata.")
except ImportError as e:
    print(f"❌ [ENGINE] Errore import Fattore Campo lib: {e}")
    field_lib = None

# 5. LUCIFERO (Forma Recente Ponderata)
try:
    import calculator_lucifero as lucifero_lib
    print("✅ [ENGINE] Libreria Lucifero caricata.")
except ImportError as e:
    print(f"❌ [ENGINE] Errore import Lucifero lib: {e}")
    lucifero_lib = None

# --- 2. CONFIGURAZIONE LEGHE ---
AI_ENGINE_DIR = os.path.dirname(CURRENT_DIR) 
STATS_FILE = os.path.join(AI_ENGINE_DIR, "league_stats.json")
LEAGUE_STATS = {}
CACHE_FILE = os.path.join(CURRENT_DIR, "last_match_data.json")

# --- PESI DEL SISTEMA (CALDERONE TOTALE) ---
H2H_WEIGHT = 1.0        
MOTIVATION_WEIGHT = 1.0 
RATING_WEIGHT = 1.0     
ROSA_VALUE_WEIGHT = 1.0 
RELIABILITY_WEIGHT = 1.0 
BVS_WEIGHT = 1.0        
FIELD_FACTOR_WEIGHT = 1.0 
LUCIFERO_WEIGHT = 1.0   # Nuovo Peso Forma

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

def get_team_data(db_conn, team_name):
    if db_conn is None: return {}
    team = db_conn.teams.find_one({"name": team_name})
    if not team: return {}
    
    data = team.get("scores", {})
    stats = team.get("stats", {})
    
    data['motivation'] = stats.get("motivation", 10.0)
    data['strength_score'] = stats.get("strengthScore09", 5.0)
    
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

# --- CORE CALCOLO SINGOLO ---

def calculate_match_score(home_raw, away_raw, h2h_scores, base_val, algo_mode):
    # Dati BASE
    h_power = home_raw['power']
    a_power = away_raw['power']
    
    h_att = home_raw['attack']
    h_def = home_raw['defense']
    a_att = away_raw['attack']
    a_def = away_raw['defense']
    
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

    # ALGO 4: Random Totale
    if algo_mode == 4:
        h_power, _ = apply_randomness(h_power)
        a_power, _ = apply_randomness(a_power)
        h_motiv, _ = apply_randomness(h_motiv)
        a_motiv, _ = apply_randomness(a_motiv)
        h_rating, _ = apply_randomness(h_rating)
        a_rating, _ = apply_randomness(a_rating)
        h_rosa, _ = apply_randomness(h_rosa)
        a_rosa, _ = apply_randomness(a_rosa)
        h_rel, _ = apply_randomness(h_rel)
        a_rel, _ = apply_randomness(a_rel)
        h_bvs, _ = apply_randomness(h_bvs)
        a_bvs, _ = apply_randomness(a_bvs)
        h_field, _ = apply_randomness(h_field)
        a_field, _ = apply_randomness(a_field)
        h_luc, _ = apply_randomness(h_luc)
        a_luc, _ = apply_randomness(a_luc)

    # --- 1. MOOD ---
    avg_att_match = (h_att + a_att) / 2
    avg_def_match = (h_def + a_def) / 2
    is_open_match = avg_att_match > avg_def_match

    # --- 2. CALCOLO POWER LORDO (IL CALDERONE) ---
    
    bonus_h = (
        (h_h2h_val * H2H_WEIGHT) +
        (h_motiv * MOTIVATION_WEIGHT) +
        (h_rating * RATING_WEIGHT) +
        (h_rosa * ROSA_VALUE_WEIGHT) +
        (h_rel * RELIABILITY_WEIGHT) +
        (h_bvs * BVS_WEIGHT) +
        (h_field * FIELD_FACTOR_WEIGHT) +
        (h_luc * LUCIFERO_WEIGHT)
    )
    
    bonus_a = (
        (a_h2h_val * H2H_WEIGHT) +
        (a_motiv * MOTIVATION_WEIGHT) +
        (a_rating * RATING_WEIGHT) +
        (a_rosa * ROSA_VALUE_WEIGHT) +
        (a_rel * RELIABILITY_WEIGHT) +
        (a_bvs * BVS_WEIGHT) +
        (a_field * FIELD_FACTOR_WEIGHT) +
        (a_luc * LUCIFERO_WEIGHT)
    )
    
    h_power_total = h_power + bonus_h
    a_power_total = a_power + bonus_a

    # --- 3. SCENARI ---
    
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
    
    freno_dyn_home = a_def + a_tactical_diff 
    freno_dyn_away = h_def + h_tactical_diff 
    
    gross_dyn_home = base_val + h_power_total 
    gross_dyn_away = base_val + a_power_total
    
    net_dyn_home = max(0, gross_dyn_home - freno_dyn_home)
    net_dyn_away = max(0, gross_dyn_away - freno_dyn_away)
    
    # --- 4. SELEZIONE ---
    if is_open_match:
        final_home = max(net_base_home, net_dyn_home)
        final_away = max(net_base_away, net_dyn_away)
    else:
        final_home = min(net_base_home, net_dyn_home)
        final_away = min(net_base_away, net_dyn_away)

    # --- 5. RANDOM FINALE ---
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
    
    # Se non siamo in modalità silenziosa, stampiamo info
    if not preloaded_data:
        print(f"\n🤖 [ENGINE] Analisi: {home_team} vs {away_team}")
        print(f"⚙️  Algoritmo: {ALGO_NAMES.get(mode, mode)}")

    # --- 1. CARICAMENTO DATI (O USO PRELOAD) ---
    if preloaded_data:
        # FAST TRACK ⚡ (Usiamo i dati passati da fuori)
        home_raw = preloaded_data['home_raw']
        away_raw = preloaded_data['away_raw']
        h2h_h = preloaded_data['h2h_h']
        h2h_a = preloaded_data['h2h_a']
        base_val = preloaded_data['base_val']
    else:
        # SLOW TRACK 🐢 (Caricamento classico dal DB)
        if db is None:
            print("❌ DB non connesso.")
            return

        match = db.matches.find_one({"home_team": home_team, "away_team": away_team})
        competition = match.get("competition", "Sconosciuto") if match else "Sconosciuto"
        base_val, _ = calculate_base_goals(competition)
        
        h_data = get_team_data(db, home_team)
        a_data = get_team_data(db, away_team)
        
        # Rating Live
        h_rating_val, h_rating_full = get_dynamic_rating(home_team)
        a_rating_val, a_rating_full = get_dynamic_rating(away_team)

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

        # Calcoli Extra Librerie
        if reliability_lib:
            h_rel = reliability_lib.calculate_reliability(home_team)
            a_rel = reliability_lib.calculate_reliability(away_team)
        else: h_rel, a_rel = 5.0, 5.0

        if bvs_lib:
            h_bvs, a_bvs = bvs_lib.get_bvs_score(home_team, away_team)
        else: h_bvs, a_bvs = 0.0, 0.0
            
        if field_lib:
            h_field, a_field = field_lib.calculate_field_factor(home_team, away_team, competition)
        else: h_field, a_field = 3.5, 3.5

        if lucifero_lib:
            h_luc = lucifero_lib.get_lucifero_score(home_team)
            a_luc = lucifero_lib.get_lucifero_score(away_team)
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
        print(f"🔥 Lucifero:    {home_team}={h_luc:.2f} | {away_team}={a_luc:.2f}")
        print(f"🔮 BVS Bonus:   {home_team}={h_bvs:+} | {away_team}={a_bvs:+}")

        h2h_h, h2h_a, h2h_msg, h2h_extra = get_h2h_data_from_db(db, home_team, away_team)
        print(f"📜 H2H Info: {h2h_msg} [Bonus: {h2h_h:.2f} - {h2h_a:.2f}]")
        
        home_raw['h2h_avg_goals'] = h2h_extra.get('avg_goals_home', 1.2)
        away_raw['h2h_avg_goals'] = h2h_extra.get('avg_goals_away', 1.0)

    # --- 2. CALCOLO DELLO SCORE (Applicazione Algoritmi + Random) ---
    
    if mode == 5:
        if not preloaded_data: print("✨ Esecuzione ENSEMBLE (Media Algo 1-4)...")
        results_h = []
        results_a = []
        for i in range(1, 5):
            nh, na = calculate_match_score(home_raw, away_raw, (h2h_h, h2h_a), base_val, i)
            results_h.append(nh)
            results_a.append(na)
        
        avg_h = sum(results_h) / 4
        avg_a = sum(results_a) / 4
        final_h, r_h = apply_randomness(avg_h)
        final_a, r_a = apply_randomness(avg_a)
        net_home, net_away = final_h, final_a
    else:
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

if __name__ == "__main__":
    print("\n--- TEST MOTORE V9 (FULL) ---")
    try:
        choice = input("Scegli Algoritmo (1-5): ").strip()
        mode = int(choice)
        if mode < 1 or mode > 5: mode = 5
    except ValueError:
        mode = 5

    predict_match("Torino", "Napoli", mode=mode)
