import sys
import os
import json
from datetime import datetime, timedelta
from tqdm import tqdm
from colorama import Fore, Style, init
from typing import Optional, List, Dict, Set

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
    """Carica la cache con PRIORITÀ alle squadre principali (evita conflitti con squadre giovanili)"""
    if TEAMS_CACHE: 
        return
    
    print(f"{Fore.YELLOW}📥 Caricamento Cache Squadre...{Style.RESET_ALL}")
    
    teams_list = list(db.teams.find({}))
    
    # 🎯 PRIORITÀ: Prima squadre principali, poi giovanili
    def is_main_team(team_name):
        """Identifica se è una squadra principale (non giovanile/riserve)"""
        lower = team_name.lower()
        youth_keywords = ['u23', 'u21', 'u19', 'primavera', 'youth', 'b team', 'ii', ' b', 'next gen', 'ng']
        return not any(kw in lower for kw in youth_keywords)
    
    # Separa squadre principali e giovanili
    main_teams = [t for t in teams_list if is_main_team(t["name"])]
    youth_teams = [t for t in teams_list if not is_main_team(t["name"])]
    
    # 🔑 PROCESSA PRIMA LE SQUADRE PRINCIPALI (hanno priorità nella cache)
    for t in main_teams + youth_teams:
        # Raccogli tutti i possibili nomi
        names = [t["name"]]
        
        # Aggiungi aliases
        if t.get("aliases"):
            if isinstance(t["aliases"], list):
                names.extend(t["aliases"])
            else:
                names.append(t["aliases"])
        
        # Aggiungi aliases_transfermarkt
        if t.get("aliases_transfermarkt"):
            names.append(t["aliases_transfermarkt"])
        
        # Normalizza e pulisci
        names = [n.lower().strip() for n in names if n]
        
        data = {
            "names": names, 
            "official_name": t["name"],
            "_id": t["_id"]
        }
        
        # ⚡ INSERISCI SOLO SE NON ESISTE (priorità a main_teams!)
        for n in names:
            if n not in TEAMS_CACHE:
                TEAMS_CACHE[n] = data
    
    print(f"✅ Cache pronta con {len(TEAMS_CACHE)} alias.")

def normalize_name(name):
    """
    Normalizzazione light:
    - minuscolo
    - strip
    - rimozione accenti base
    """
    if not name:
        return ""
    name = name.lower().strip()
    replacements = {
        "ü": "u", "ö": "o", "ä": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "á": "a", "à": "a", "â": "a", "ã": "a",
        "í": "i", "ì": "i", "î": "i",
        "ó": "o", "ò": "o", "ô": "o",
        "ú": "u", "ù": "u",
        "ñ": "n", "ç": "c",
    }
    for k, v in replacements.items():
        name = name.replace(k, v)
    return name

def get_team_aliases(team_name: str, team_data: Optional[dict] = None) -> list:
    """
    Genera tutti i possibili alias per una squadra (come scraper).
    Include: nome originale, normalizzato, alias DB, parti del nome.
    """
    aliases = set()
    
    # Nome originale
    aliases.add(team_name.lower().strip())
    
    # Nome normalizzato
    normalized = normalize_name(team_name)
    if normalized:
        aliases.add(normalized)
    
    # Alias dal team_data (già in TEAMS_CACHE)
    if team_data and "names" in team_data:
        for alias in team_data["names"]:
            if alias:
                aliases.add(alias.lower().strip())
                # Normalizza anche gli alias
                norm_alias = normalize_name(alias)
                if norm_alias:
                    aliases.add(norm_alias)
    
    # 🔑 PARTI DEL NOME (per nomi composti tipo "Estoril Praia")
    words = team_name.lower().split()
    if len(words) > 1:
        for word in words:
            if len(word) >= 4:  # Solo parole significative
                aliases.add(word)
    
    # Stesso per nome normalizzato
    if normalized:
        words_norm = normalized.split()
        if len(words_norm) > 1:
            for word in words_norm:
                if len(word) >= 4:
                    aliases.add(word)
    
    # Rimuovi stringhe vuote
    aliases.discard("")
    
    return list(aliases)

