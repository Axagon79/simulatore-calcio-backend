import os
import sys
import json
import random
import numpy as np
import time

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
sys.path.append(PROJECT_ROOT)

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

try:
    import ai_engine.calculators.bulk_manager as bulk_manager
except ImportError:
    bulk_manager = None

try: import ai_engine.calculators.calculate_team_rating as rating_lib
except: rating_lib = None
try: import ai_engine.calculators.calculator_affidabilità as reliability_lib
except: reliability_lib = None
try: import ai_engine.calculators.calculator_bvs as bvs_lib
except: bvs_lib = None
try: import ai_engine.calculators.calculator_fattore_campo as field_lib
except: field_lib = None
try: import ai_engine.calculators.calculator_lucifero as lucifero_lib
except: lucifero_lib = None
try: import ai_engine.calculators.calculate_attacco_difesa as att_def_lib
except: att_def_lib = None
try: import ai_engine.calculators.calculate_motivazioni as motiv_lib
except: motiv_lib = None
try: import ai_engine.calculators.calculate_valore_rosa as value_rosa_lib
except: value_rosa_lib = None

AI_ENGINE_DIR = os.path.dirname(CURRENT_DIR)

STATS_FILE = os.path.join(AI_ENGINE_DIR, "league_stats.json")
LEAGUE_STATS = {}
CACHE_FILE = os.path.join(CURRENT_DIR, "last_match_data.json")

TUNING_FILE = os.path.join(CURRENT_DIR, "tuning_settings.json")

def load_tuning_db():
    """Carica tuning da MongoDB (con fallback su file locale)"""
    
    try:
        doc = db['tuning_settings'].find_one({"_id": "main_config"})
        if doc and "config" in doc:
            
            return doc["config"]
    except Exception as e:
        print(f"⚠️ [ENGINE] MongoDB tuning non disponibile: {e}")
    
    try:
        if os.path.exists(TUNING_FILE):
            with open(TUNING_FILE, "r", encoding="utf-8") as f:
                print("✅ [ENGINE] Tuning caricato da file locale (fallback)")
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Errore lettura tuning: {e}")
    
    return {}

RAW_DB = load_tuning_db()

JSON_KEYS_MAP = {
    1: "ALGO_1",
    2: "ALGO_2",
    3: "ALGO_3",
    4: "ALGO_4",
    5: "GLOBAL"
}

# 3. Funzione costruttrice del compartimento pesi
def build_weights_compartment(algo_id):
    global_data = RAW_DB.get("GLOBAL", {})
    
    key_name = JSON_KEYS_MAP.get(algo_id, "GLOBAL")
    specific_data = RAW_DB.get(key_name, {})
    
    def get_w(key, default=1.0):
        if key in specific_data and "valore" in specific_data[key]:
            return specific_data[key]["valore"]
        if key in global_data and "valore" in global_data[key]:
            return global_data[key]["valore"]
        return default

    return {
        "H2H": get_w("PESO_STORIA_H2H", 1.0),
        "MOTIVATION": get_w("PESO_MOTIVAZIONE", 1.0),
        "RATING": get_w("PESO_RATING_ROSA", 1.0),
        "ROSA_VAL": get_w("PESO_VALORE_ROSA", 1.0),
        "RELIABILITY": get_w("PESO_AFFIDABILITA", 1.0),
        "BVS": get_w("PESO_BVS_QUOTE", 1.0),
        "FIELD": get_w("PESO_FATTORE_CAMPO", 1.0),
        "LUCIFERO": get_w("PESO_FORMA_RECENTE", 1.0),
        "DIVISORE_GOL": get_w("DIVISORE_MEDIA_GOL", 2.0),
        "WINSHIFT": get_w("POTENZA_FAVORITA_WINSHIFT", 0.40),
        "IMPATTO_DIF": get_w("IMPATTO_DIFESA_TATTICA", 15.0),
        "MAX_GOL": get_w("TETTO_MAX_GOL_ATTESI", 4.5)
    }

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

