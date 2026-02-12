import os
import sys
import re
from datetime import datetime
import dateutil.parser
from tqdm import tqdm # Barra di caricamento
from bson import ObjectId # Necessario per gestire gli ID di MongoDB

# --- CONFIGURAZIONE PERCORSI ---
# Risale fino alla root del progetto (3 livelli: frequenti -> Aggiornamenti -> ai_engine -> root)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)

try:
    from config import db
except ImportError:
    print("⚠️ Config non trovato. Assicurati di lanciare il file dalla cartella corretta.")
    db = None

# CONFIGURAZIONE COLLEZIONI
teams_collection = db['teams'] if db is not None else None
h2h_collection = db['h2h_by_round'] if db is not None else None

# --- CACHE TEAMS (popolata da run_updater per performance) ---
_teams_by_id = None       # {str(ObjectId): team_doc}
_teams_by_name = None     # {lowercase_name: team_doc}
_teams_by_league = None   # {league_name: [team_doc, ...]}
_league_avg_cache = {}    # {league_name: (avg_home, avg_away)}

def get_league_averages(league_name):
    """
    Calcola la media punti casalinga e in trasferta dell'intero campionato.
    Usa cache se disponibile, altrimenti query DB.
    """
    # Check cache
    if league_name in _league_avg_cache:
        return _league_avg_cache[league_name]

    # Trova teams: da cache o da DB
    if _teams_by_league is not None:
        teams = _teams_by_league.get(league_name, [])
        if not teams:
            # Fallback: ricerca parziale tra le chiavi
            ln = league_name.lower()
            for key, val in _teams_by_league.items():
                if ln in key.lower():
                    teams = val
                    break
    else:
        if teams_collection is None: return 1.60, 1.10
        teams = list(teams_collection.find({"ranking.league": league_name}))
        if not teams:
            teams = list(teams_collection.find({"ranking.league": {"$regex": league_name, "$options": "i"}}))

    if not teams:
        return 1.60, 1.10

    total_home_ppg = 0
    total_away_ppg = 0
    count = 0

    for team in teams:
        rank = team.get('ranking', {})
        h_pts = rank.get('homePoints', 0)
        h_played = rank.get('homeStats', {}).get('played', 0)
        a_pts = rank.get('awayPoints', 0)
        a_played = rank.get('awayStats', {}).get('played', 0)

        if h_played > 0:
            total_home_ppg += (h_pts / h_played)
        if a_played > 0:
            total_away_ppg += (a_pts / a_played)
        if h_played > 0 or a_played > 0:
            count += 1

    if count == 0: return 1.60, 1.10

    result = total_home_ppg / count, total_away_ppg / count
    _league_avg_cache[league_name] = result
    return result

