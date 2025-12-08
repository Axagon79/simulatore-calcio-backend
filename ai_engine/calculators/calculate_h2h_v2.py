import sys
import os
import json
from datetime import datetime, timedelta
from tqdm import tqdm
from colorama import Fore, Style, init


# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grandparent_dir) 
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)


try:
    from config import db
except ImportError:
    print("❌ Errore import config")
    sys.exit(1)


init(autoreset=True)


SOURCE_COLLECTION = "raw_h2h_data_v2" 
TARGET_COLLECTION = "h2h_by_round"


# Cache per velocizzare
TEAMS_CACHE = {}


def load_teams_cache():
    if TEAMS_CACHE: return
    print(f"{Fore.YELLOW}📥 Caricamento Cache Squadre...{Style.RESET_ALL}")
    for t in db.teams.find({}):
        names = [t["name"]] + t.get("aliases", []) + [t.get("aliases_transfermarkt")]
        names = [n.lower().strip() for n in names if n]
        data = {"names": names, "official_name": t["name"]}
        for n in names:
            TEAMS_CACHE[n] = data
    print(f"✅ Cache pronta.")


def parse_date(date_str):
    formats = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


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


def get_h2h_score_v2(home_name, away_name, h_canon, a_canon):
    load_teams_cache()

    # --- FIX NOMI: MAPPATURA MANUALE ---
    # Inserito qui per intercettare i nomi sbagliati PRIMA della ricerca
    if home_name == "Roma": home_name = "AS Roma"
    if away_name == "Roma": away_name = "AS Roma"
    if home_name == "Milan": home_name = "AC Milan"
    if away_name == "Milan": away_name = "AC Milan"
    if home_name == "Inter": home_name = "Inter Milan"
    if away_name == "Inter": away_name = "Inter Milan"
    # -----------------------------------
    
    # Trova Documento H2H
    doc = db[SOURCE_COLLECTION].find_one({
        "$or": [
            {"team_a": {"$in": [home_name, h_canon]}, "team_b": {"$in": [away_name, a_canon]}},
            {"team_a": {"$in": [away_name, a_canon]}, "team_b": {"$in": [home_name, h_canon]}},
        ]
    })


    if not doc: return None
    matches = doc.get("matches", [])
    if not matches: return None


    current_date = datetime.now()
    cutoff_20y = current_date - timedelta(days=365*20)
    cutoff_5y = current_date - timedelta(days=365*5)


    w_score_h = 0.0
    w_score_a = 0.0
    total_weight = 0.0
    valid_matches = 0


    # Stats per Summary
    wins_h = 0
    wins_a = 0
    draws = 0
    
    # ⭐ NUOVO: Accumulatori Gol Ponderati
    total_goals_scored_h = 0.0
    total_goals_scored_a = 0.0
    total_goals_weight = 0.0


    for m in matches:
        if m.get("score") == "-:-" or m.get("winner") == "-": continue
        d_obj = parse_date(m.get("date"))
        if not d_obj or d_obj < cutoff_20y: continue


        # Peso Tempo
        time_weight = 1.0 if d_obj >= cutoff_5y else 0.5


        hist_home_name = m.get("home_team")
        hist_away_name = m.get("away_team")
        hist_home_pos = m.get("home_pos")
        hist_away_pos = m.get("away_pos")
        winner = m.get("winner")
        score = m.get("score", "0:0")


        # Calcolo punti
        pts_hist_h, pts_hist_a = calculate_match_points(winner, hist_home_name, hist_away_name, hist_home_pos, hist_away_pos)
        
        # Estrazione Gol Partita Storica
        g_h_hist, g_a_hist = extract_goals_from_score(score)


        # --- ASSEGNAZIONE CORRETTA (Chi è chi?) ---
        
        # CASO 1: Home Attuale = Home Storica (Partita Normale)
        if home_name.lower() in hist_home_name.lower() or (h_canon and h_canon.lower() in hist_home_name.lower()):
            # Punti
            w_score_h += pts_hist_h * time_weight
            w_score_a += pts_hist_a * time_weight
            
            # Gol
            total_goals_scored_h += g_h_hist * time_weight
            total_goals_scored_a += g_a_hist * time_weight
            
            if winner == hist_home_name: wins_h += 1
            elif winner == hist_away_name: wins_a += 1
            else: draws += 1
            
        # CASO 2: Home Attuale = Away Storica (Partita a campi invertiti)
        elif home_name.lower() in hist_away_name.lower() or (h_canon and h_canon.lower() in hist_away_name.lower()):
            # Punti (Invertiti)
            w_score_h += pts_hist_a * time_weight 
            w_score_a += pts_hist_h * time_weight
            
            # Gol (Invertiti: Home Attuale ha fatto i gol dell'Away Storica)
            total_goals_scored_h += g_a_hist * time_weight
            total_goals_scored_a += g_h_hist * time_weight


            if winner == hist_away_name: wins_h += 1 # L'Away storica (cioè Home attuale) ha vinto
            elif winner == hist_home_name: wins_a += 1
            else: draws += 1
            
        total_weight += 3.0 * time_weight
        total_goals_weight += time_weight # Peso puro per la media gol
        valid_matches += 1


    if valid_matches == 0:
        return {"home_score": 5.0, "away_score": 5.0, "h2h_weight": 0.0, "history_summary": "Nessun dato rilevante"}


    # Normalizzazione Punteggi 0-10
    raw_h = w_score_h
    raw_a = w_score_a
    
    if (raw_h + raw_a) == 0:
        norm_h = 5.0; norm_a = 5.0
    else:
        norm_h = (raw_h / (raw_h + raw_a)) * 10
        norm_a = (raw_a / (raw_h + raw_a)) * 10
    
    # Calcolo Medie Gol Ponderate
    avg_g_h = total_goals_scored_h / total_goals_weight if total_goals_weight > 0 else 0
    avg_g_a = total_goals_scored_a / total_goals_weight if total_goals_weight > 0 else 0


    confidence = 1.0 if valid_matches >= 3 else 0.5


    return {
        "home_score": round(norm_h, 2),
        "away_score": round(norm_a, 2),
        
        # ⭐ NUOVI CAMPI GOL (Utili per il Motore)
        "avg_goals_home": round(avg_g_h, 2),
        "avg_goals_away": round(avg_g_a, 2),
        "avg_total_goals": round(avg_g_h + avg_g_a, 2),
        
        "history_summary": f"{home_name} V{wins_h} | {away_name} V{wins_a} | P{draws} (Avg Gol: {avg_g_h:.1f}-{avg_g_a:.1f})",
        "total_matches": valid_matches,
        "h2h_weight": confidence,
        "details": "V2 Pro (Goals + Delta Difficulty)"
    }