# === SISTEMA IBRIDO: DB league_stats → JSON fallback ===
LEAGUE_STATS = {}
try:
    # db già importato all'inizio del file
    docs = list(db.league_stats.find())
    for doc in docs:
        league_name = doc['_id']
        avg_goals = doc.get('avg_goals', 2.50)
        LEAGUE_STATS[league_name] = {
            'avg_goals': avg_goals,
            'avg_home_league': avg_goals / 2,
            'avg_away_league': avg_goals / 2
        }
    print(f"✅ LEAGUE_STATS da DB league_stats: {len(LEAGUE_STATS)} campionati")
except Exception as e:
    print(f"⚠️ DB league_stats non disponibile: {e}")
    # === FALLBACK JSON (come prima) ===
    STATS_FILE = os.path.join(AI_ENGINE_DIR, "league_stats.json")
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                LEAGUE_STATS = json.load(f)
            print(f"✅ Fallback JSON league_stats.json: {len(LEAGUE_STATS)}")
        else:
            print(f"⚠️ File {STATS_FILE} non trovato")
    except Exception as e2:
        print(f"❌ Anche JSON fallito: {e2}")


DEFAULT_LEAGUE_AVG = 2.50

def calculate_base_goals(league_name, bulk_cache=None):
    if bulk_cache and "LEAGUE_STATS" in bulk_cache:
        stats = bulk_cache["LEAGUE_STATS"]
        avg_total = stats.get("avg_home_league", 1.60) + stats.get("avg_away_league", 1.10)
    else:
        league_data = LEAGUE_STATS.get(league_name, {})
        if isinstance(league_data, dict):
            avg_total = league_data.get("avg_goals", DEFAULT_LEAGUE_AVG)
        else:
            avg_total = league_data if league_data else DEFAULT_LEAGUE_AVG
            
    avg_team = avg_total / 2
    base_value = ((avg_team / 10) * 2) + (avg_team / 10)
    return round(base_value, 4), avg_total

def get_identity_card(db_conn, input_name, bulk_cache=None):
    """Risolve l'identità con priorità al Bulk Cache e supporto Alias Ibridi"""
    if bulk_cache and "TEAMS" in bulk_cache:
        for t in bulk_cache["TEAMS"]:
            if t.get("name", "").lower() == input_name.lower():
                return {"official_name": t.get("name"), "aliases": t.get("aliases", []), "input_name": input_name}
            
            aliases = t.get("aliases", [])
            found = False
            
            if isinstance(aliases, list):
                if input_name.lower() in [a.lower() for a in aliases if isinstance(a, str)]:
                    found = True
            elif isinstance(aliases, dict):
                for key, val in aliases.items():
                    if isinstance(val, str) and val.lower() == input_name.lower():
                        found = True
                        break
            
            if found:
                return {"official_name": t.get("name"), "aliases": aliases, "input_name": input_name}

    if db_conn is None:
        return {"official_name": input_name, "aliases": [], "input_name": input_name}
    
    try:
        query = {
            "$or": [
                {"name": {"$regex": f"^{input_name}$", "$options": "i"}},
                {"aliases": {"$regex": f"^{input_name}$", "$options": "i"}},
                {"aliases.soccerstats": {"$regex": f"^{input_name}$", "$options": "i"}}
            ]
        }
        doc = db_conn.teams.find_one(query)
        if doc:
            return {"official_name": doc.get("name"), "aliases": doc.get("aliases", []), "input_name": input_name}
    except Exception as e:
        print(f"⚠️ Errore ricerca identità {input_name}: {e}")
        
    return {"official_name": input_name, "aliases": [], "input_name": input_name}


def get_team_data(db_conn, team_identity):
    """Recupera i dati tecnici (stats, scores) usando l'identità risolta"""
    if db_conn is None:
        return {}
    
    target_name = team_identity
    if isinstance(team_identity, dict):
        target_name = team_identity.get("official_name")
        
    team = db_conn.teams.find_one({"name": target_name})
    
    if not team:
        return {}
    
    data = team.get("scores", {})
    stats = team.get("stats", {})
    
    data['motivation'] = stats.get("motivation", 10.0)
    data['strength_score'] = stats.get("strengthScore09", 5.0)
    data['rating_stored'] = team.get('rating_5_25', None)
    
    return data