def calculate_field_factor(home_id, home_name, away_id, away_name, league_name=None):
    """
    Restituisce il punteggio Fattore Campo GREZZO (0-7).
    Priorità di ricerca: ID > Nome.
    """
    default_res = 3.5, 3.5 # Neutro
    
    if teams_collection is None: return default_res

    # 1. FUNZIONE CERCA SQUADRA (Cache > ID > Nome)
    def find_team(t_id, t_name):
        # --- MODALITÀ CACHE (veloce) ---
        if _teams_by_id is not None:
            if t_id:
                tid_str = str(t_id)
                if tid_str in _teams_by_id:
                    return _teams_by_id[tid_str]
            if t_name:
                return _teams_by_name.get(t_name.lower())
            return None

        # --- MODALITÀ DB (fallback per test_manuale) ---
        if t_id:
            if isinstance(t_id, str) and ObjectId.is_valid(t_id):
                res = teams_collection.find_one({"_id": ObjectId(t_id)})
                if res: return res
            elif isinstance(t_id, ObjectId):
                res = teams_collection.find_one({"_id": t_id})
                if res: return res

        return teams_collection.find_one({
            "$or": [
                {"name": t_name},
                {"aliases": t_name},
                {"aliases.soccerstats": t_name},
                {"official_name": t_name}
            ]
        })

    # Trova le squadre
    home_team = find_team(home_id, home_name)
    away_team = find_team(away_id, away_name)

    if not home_team or not away_team:
        # Se non trovi le squadre nemmeno col nome, ritorna neutro
        return default_res

    # 2. DETERMINA LEGA
    if not league_name:
        league_name = home_team.get("ranking", {}).get("league", "Unknown")

    # 3. OTTIENI MEDIE CAMPIONATO
    avg_h_league, avg_a_league = get_league_averages(league_name)

    # Protezione matematica
    if avg_h_league < 0.1: avg_h_league = 1.5
    if avg_a_league < 0.1: avg_a_league = 1.0

    # --- CALCOLO CASA ---
    h_rank = home_team.get('ranking', {})
    h_pts = h_rank.get('homePoints', 0)
    h_played = h_rank.get('homeStats', {}).get('played', 0)
    
    if h_played > 0:
        home_ppg = h_pts / h_played
    else:
        home_ppg = avg_h_league

    home_ratio = home_ppg / avg_h_league
    home_score = (home_ratio * 3.5) + 0.25
    if home_score > 7.0: home_score = 7.0

    # --- CALCOLO OSPITE ---
    a_rank = away_team.get('ranking', {})
    a_pts = a_rank.get('awayPoints', 0)
    a_played = a_rank.get('awayStats', {}).get('played', 0)
    
    if a_played > 0:
        away_ppg = a_pts / a_played
    else:
        away_ppg = avg_a_league

    away_ratio = away_ppg / avg_a_league
    away_score = away_ratio * 3.5
    if away_score > 7.0: away_score = 7.0

    return round(home_score, 2), round(away_score, 2)


# --- FUNZIONI PER TROVARE LE GIORNATE MIRATE (Prec/Attuale/Succ) ---
# Copiato da db_updater_bvs.py

def get_round_number(doc):
    """Estrae il numero di giornata dall'ID documento."""
    name = doc.get('_id', '') or doc.get('round_name', '')
    match = re.search(r'(\d+)', str(name))
    return int(match.group(1)) if match else 999

def find_target_rounds(league_docs):
    """Trova le 3 giornate da aggiornare: precedente, attuale, successiva."""
    if not league_docs: return []
    sorted_docs = sorted(league_docs, key=get_round_number)
    now = datetime.now()
    closest_index = -1
    min_diff = float('inf')
    for i, doc in enumerate(sorted_docs):
        dates = []
        for m in doc.get('matches', []):
            d_raw = m.get('date_obj') or m.get('date')
            try:
                if d_raw:
                    d = d_raw if isinstance(d_raw, datetime) else dateutil.parser.parse(d_raw)
                    dates.append(d.replace(tzinfo=None))
            except: pass
        if dates:
            avg_date = sum([d.timestamp() for d in dates]) / len(dates)
            diff = abs(now.timestamp() - avg_date)
            if diff < min_diff: min_diff = diff; closest_index = i
    if closest_index == -1: return []
    start_idx = max(0, closest_index - 1)
    end_idx = min(len(sorted_docs), closest_index + 2)
    return sorted_docs[start_idx:end_idx]


