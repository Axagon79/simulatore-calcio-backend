import sys
import os
from datetime import datetime, timedelta
from tqdm import tqdm
from colorama import Fore, Style, init

# --- FIX UNIVERSALE PER I PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grandparent_dir) 
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)

try:
    from config import db
except ImportError:
    print(f"{Fore.RED}ERRORE CRITICO: Non trovo 'config.py'.{Style.RESET_ALL}")
    sys.exit(1)

init(autoreset=True)

COLLECTION_NAME = "h2h_by_round"

# --- CACHE GLOBALE PER VELOCITÀ ---
TEAMS_CACHE = {}

def load_teams_cache():
    """Carica tutta la rubrica teams_identity in memoria."""
    if TEAMS_CACHE: return
    print(f"{Fore.YELLOW}📥 Caricamento Cache Squadre (teams_identity)...{Style.RESET_ALL}")
    cursor = db.teams_identity.find({})
    for doc in cursor:
        t_id = doc.get("tm_id")
        all_names = doc.get("all_names", [])
        team_data = {"id": t_id, "names": all_names}
        
        for name in all_names:
            clean_name = name.lower().strip()
            TEAMS_CACHE[clean_name] = team_data
    print(f"✅ Cache caricata con {len(TEAMS_CACHE)} chiavi di ricerca.")

def parse_date(date_str):
    """Tenta di convertire una stringa data in oggetto datetime."""
    formats = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

def get_offline_h2h_score(match_data):
    """
    Calcola H2H con:
    1. Risoluzione nomi intelligente (Identity)
    2. Filtro ultimi 20 anni
    3. Pesi temporali (Recency Bias)
    """
    load_teams_cache()

    # 1. IDENTITÀ SQUADRE
    home_name = match_data.get("home", "").strip()
    away_name = match_data.get("away", "").strip()
    
    home_identity = TEAMS_CACHE.get(home_name.lower())
    away_identity = TEAMS_CACHE.get(away_name.lower())
    
    # Fallback canonical
    if not home_identity and match_data.get("home_canonical"):
        home_identity = TEAMS_CACHE.get(match_data.get("home_canonical").lower())
    if not away_identity and match_data.get("away_canonical"):
        away_identity = TEAMS_CACHE.get(match_data.get("away_canonical").lower())

    # Setup liste candidati
    if home_identity:
        home_candidates = home_identity["names"]
        home_id_check = home_identity["id"] # Utile per debug
    else:
        home_candidates = [home_name]
        if match_data.get("home_canonical"): home_candidates.append(match_data.get("home_canonical"))

    if away_identity:
        away_candidates = away_identity["names"]
        away_id_check = away_identity["id"]
    else:
        away_candidates = [away_name]
        if match_data.get("away_canonical"): away_candidates.append(match_data.get("away_canonical"))

    # 2. RICERCA DOCUMENTO H2H
    query = {
        "$or": [
            {"team_a": {"$in": home_candidates}, "team_b": {"$in": away_candidates}},
            {"team_a": {"$in": away_candidates}, "team_b": {"$in": home_candidates}}
        ]
    }
    h2h_doc = db.raw_h2h_data.find_one(query)

    if not h2h_doc:
        return None 

    matches = h2h_doc.get("matches", [])
    if not matches: return None

    # 3. CALCOLO CON FILTRI TEMPORALI
    current_date = datetime.now()
    cutoff_20_years = current_date - timedelta(days=365*20) # 20 anni fa
    cutoff_10_years = current_date - timedelta(days=365*10)
    cutoff_5_years = current_date - timedelta(days=365*5)

    weighted_score_home = 0.0
    weighted_score_away = 0.0
    total_weight = 0.0
    
    valid_matches_count = 0
    wins_home_count = 0
    wins_away_count = 0
    draws_count = 0

    for m in matches:
        # Data
        m_date_str = m.get('date')
        if not m_date_str: continue
        
        m_date = parse_date(m_date_str)
        if not m_date: continue

        # FILTRO 20 ANNI
        if m_date < cutoff_20_years:
            continue # Partita troppo vecchia, ignorare

        # CALCOLO PESO (Recency Bias)
        weight = 0.5 # Default (tra 10 e 20 anni)
        if m_date >= cutoff_5_years:
            weight = 1.0 # Molto recente -> conta tantissimo
        elif m_date >= cutoff_10_years:
            weight = 0.75 # Medio

        winner = m.get('winner')
        if not winner: continue

        points_home = 0
        points_away = 0
        is_valid_result = False

        # Logica Vincitore
        if winner in home_candidates:
            points_home = 3
            wins_home_count += 1
            is_valid_result = True
        elif winner in away_candidates:
            points_away = 3
            wins_away_count += 1
            is_valid_result = True
        elif winner.lower() == "draw" or winner == "draw":
            points_home = 1
            points_away = 1
            draws_count += 1
            is_valid_result = True
        
        if is_valid_result:
            weighted_score_home += (points_home * weight)
            weighted_score_away += (points_away * weight)
            total_weight += (3 * weight) # Il massimo punteggio possibile per questo match pesato
            valid_matches_count += 1

    # 4. NORMALIZZAZIONE FINALE (0-10)
    if total_weight > 0:
        final_home_score = round((weighted_score_home / total_weight) * 10, 2)
        final_away_score = round((weighted_score_away / total_weight) * 10, 2)
    else:
        # Nessuna partita valida negli ultimi 20 anni
        return None 

    return {
        "home_score": final_home_score,
        "away_score": final_away_score,
        "history_summary": f"{home_name} V{wins_home_count} | {away_name} V{wins_away_count} | P{draws_count} (su {valid_matches_count} match <20anni)",
        "total_matches": valid_matches_count
    }

def update_round_h2h_matrix():
    print(f"{Fore.CYAN}🏟️  CALCOLATORE MATRICE H2H - ULTIMATE (Identity + 20Y + Weights){Style.RESET_ALL}")
    print("============================================================")

    rounds_cursor = db[COLLECTION_NAME].find({})
    rounds = list(rounds_cursor)
    total_rounds = len(rounds)

    if total_rounds == 0:
        print(f"{Fore.RED}❌ Nessuna giornata trovata.{Style.RESET_ALL}")
        return

    print(f"🚀 Trovate {total_rounds} giornate. Inizio elaborazione...")

    updated_matches_count = 0
    
    for round_doc in tqdm(rounds, desc="Elaborazione", unit="round"):
        matches_list = round_doc.get("matches", [])
        modified = False
        
        for match in matches_list:
            h2h_result = get_offline_h2h_score(match)
            
            if h2h_result:
                match["h2h_data"] = h2h_result
                match["h2h_last_updated"] = datetime.now()
                modified = True
                updated_matches_count += 1
            else:
                # Se dopo il filtro 20 anni non rimane nulla, mettiamo No Data
                if match.get("h2h_data") is None or "history_summary" not in match.get("h2h_data", {}):
                    match["h2h_data"] = {"status": "No Relevant Data (<20y)"}
                    modified = True

        if modified:
            db[COLLECTION_NAME].update_one(
                {"_id": round_doc["_id"]},
                {"$set": {"matches": matches_list}}
            )

    print("\n" + "="*60)
    print(f"{Fore.GREEN}✅ AGGIORNAMENTO COMPLETATO!{Style.RESET_ALL}")
    print(f"📊 Partite arricchite: {updated_matches_count}")
    print("="*60)

if __name__ == "__main__":
    update_round_h2h_matrix()
