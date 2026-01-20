import sys
import os
import json
import math
from datetime import datetime, timedelta
from tqdm import tqdm
from colorama import Fore, Style, init

# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

try:
    from config import db
except ImportError:
    print("❌ Errore import config")
    sys.exit(1)

init(autoreset=True)

SOURCE_COLLECTION = "raw_h2h_data_v2" 
TARGET_COLLECTION = "h2h_by_round"

def extract_goals_from_score(score_str):
    """
    Estrae i gol da stringhe tipo '2:1', '1-1', '3 : 0'
    Restituisce (gol_casa, gol_trasferta)
    """
    try:
        if ":" in score_str:
            parts = score_str.split(":")
        elif "-" in score_str:
            parts = score_str.split("-")
        else:
            return 0, 0
        
        return int(parts[0].strip()), int(parts[1].strip())
    except:
        return 0, 0

def calculate_match_points(winner, home_name_db, away_name_db, home_pos, away_pos):
    """
    Applica la Formula Dinamica Delta per calcolare i punti H2H.
    """
    # Default se mancano le posizioni
    if not home_pos: home_pos = 10
    if not away_pos: away_pos = 10

    # Riconoscimento Vincitore
    is_home_winner = winner.lower() in home_name_db.lower() or home_name_db.lower() in winner.lower()
    is_away_winner = winner.lower() in away_name_db.lower() or away_name_db.lower() in winner.lower()
    
    points_h = 0.0
    points_a = 0.0

    # --- LOGICA VITTORIE ---
    if is_home_winner:
        difficulty_mult = 1.0 + (home_pos - away_pos) * 0.02
        difficulty_mult = max(0.5, min(1.5, difficulty_mult))
        points_h = 3.0 * difficulty_mult
        
    elif is_away_winner:
        difficulty_mult = 1.0 + (away_pos - home_pos) * 0.02
        difficulty_mult = max(0.5, min(1.5, difficulty_mult))
        points_a = 3.0 * difficulty_mult
        
    elif winner == "Draw":
        # --- LOGICA PAREGGI ---
        bonus_h = (home_pos - away_pos) * 0.05
        points_h = 1.0 + bonus_h
        points_h = points_h * 0.9 
        points_h = max(0.2, min(2.0, points_h))

        bonus_a = (away_pos - home_pos) * 0.05
        points_a = 1.0 + bonus_a
        points_a = points_a * 1.1
        points_a = max(0.2, min(2.0, points_a))
        
    return points_h, points_a