def run_calculator():
    print(f"{Fore.CYAN}🧠 CALCOLATORE H2H v2.0 PRO (Formula Dinamica + GOL + FIX NOMI){Style.RESET_ALL}")
    
    rounds = list(db[TARGET_COLLECTION].find({}))
    count = 0
    
    for r in tqdm(rounds, desc="Elaborazione"):
        modified = False
        for m in r.get("matches", []):
            res = get_h2h_score_v2(m["home"], m["away"], m.get("home_canonical"), m.get("away_canonical"))
            if res:
                m["h2h_data"] = res
                m["h2h_last_updated"] = datetime.now()
                modified = True
                count += 1
            else:
                m["h2h_data"] = {"status": "No Data", "h2h_weight": 0.0}
                modified = True
        
        if modified:
            db[TARGET_COLLECTION].update_one({"_id": r["_id"]}, {"$set": {"matches": r["matches"]}})


# --- FUNZIONE DI TEST RAPIDO ---
def test_manuale(squadra_casa, squadra_trasferta):
    print(f"\n🧪 TEST MANUALE: {squadra_casa} (Casa) vs {squadra_trasferta} (Trasferta)")
    # Nota: I canonical names (None, None) servono solo se il nome principale fallisce
    result = get_h2h_score_v2(squadra_casa, squadra_trasferta, None, None)
    
    if result:
        print(json.dumps(result, indent=4))
    else:
        print("❌ Nessun dato H2H trovato tra queste due squadre.")


if __name__ == "__main__":
    # --- MODALITÀ TEST (DISATTIVATA PER PRODUZIONE) ---
    # test_manuale("Cagliari", "Roma")
    
    # --- MODALITÀ PRODUZIONE (ATTIVA) ---
    # Questo lancia l'aggiornamento di TUTTE le partite nel database.
    run_calculator()
