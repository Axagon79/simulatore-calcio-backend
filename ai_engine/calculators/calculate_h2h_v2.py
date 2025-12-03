import sys
import os
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
    # Default se mancano le posizioni (es. inizio stagione o dati vecchi)
    if not home_pos: home_pos = 10
    if not away_pos: away_pos = 10

    # Riconoscimento Vincitore
    # I nomi in 'winner' vengono da Transfermarkt (scraped). Dobbiamo capire a chi corrispondono.
    # Usiamo un match parziale semplice
    is_home_winner = winner.lower() in home_name_db.lower() or home_name_db.lower() in winner.lower()
    is_away_winner = winner.lower() in away_name_db.lower() or away_name_db.lower() in winner.lower()
    
    # Inizializza Punteggi
    points_h = 0.0
    points_a = 0.0

    # --- LOGICA VITTORIE (Moltiplicatore Difficoltà) ---
    # Moltiplicatore = 1 + (PosizioneTua - PosizioneAvversario) * 0.02
    # Se sei 18° e batti 1°: 1 + (18 - 1) * 0.02 = 1.34 (Bonus 34%)
    # Se sei 1° e batti 18°: 1 + (1 - 18) * 0.02 = 0.66 (Malus 34%)
    
    if is_home_winner:
        # Vittoria Casa
        difficulty_mult = 1.0 + (home_pos - away_pos) * 0.02
        # Limiti di sicurezza (da 0.5 a 1.5)
        difficulty_mult = max(0.5, min(1.5, difficulty_mult))
        points_h = 3.0 * difficulty_mult
        
    elif is_away_winner:
        # Vittoria Ospite
        difficulty_mult = 1.0 + (away_pos - home_pos) * 0.02
        difficulty_mult = max(0.5, min(1.5, difficulty_mult))
        points_a = 3.0 * difficulty_mult
        
    elif winner == "Draw":
        # --- LOGICA PAREGGI (Bonus Additivo) ---
        # Punti = 1.0 + (PosizioneTua - PosizioneAvversario) * 0.05
        
        # Pareggio Casa
        bonus_h = (home_pos - away_pos) * 0.05
        points_h = 1.0 + bonus_h
        # Malus leggero per casa (0.9 base)
        points_h = points_h * 0.9 
        points_h = max(0.2, min(2.0, points_h))

        # Pareggio Ospite
        bonus_a = (away_pos - home_pos) * 0.05
        points_a = 1.0 + bonus_a
        # Bonus leggero per trasferta (1.1 base)
        points_a = points_a * 1.1
        points_a = max(0.2, min(2.0, points_a))
        
    return points_h, points_a

def get_h2h_score_v2(home_name, away_name, h_canon, a_canon):
    load_teams_cache()
    
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

    for m in matches:
        # Filtri
        if m.get("score") == "-:-" or m.get("winner") == "-": continue
        d_obj = parse_date(m.get("date"))
        if not d_obj or d_obj < cutoff_20y: continue

        # Peso Tempo
        time_weight = 1.0 if d_obj >= cutoff_5y else 0.5

        # Dati dal match storico
        # ATTENZIONE: m['home_team'] è la squadra che giocava in casa NEL PASSATO.
        # Dobbiamo capire se corrisponde alla nostra 'home_name' attuale o 'away_name' attuale.
        
        hist_home_name = m.get("home_team")
        hist_away_name = m.get("away_team")
        hist_home_pos = m.get("home_pos")
        hist_away_pos = m.get("away_pos")
        winner = m.get("winner")

        # Chi è chi?
        # current_home_is_hist_home = home_name.lower() in hist_home_name.lower() ...
        # Semplifichiamo: calcoliamo i punti per la Home storica e Away storica
        # Poi li assegniamo alla squadra giusta.
        
        pts_hist_h, pts_hist_a = calculate_match_points(winner, hist_home_name, hist_away_name, hist_home_pos, hist_away_pos)
        
        # Assegnazione
        # Se HomeAttuale == HomeStorica
        if home_name.lower() in hist_home_name.lower() or (h_canon and h_canon.lower() in hist_home_name.lower()):
            w_score_h += pts_hist_h * time_weight
            w_score_a += pts_hist_a * time_weight
            if winner == hist_home_name: wins_h += 1
            elif winner == hist_away_name: wins_a += 1
            else: draws += 1
            
        # Se HomeAttuale == AwayStorica (Partita a campi invertiti)
        elif home_name.lower() in hist_away_name.lower() or (h_canon and h_canon.lower() in hist_away_name.lower()):
            w_score_h += pts_hist_a * time_weight # HomeAttuale prende i punti che fece l'AwayStorica
            w_score_a += pts_hist_h * time_weight
            if winner == hist_away_name: wins_h += 1
            elif winner == hist_home_name: wins_a += 1
            else: draws += 1
            
        total_weight += 3.0 * time_weight # Max teorico (circa)
        valid_matches += 1

    if valid_matches == 0:
        return {"home_score": 5.0, "away_score": 5.0, "h2h_weight": 0.0, "history_summary": "Nessun dato rilevante"}

    # Normalizzazione 0-10
    # Usiamo una normalizzazione morbida per evitare estremi
    raw_h = w_score_h
    raw_a = w_score_a
    
    # Evitiamo divisione per zero
    if (raw_h + raw_a) == 0:
        norm_h = 5.0
        norm_a = 5.0
    else:
        norm_h = (raw_h / (raw_h + raw_a)) * 10
        norm_a = (raw_a / (raw_h + raw_a)) * 10
    
    confidence = 1.0 if valid_matches >= 3 else 0.5

    return {
        "home_score": round(norm_h, 2),
        "away_score": round(norm_a, 2),
        "history_summary": f"{home_name} V{wins_h} | {away_name} V{wins_a} | P{draws} ({valid_matches} match)",
        "total_matches": valid_matches,
        "h2h_weight": confidence,
        "details": "V2 Algorithm (Dynamic Delta)"
    }

def run_calculator():
    print(f"{Fore.CYAN}🧠 CALCOLATORE H2H v2.0 PRO (Formula Dinamica){Style.RESET_ALL}")
    
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

    print(f"\n✅ Aggiornate {count} partite con algoritmo PRO.")

if __name__ == "__main__":
    run_calculator()