# --- IL "BRACCIO": Funzione che aggiorna il Database ---
def run_updater():
    global _teams_by_id, _teams_by_name, _teams_by_league, _league_avg_cache
    print("🚀 Avvio Update Fattore Campo (MIRATO: Prec/Attuale/Succ)...")

    if h2h_collection is None:
        print("❌ Errore: Impossibile connettersi alla collezione h2h_by_round")
        return

    # 0. Cache: carica tutti i teams una volta sola
    print("📦 Caricamento teams in memoria...")
    all_teams_list = list(teams_collection.find({}))
    _teams_by_id = {}
    _teams_by_name = {}
    _teams_by_league = {}
    _league_avg_cache = {}

    for t in all_teams_list:
        # Indice per ID
        _teams_by_id[str(t["_id"])] = t
        # Indice per nome
        name = t.get("name")
        if name:
            _teams_by_name[name.lower()] = t
        official = t.get("official_name")
        if official:
            _teams_by_name[official.lower()] = t
        # Indice per aliases
        aliases = t.get("aliases")
        if isinstance(aliases, list):
            for a in aliases:
                if isinstance(a, str):
                    _teams_by_name[a.lower()] = t
        elif isinstance(aliases, dict):
            for val in aliases.values():
                if isinstance(val, str):
                    _teams_by_name[val.lower()] = t
        elif isinstance(aliases, str):
            _teams_by_name[aliases.lower()] = t
        # Indice per lega
        league = t.get("ranking", {}).get("league")
        if league:
            _teams_by_league.setdefault(league, []).append(t)

    print(f"   {len(all_teams_list)} teams → {len(_teams_by_name)} nomi indicizzati, {len(_teams_by_league)} leghe")

    # 1. Trova tutti i campionati distinti
    all_leagues = h2h_collection.distinct("league")
    print(f"📋 Campionati trovati: {len(all_leagues)}")

    total_updated = 0
    total_rounds = 0

    for league in tqdm(all_leagues, desc="Campionati"):
        # 2. Prendi i round di questo campionato
        league_docs = list(h2h_collection.find({"league": league}))

        # 3. Trova le 3 giornate mirate
        target_rounds = find_target_rounds(league_docs)

        if not target_rounds:
            continue

        round_nums = [get_round_number(d) for d in target_rounds]
        print(f"\n  🏆 {league}: giornate {round_nums}")
        total_rounds += len(target_rounds)

        for r in target_rounds:
            modified = False
            matches = r.get("matches", [])

            for m in matches:
                # 1. Recupera ID e Nomi dalla partita
                h_id = m.get("home_team_id") or m.get("home_id") or m.get("id_home")
                a_id = m.get("away_team_id") or m.get("away_id") or m.get("id_away")

                h_name = m.get("home")
                a_name = m.get("away")

                # 2. Chiama il calcolatore (Restituisce 0-7)
                raw_h, raw_a = calculate_field_factor(h_id, h_name, a_id, a_name)

                # 3. Normalizza in Percentuale (0-100) per il Frontend
                pct_h = int((raw_h / 7.0) * 100)
                pct_a = int((raw_a / 7.0) * 100)

                # Capping di sicurezza (Min 10 - Max 99)
                pct_h = max(10, min(99, pct_h))
                pct_a = max(10, min(99, pct_a))

                # 4. Crea il pacchetto dati
                nuovo_dato = {
                    "field_home": pct_h,
                    "field_away": pct_a
                }

                # 5. Iniezione nel campo "fattore_campo"
                existing_h2h = m.get("h2h_data", {})
                if not isinstance(existing_h2h, dict): existing_h2h = {}

                existing_fattore_campo = existing_h2h.get("fattore_campo", {})
                existing_fattore_campo.update(nuovo_dato)

                existing_h2h["fattore_campo"] = existing_fattore_campo

                m["h2h_data"] = existing_h2h
                modified = True
                total_updated += 1

            # 6. Salva su DB se la giornata è stata modificata
            if modified:
                h2h_collection.update_one(
                    {"_id": r["_id"]},
                    {"$set": {"matches": matches}}
                )

    print(f"\n✅ Completato! Processati {total_rounds} round, aggiornate {total_updated} partite.")
    
# --- FUNZIONE DI TEST MANUALE ---
def test_manuale(squadra_casa, squadra_ospite):
    print(f"\n🧪 TEST RAPIDO: {squadra_casa} vs {squadra_ospite}")
    
    # Chiamiamo il calcolatore passando None come ID (usiamo solo i nomi per il test)
    raw_h, raw_a = calculate_field_factor(None, squadra_casa, None, squadra_ospite)
    
    # Simuliamo il calcolo percentuale
    pct_h = int((raw_h / 7.0) * 100)
    pct_a = int((raw_a / 7.0) * 100)
    
    print(f"   📊 Grezzi (0-7):  Casa {raw_h}  |  Ospite {raw_a}")
    print(f"   🎨 Frontend (%):  Casa {pct_h}%  |  Ospite {pct_a}%")
    print("---------------------------------------------------")

if __name__ == "__main__":
    # --- MODALITÀ A: TEST MANUALE (Togli il # per usare) ---
    #test_manuale("Guimaraes", "Inter")
    # test_manuale("Juventus", "Milan")

    # --- MODALITÀ B: AGGIORNAMENTO COMPLETO DB (Usa questa per la produzione) ---
    run_updater()