def get_h2h_data_from_db(db_conn, home_team, away_team):
    if db_conn is None:
        return 0, 0, "Nessun Dato", {}
    
    doc = db_conn.h2h_by_round.find_one(
        {"matches": {"$elemMatch": {"home": home_team, "away": away_team}}},
        {"matches.$": 1}
    )
    
    if doc and "matches" in doc and len(doc["matches"]) > 0:
        h2h = doc["matches"][0].get("h2h_data", {})
        if h2h.get("status") == "No Data":
            return 0, 0, "Dati Insufficienti", {}
        
        extra = {
            "avg_goals_home": h2h.get("avg_goals_home", 1.2),
            "avg_goals_away": h2h.get("avg_goals_away", 1.0)
        }
        return h2h.get("home_score", 0), h2h.get("away_score", 0), h2h.get("history_summary", ""), extra
        
    return 0, 0, "Match non trovato in H2H DB", {}

def get_dynamic_rating(team_name, preloaded_data=None, bulk_cache=None):
    """Recupera rating e decide se mostrare i log (verbose). Supporta Bulk Cache"""
    if rating_lib is None:
        return 12.5, {}
    
    is_verbose = False if preloaded_data else True
    
    try:
        result = rating_lib.calculate_team_rating(team_name, verbose=is_verbose, bulk_cache=bulk_cache)
        if result:
            return result.get('rating_5_25', 12.5), result
        return 12.5, {}
    except Exception as e:
        if is_verbose:
            print(f"⚠️ Errore calcolo rating {team_name}: {e}")
        return 12.5, {}

def apply_randomness(value):
    if value == 0:
        return 0, 0
    fluctuation = random.uniform(-0.15, 0.15)
    adjusted = value * (1 + fluctuation)
    return round(adjusted, 4), fluctuation