def get_h2h_score_v2(match_payload):
    """Calcola i dati rispettando la struttura originale del database."""
    id_h = match_payload.get("home_tm_id")
    id_a = match_payload.get("away_tm_id")
    home_name_curr = match_payload.get("home", "")
    away_name_curr = match_payload.get("away", "")
    
    if not id_h or not id_a:
        return {"status": "No ID", "h2h_weight": 0}

    # Query per ID (Veloce e precisa)
    doc = db[SOURCE_COLLECTION].find_one({
        "$or": [
            {"tm_id_a": int(id_h), "tm_id_b": int(id_a)},
            {"tm_id_a": int(id_a), "tm_id_b": int(id_h)}
        ]
    })

    if not doc or not doc.get("matches"):
        return {"status": "No Data", "h2h_weight": 0, "home_score": 5.0, "away_score": 5.0}

    matches = doc["matches"]
    w_score_h, w_score_a = 0.0, 0.0
    wins_h, wins_a, draws = 0, 0, 0
    goals_h, goals_a = 0, 0
    
    # Identificazione squadra casa/trasferta storica tramite ID
    official_h_name_tm = doc["team_a"] if doc["tm_id_a"] == int(id_h) else doc["team_b"]

    for m in matches:
        score_raw = m.get("score", "0:0")
        if score_raw == "-:-": continue
        
        # Punti Formula Delta
        p_h, p_a = calculate_match_points(m["winner"], m["home_team"], m["away_team"], m.get("home_pos"), m.get("away_pos"))
        
        # Gol con funzione dedicata
        g_casa, g_trasf = extract_goals_from_score(score_raw)

        # Mapping storico -> attuale (Gestione campi invertiti)
        if m["home_team"].lower() in official_h_name_tm.lower() or official_h_name_tm.lower() in m["home_team"].lower():
            w_score_h += p_h
            w_score_a += p_a
            goals_h += g_casa
            goals_a += g_trasf
            if m["winner"] == "Draw": draws += 1
            elif m["winner"].lower() in official_h_name_tm.lower(): wins_h += 1
            else: wins_a += 1
        else:
            w_score_h += p_a
            w_score_a += p_h
            goals_h += g_trasf
            goals_a += g_casa
            if m["winner"] == "Draw": draws += 1
            elif m["winner"].lower() in official_h_name_tm.lower(): wins_h += 1
            else: wins_a += 1

    total_matches = len(matches)
    avg_g_h = goals_h / total_matches if total_matches > 0 else 0
    avg_g_a = goals_a / total_matches if total_matches > 0 else 0

    # Normalizzazione Grafici (Radice Quadrata)
    MAX_THEORETICAL = total_matches * 3.5 if total_matches > 0 else 1
    norm_h = math.sqrt(w_score_h / MAX_THEORETICAL) * 10 if w_score_h > 0 else 0
    norm_a = math.sqrt(w_score_a / MAX_THEORETICAL) * 10 if w_score_a > 0 else 0
    
    confidence = 1 if total_matches >= 3 else 0.5

    return {
        "status": "Calculated",
        "home_score": round(norm_h, 2),
        "away_score": round(norm_a, 2),
        
        # ⭐ NUOVI CAMPI GOL (Utili per il Motore)
        "avg_goals_home": round(avg_g_h, 2),
        "avg_goals_away": round(avg_g_a, 2),
        "avg_total_goals": round(avg_g_h + avg_g_a, 2),
        
        "history_summary": f"{home_name_curr} V{wins_h} | {away_name_curr} V{wins_a} | P{draws} (Avg Gol: {avg_g_h:.1f}-{avg_g_a:.1f})",
        "total_matches": total_matches,
        "h2h_weight": confidence,
        "details": "V2 Pro (Goals + Delta Difficulty) [Bulk Integrated]"
    }

def run_calculator(target_league=None):
    leagues_in_db = sorted(db[TARGET_COLLECTION].distinct("league"))
    
    if target_league:
        selected_leagues = leagues_in_db if target_league.lower() == "all" else [target_league]
    else:
        print(f"\n{Fore.CYAN}🚀 RIPRISTINO STRUTTURA COLLEZIONE H2H")
        for i, l in enumerate(leagues_in_db, 1): print(f"  {i}. {l}")
        print(f"  {len(leagues_in_db) + 1}. 🔥 ELABORA TUTTI")
        choice = input(f"\n🎯 Scelta: ").strip()
        if not choice: return
        selected_leagues = leagues_in_db if int(choice) == len(leagues_in_db) + 1 else [leagues_in_db[int(choice) - 1]]

    for league_name in selected_leagues:
        rounds = list(db[TARGET_COLLECTION].find({"league": league_name}))
        print(f"\nProcessing {Fore.GREEN}{league_name}{Style.RESET_ALL}...")
        
        for r in tqdm(rounds, desc="Aggiornamento DB", disable=target_league is not None):
            matches_updated = []
            for m in r.get("matches", []):
                res = get_h2h_score_v2(m)
                
                # --- AGGIORNAMENTO CHIRURGICO (Preserva Lucifero) ---
                h2h_obj = m.get("h2h_data", {})
                if not isinstance(h2h_obj, dict): h2h_obj = {}
                h2h_obj.update(res)
                m["h2h_data"] = h2h_obj
                
                # Sincronizzazione campi esterni per compatibilità frontend
                if res.get("status") == "Calculated":
                    m["home_score"] = res["home_score"]
                    m["away_score"] = res["away_score"]
                    m["avg_goals_home"] = res["avg_goals_home"]
                    m["avg_goals_away"] = res["avg_goals_away"]
                    m["history_summary"] = res["history_summary"]
                
                matches_updated.append(m)
            
            db[TARGET_COLLECTION].update_one({"_id": r["_id"]}, {"$set": {"matches": matches_updated}})

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_calculator(sys.argv[1])
    else:
        run_calculator()