def teams_match(aliases1: List[str], aliases2: List[str]) -> bool:
    """
    Verifica se due squadre corrispondono usando matching flessibile (SUBSTRING).
    Replica la logica dello scraper: doppia normalizzazione + substring match.
    """
    # Normalizza TUTTI gli alias (come scraper righe 235-248)
    set1_normalized = set()
    for alias in aliases1:
        if alias:  # Skip valori vuoti
            set1_normalized.add(alias.lower())
            normalized = normalize_name(alias)
            if normalized:
                set1_normalized.add(normalized)
    
    set2_normalized = set()
    for alias in aliases2:
        if alias:  # Skip valori vuoti
            set2_normalized.add(alias.lower())
            normalized = normalize_name(alias)
            if normalized:
                set2_normalized.add(normalized)
    
    # Rimuovi stringhe vuote
    set1_normalized.discard("")
    set2_normalized.discard("")
    
    # Check SUBSTRING in entrambe le direzioni (come scraper riga 245)
    for a1 in set1_normalized:
        for a2 in set2_normalized:
            if a1 in a2 or a2 in a1:
                return True
    
    return False

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

    # --- RISOLUZIONE NOMI STILE SCRAPER (TEAMS_CACHE + NORMALIZE) ---

    # 1) Normalizza i nomi in ingresso
    home_key = normalize_name(home_name)
    away_key = normalize_name(away_name)
    h_canon_key = normalize_name(h_canon) if h_canon else ""
    a_canon_key = normalize_name(a_canon) if a_canon else ""

    # 2) Usa TEAMS_CACHE per risalire al nome ufficiale (se possibile)
    h_team_data = TEAMS_CACHE.get(home_key) or TEAMS_CACHE.get(h_canon_key)
    a_team_data = TEAMS_CACHE.get(away_key) or TEAMS_CACHE.get(a_canon_key)

    home_official = h_team_data["official_name"] if h_team_data else home_name
    away_official = a_team_data["official_name"] if a_team_data else away_name

    # 3) Costruisci liste di possibili nomi da usare nella query H2H
    def build_alias_list(team_data, fallback_name, canon_name):
        aliases = []
        # fallback raw + canonical
        if fallback_name:
            aliases.append(normalize_name(fallback_name))
        if canon_name:
            aliases.append(normalize_name(str(canon_name)))
        # nomi da TEAMS_CACHE (campo "names" creato in load_teams_cache)
        if team_data:
            aliases.extend([normalize_name(n) for n in team_data.get("names", [])])
        # dedup e pulizia
        aliases = [x for x in set(aliases) if x]
        return aliases

    possible_names_h = build_alias_list(h_team_data, home_official, h_canon)
    possible_names_a = build_alias_list(a_team_data, away_official, a_canon)


    # 4) Cerca documento H2H usando ID (VELOCE ⚡)
    doc = None

    

    # Trova squadre in db.teams
    home_team_doc = db.teams.find_one({"name": home_official})
   
    away_team_doc = db.teams.find_one({"name": away_official})
   
    if home_team_doc and away_team_doc:
        h_id = home_team_doc['_id']
        a_id = away_team_doc['_id']
        
        
        # Query indicizzata per ID (millisecondi)
        doc = db[SOURCE_COLLECTION].find_one({
            "$or": [
                {"team_a_id": h_id, "team_b_id": a_id},
                {"team_a_id": a_id, "team_b_id": h_id}
            ]
        })

    if not doc:
        return None

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
    
    # Accumulatori Gol Ponderati
    total_goals_scored_h = 0.0
    total_goals_scored_a = 0.0
    total_goals_weight = 0.0

    # 🔑 GENERA ALIAS PER SQUADRE ATTUALI (come scraper)
    home_aliases = get_team_aliases(home_name, h_team_data)
    away_aliases = get_team_aliases(away_name, a_team_data)

    for m in matches:
        if m.get("score") == "-:-" or m.get("winner") == "-": 
            continue
        d_obj = parse_date(m.get("date"))
        if not d_obj or d_obj < cutoff_20y: 
            continue

        # Peso Tempo
        time_weight = 1.0 if d_obj >= cutoff_5y else 0.5

        hist_home_name = m.get("home_team")
        hist_away_name = m.get("away_team")
        hist_home_pos = m.get("home_pos")
        hist_away_pos = m.get("away_pos")
        winner = m.get("winner")
        score = m.get("score", "0:0")

        # 🔍 RISOLVI NOMI STORICI USANDO TEAMS_CACHE
        hist_home_key = normalize_name(hist_home_name)
        hist_away_key = normalize_name(hist_away_name)
        
        hist_home_data = TEAMS_CACHE.get(hist_home_key)
        hist_away_data = TEAMS_CACHE.get(hist_away_key)
        
        # Genera alias per squadre storiche
        hist_home_aliases = get_team_aliases(hist_home_name, hist_home_data)
        hist_away_aliases = get_team_aliases(hist_away_name, hist_away_data)

        # Calcolo punti
        pts_hist_h, pts_hist_a = calculate_match_points(
            winner, hist_home_name, hist_away_name, 
            hist_home_pos, hist_away_pos
        )
        
        # Estrazione Gol
        g_h_hist, g_a_hist = extract_goals_from_score(score)

        # --- MATCHING FLESSIBILE (come scraper) ---
        
        # Verifica se Home Attuale corrisponde a Home Storica
        home_is_hist_home = teams_match(home_aliases, hist_home_aliases)
        
        # Verifica se Home Attuale corrisponde a Away Storica
        home_is_hist_away = teams_match(home_aliases, hist_away_aliases)
        
        if home_is_hist_home:
            # CASO 1: Home Attuale = Home Storica
            w_score_h += pts_hist_h * time_weight
            w_score_a += pts_hist_a * time_weight
            
            total_goals_scored_h += g_h_hist * time_weight
            total_goals_scored_a += g_a_hist * time_weight
            
            if winner == hist_home_name: wins_h += 1
            elif winner == hist_away_name: wins_a += 1
            else: draws += 1
            
        elif home_is_hist_away:
            # CASO 2: Home Attuale = Away Storica (campi invertiti)
            w_score_h += pts_hist_a * time_weight 
            w_score_a += pts_hist_h * time_weight
            
            total_goals_scored_h += g_a_hist * time_weight
            total_goals_scored_a += g_h_hist * time_weight

            if winner == hist_away_name: wins_h += 1
            elif winner == hist_home_name: wins_a += 1
            else: draws += 1
        else:
            # ⚠️ Partita storica non riconosciuta (skip silenzioso)
            continue
            
        total_weight += 3.0 * time_weight
        total_goals_weight += time_weight
        valid_matches += 1


    if valid_matches == 0:
        return {"home_score": 5.0, "away_score": 5.0, "h2h_weight": 0.0, "history_summary": "Nessun dato rilevante"}


    # Scala Assoluta 0-10 (indipendente)
    # Più punti accumulati negli scontri diretti = punteggio più alto
    # Mantiene tutta la logica esistente: peso temporale + difficoltà vittoria

    # Massimo teorico: ~10 vittorie difficili = 10 * 4.5 punti = 45
    MAX_THEORETICAL_SCORE = 45.0

    raw_h = w_score_h
    raw_a = w_score_a

    # Converti punti raw in scala 0-10 assoluta
    norm_h = min(10.0, (raw_h / MAX_THEORETICAL_SCORE) * 10)
    norm_a = min(10.0, (raw_a / MAX_THEORETICAL_SCORE) * 10)

    # Se non ci sono dati, punteggio neutro
    if raw_h == 0 and raw_a == 0:
        norm_h = 5.0
        norm_a = 5.0
    
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
    #test_manuale("Famalicão", "Estoril")  # ← Attiva questa
    
    # --- MODALITÀ PRODUZIONE (ATTIVA) ---
    # Questo lancia l'aggiornamento di TUTTE le partite nel database.
     run_calculator()