def calculate_match_score(home_raw, away_raw, h2h_scores, base_val, algo_mode):
    safe_mode = algo_mode if algo_mode in WEIGHTS_CACHE else 5
    W = WEIGHTS_CACHE[safe_mode]

    h_power = home_raw['power']
    a_power = away_raw['power']
    h_att, h_def = home_raw['attack'], home_raw['defense']
    a_att, a_def = away_raw['attack'], away_raw['defense']
    
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

    if algo_mode == 4:
        h_power, _ = apply_randomness(h_power)
        a_power, _ = apply_randomness(a_power)
        h_motiv, _ = apply_randomness(h_motiv)
        a_motiv, _ = apply_randomness(a_motiv)
        h_rating, _ = apply_randomness(h_rating)
        a_rating, _ = apply_randomness(a_rating)

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

    freno_base_home = a_def
    freno_base_away = h_def
    
    gross_base_home = base_val + h_power_total
    gross_base_away = base_val + a_power_total
    
    net_base_home = max(0, gross_base_home - freno_base_home)
    net_base_away = max(0, gross_base_away - freno_base_away)

    h_tactical_diff = h_def - h_att
    a_tactical_diff = a_def - a_att
    
    freno_dyn_home = a_def + a_tactical_diff
    freno_dyn_away = h_def + h_tactical_diff
    
    gross_dyn_home = base_val + h_power_total
    gross_dyn_away = base_val + a_power_total
    
    net_dyn_home = max(0, gross_dyn_home - freno_dyn_home)
    net_dyn_away = max(0, gross_dyn_away - freno_dyn_away)

    final_home = (h_power_total + net_base_home + net_dyn_home) / 3
    final_away = (a_power_total + net_base_away + net_dyn_away) / 3

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
    bulk_cache = preloaded_data.get('bulk_cache') if preloaded_data else None

    h_id = get_identity_card(db, home_team, bulk_cache)
    a_id = get_identity_card(db, away_team, bulk_cache)

    if not preloaded_data:
        print(f"\n🤖 [ENGINE] Analisi: {home_team} vs {away_team}")
        print(f"⚙️ Algoritmo: {ALGO_NAMES.get(mode, mode)}")
        if h_id['official_name'] != home_team:
            print(f"   🔍 Identità Risolta: '{home_team}' -> '{h_id['official_name']}'")
        if a_id['official_name'] != away_team:
            print(f"   🔍 Identità Risolta: '{away_team}' -> '{a_id['official_name']}'")

    if preloaded_data:
        # ✅ CHECK SE È UNA COPPA
        is_cup = preloaded_data.get('is_cup', False)
        
        home_raw = preloaded_data['home_raw']
        away_raw = preloaded_data['away_raw']
        h2h_h = preloaded_data.get('h2h_h', 0)
        h2h_a = preloaded_data.get('h2h_a', 0)
        base_val = preloaded_data.get('base_val', 2.5)
        
        # ✅ SOLO se home_raw è un dict (non per coppe dove è già completo)
        if isinstance(home_raw, dict):
            home_raw['h2h_score'] = h2h_h
            away_raw['h2h_score'] = h2h_a
        
        H_OFF, A_OFF = h_id['official_name'], a_id['official_name']
    else:
        if db is None:
            print("❌ DB non connesso.")
            return

        H_OFF = h_id['official_name']
        A_OFF = a_id['official_name']

        match = db.matches.find_one({"home_team": H_OFF, "away_team": A_OFF})
        if not match:
            match = db.matches.find_one({"home_team": home_team, "away_team": away_team})
        
        competition = match.get("competition", "Sconosciuto") if match else "Sconosciuto"
        base_val, _ = calculate_base_goals(competition)

        h_data = get_team_data(db, h_id)
        a_data = get_team_data(db, a_id)

        h_rating_val, h_rating_full = get_dynamic_rating(H_OFF)
        a_rating_val, a_rating_full = get_dynamic_rating(A_OFF)
        
    if not preloaded_data:
        def clean_roster(team_data_full):
            if not team_data_full or "starters" not in team_data_full:
                return "N/A"
            return {
                "Squadra": team_data_full.get("team"),
                "Modulo": team_data_full.get("formation"),
                "Rating": f"{team_data_full.get('rating_5_25', 'N/A')}/25",
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

        if reliability_lib:
            h_rel = reliability_lib.calculate_reliability(H_OFF)
            a_rel = reliability_lib.calculate_reliability(A_OFF)
        else:
            h_rel, a_rel = 5.0, 5.0

        if bvs_lib:
            h_bvs, a_bvs = bvs_lib.get_bvs_score(H_OFF, A_OFF)
        else:
            h_bvs, a_bvs = 0.0, 0.0

        if field_lib:
            h_field, a_field = field_lib.calculate_field_factor(H_OFF, A_OFF, competition)
        else:
            h_field, a_field = 3.5, 3.5

        if lucifero_lib:
            h_luc = lucifero_lib.get_lucifero_score(H_OFF)
            a_luc = lucifero_lib.get_lucifero_score(A_OFF)
        else:
            h_luc, a_luc = 0.0, 0.0

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
        
        print(f"📊 Motivazioni: {home_team}={home_raw['motivation']} | {away_team}={away_raw['motivation']}")
        print(f"⭐ Rating Rosa: {home_team}={h_rating_val:.2f}/25 | {away_team}={a_rating_val:.2f}/25")
        print(f"⚔️  Attacco/Difesa: {home_team}={home_raw['attack']:.1f}/{home_raw['defense']:.1f} | {away_team}={away_raw['attack']:.1f}/{away_raw['defense']:.1f}")
        print(f"💎 Valore Rosa: {home_team}={home_raw['strength_score']} | {away_team}={away_raw['strength_score']}")
        print(f"🍀 Affidabilità: {home_team}={h_rel} | {away_team}={a_rel}")
        print(f"🏟️  Fattore Campo:{home_team}={h_field} | {away_team}={a_field}")
        print(f"🔥 Lucifero:     {home_team}={h_luc:.2f} | {away_team}={a_luc:.2f}")
        print(f"🔮 BVS Bonus:    {home_team}={h_bvs:+} | {away_team}={a_bvs:+}")

        h2h_h, h2h_a, h2h_msg, h2h_extra = get_h2h_data_from_db(db, H_OFF, A_OFF)
        print("DEBUG H2H:", H_OFF, A_OFF, "=>", h2h_h, h2h_a)

        home_raw['h2h_score'] = h2h_h
        away_raw['h2h_score'] = h2h_a

        print(f"📜 H2H Info: {h2h_msg} [Bonus: {h2h_h:.2f} - {h2h_a:.2f}]")
        
        home_raw['h2h_avg_goals'] = h2h_extra.get('avg_goals_home', 1.2)
        away_raw['h2h_avg_goals'] = h2h_extra.get('avg_goals_away', 1.0)

    if mode == 5:
        if not preloaded_data:
            print("✨ Esecuzione ENSEMBLE (1-4 + GLOBAL)...")
        
        results_h = []
        results_a = []
        
        for i in range(1, 5):
            nh, na = calculate_match_score(home_raw, away_raw, (h2h_h, h2h_a), base_val, i)
            results_h.append(nh)
            results_a.append(na)
            
        nh_global, na_global = calculate_match_score(home_raw, away_raw, (h2h_h, h2h_a), base_val, 5)
        results_h.append(nh_global)
        results_a.append(na_global)
        
        avg_h = sum(results_h) / 5
        avg_a = sum(results_a) / 5
        
        final_h, r_h = apply_randomness(avg_h)
        final_a, r_a = apply_randomness(avg_a)
        net_home, net_away = final_h, final_a
    else:
        net_home, net_away = calculate_match_score(home_raw, away_raw, (h2h_h, h2h_a), base_val, mode)

    if not preloaded_data:
        MAX_THEORETICAL_SCORE = 131.00
        perc_h = (net_home / MAX_THEORETICAL_SCORE) * 100
        perc_a = (net_away / MAX_THEORETICAL_SCORE) * 100

        print("-" * 55)
        print(f"🏁 RISULTATO FINALE ({ALGO_NAMES.get(mode)}):")
        print(f"   🏠 {home_team:<15}: {net_home:6.2f} / 131.00 ({perc_h:.1f}%)")
        print(f"   ✈️ {away_team:<15}: {net_away:6.2f} / 131.00 ({perc_a:.1f}%)")
        print("-" * 55)
    
    return net_home, net_away, home_raw, away_raw


# // modificato per: logica bulk
def preload_match_data(home_team, away_team,league=None, bulk_cache=None):
    """
    VERSIONE TURBO BULK V3: Esegue un unico viaggio al DB per caricare tutto.
    Integra calcolatori satellite per popolare i dati RAW in memoria.
    
    Args:
        bulk_cache: Se fornito, riutilizza questi dati invece di ricaricare
    """
    t_start = time.time()
    # ✅ Inizializza subito le variabili con valori di default
    league = ""
    competition = ""
    if bulk_cache is None:
        match_info = db.matches.find_one({"home_team": home_team, "away_team": away_team})
        
        if match_info is None:
            raise ValueError(f"❌ Partita {home_team} vs {away_team} non trovata nel database")
        
        league = match_info.get("league")
        if not league:
            raise ValueError(f"❌ Campo 'league' mancante per {home_team} vs {away_team}")
        
        competition = match_info.get("competition", league)

        bulk_cache = bulk_manager.get_all_data_bulk(home_team, away_team, league)
        print(f"📦 Bulk_cache caricato da DB per league: {league}", file=sys.stderr)
    else:
        print(f"♻️ Riutilizzo bulk_cache fornito", file=sys.stderr)
        
        # Estrai league da LEAGUE_STATS
        league = bulk_cache.get('LEAGUE_STATS', {}).get('league')
        
        # Fallback: estrai da MASTER_DATA se LEAGUE_STATS è vuoto
        if not league:
            master_data = bulk_cache.get('MASTER_DATA', {})
            if master_data:
                # Prendi la league dalla prima squadra
                first_team_data = next(iter(master_data.values()), {})
                league = first_team_data.get('league')
        
        print(f"🔍 [PRELOAD] League estratta: '{league}'", file=sys.stderr)
        
        if not league:
            raise ValueError(f"❌ Campo 'league' non trovato in bulk_cache. Verifica LEAGUE_STATS.")
        
        competition = league


    h_rating, _ = get_dynamic_rating(home_team, bulk_cache=bulk_cache)
    a_rating, _ = get_dynamic_rating(away_team, bulk_cache=bulk_cache)
    
    h_rel = reliability_lib.calculate_reliability(home_team, bulk_cache=bulk_cache) if reliability_lib else 5.0
    a_rel = reliability_lib.calculate_reliability(away_team, bulk_cache=bulk_cache) if reliability_lib else 5.0
    h_bvs, a_bvs = bvs_lib.get_bvs_score(home_team, away_team, bulk_cache=bulk_cache) if bvs_lib else (0, 0)
    h_field, a_field = field_lib.calculate_field_factor(home_team, away_team, league, bulk_cache=bulk_cache) if field_lib else (3.5, 3.5)
    h_luc = lucifero_lib.get_lucifero_score(home_team, bulk_cache=bulk_cache) if lucifero_lib else 0
    a_luc = lucifero_lib.get_lucifero_score(away_team, bulk_cache=bulk_cache) if lucifero_lib else 0
    
    # Usa direttamente MASTER_DATA (i scores sono già calcolati nel DB)
    master_data = bulk_cache.get("MASTER_DATA", {})

    if home_team not in master_data:
        raise ValueError(f"❌ {home_team} non trovato in MASTER_DATA")
    if away_team not in master_data:
        raise ValueError(f"❌ {away_team} non trovato in MASTER_DATA")

    h_data = master_data[home_team]
    a_data = master_data[away_team]

    h_scores = {
        'home_power': h_data['power'],
        'attack_home': h_data['attack'],
        'defense_home': h_data['defense']
    }
    a_scores = {
        'away_power': a_data['power'],
        'attack_away': a_data['attack'],
        'defense_away': a_data['defense']
    }

    print(f"✅ Scores da MASTER_DATA: home_power={h_scores['home_power']}, away_power={a_scores['away_power']}", file=sys.stderr)
    h_motiv = motiv_lib.get_motivation_live_bulk(home_team, league, bulk_cache) if motiv_lib else 10
    a_motiv = motiv_lib.get_motivation_live_bulk(away_team, league, bulk_cache) if motiv_lib else 10
    h_val = value_rosa_lib.get_value_score_live_bulk(home_team, league, bulk_cache) if value_rosa_lib else 5
    a_val = value_rosa_lib.get_value_score_live_bulk(away_team, league, bulk_cache) if value_rosa_lib else 5

    h2h_data = bulk_cache.get("MATCH_H2H", {})
    h2h_h = h2h_data.get('h_score', 0)
    h2h_a = h2h_data.get('a_score', 0)
    base_val, _ = calculate_base_goals(league, bulk_cache)

    home_raw = {
        'power': h_scores['home_power'],
        'attack': h_scores['attack_home'],
        'defense': h_scores['defense_home'],
        'motivation': h_motiv,
        'strength_score': h_val,
        'rating': h_rating,
        'reliability': h_rel,
        'bvs': h_bvs,
        'field_factor': h_field,
        'lucifero': h_luc,
        'h2h_score': h2h_h
    }
    
    away_raw = {
        'power': a_scores['away_power'],
        'attack': a_scores['attack_away'],
        'defense': a_scores['defense_away'],
        'motivation': a_motiv,
        'strength_score': a_val,
        'rating': a_rating,
        'reliability': a_rel,
        'bvs': a_bvs,
        'field_factor': a_field,
        'lucifero': a_luc,
        'h2h_score': h2h_a
    }

    print(f"⏱️ PRELOAD DATI (METODO BULK): {time.time()-t_start:.3f}s")

    return {
        'bulk_cache': bulk_cache,
        'home_raw': home_raw,
        'away_raw': away_raw,
        'h2h_h': h2h_h,
        'h2h_a': h2h_a,
        'base_val': base_val,
        'home_team': home_team,
        'away_team': away_team,
        'competition': competition  # ✅ Aggiungi questa riga
    }

if __name__ == "__main__":
    print("\n--- ⚽ ENGINE CORE V3.0 - TEST MODE ---")
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
            import traceback
            traceback.print_exc()
            exit()
        
        simulations = 500
        
        results_h = []
        results_a = []
        wins_h = wins_a = draws = 0
        
        print(f"🚀 {simulations} simulazioni...")
        for i in range(simulations):
            try:
                s_h, s_a, _, _ = predict_match(home, away, mode=5, preloaded_data=static_data)
                if s_h is None:
                    continue
                
                results_h.append(s_h)
                results_a.append(s_a)
                
                if s_h > s_a + 0.5:
                    wins_h += 1
                elif s_a > s_h + 0.5:
                    wins_a += 1
                else:
                    draws += 1
                
                if i % 50 == 0 or i == simulations-1:
                    pct = (i+1)/simulations*100
                    print(f"\r🎲 {pct:.0f}% ({i+1}/{simulations}) | {s_h:.1f}-{s_a:.1f}", end="")
                    
            except Exception as e:
                continue
        
        print()
        
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