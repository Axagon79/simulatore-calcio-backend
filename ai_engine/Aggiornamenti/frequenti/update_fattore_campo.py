import os
import sys
from tqdm import tqdm # Barra di caricamento
from bson import ObjectId # Necessario per gestire gli ID di MongoDB

# --- CONFIGURAZIONE PERCORSI ---
# Permette di trovare il file config.py nella cartella superiore
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

try:
    from config import db
except ImportError:
    print("⚠️ Config non trovato. Assicurati di lanciare il file dalla cartella corretta.")
    db = None

# CONFIGURAZIONE COLLEZIONI
teams_collection = db['teams'] if db is not None else None
h2h_collection = db['h2h_by_round'] if db is not None else None

def get_league_averages(league_name):
    """
    Calcola la media punti casalinga e in trasferta dell'intero campionato.
    """
    if teams_collection is None: return 1.60, 1.10

    # Cerca tutte le squadre di quel campionato
    teams = list(teams_collection.find({"ranking.league": league_name}))

    if not teams:
        # Fallback: ricerca parziale
        teams = list(teams_collection.find({"ranking.league": {"$regex": league_name, "$options": "i"}}))

    if not teams:
        return 1.60, 1.10 

    total_home_ppg = 0
    total_away_ppg = 0
    count = 0

    for team in teams:
        rank = team.get('ranking', {})
        
        # Statistiche Casa
        h_pts = rank.get('homePoints', 0)
        h_played = rank.get('homeStats', {}).get('played', 0)
        
        # Statistiche Fuori
        a_pts = rank.get('awayPoints', 0)
        a_played = rank.get('awayStats', {}).get('played', 0)

        if h_played > 0:
            total_home_ppg += (h_pts / h_played)
        
        if a_played > 0:
            total_away_ppg += (a_pts / a_played)
            
        if h_played > 0 or a_played > 0:
            count += 1

    if count == 0: return 1.60, 1.10

    return total_home_ppg / count, total_away_ppg / count

def calculate_field_factor(home_id, home_name, away_id, away_name, league_name=None):
    """
    Restituisce il punteggio Fattore Campo GREZZO (0-7).
    Priorità di ricerca: ID > Nome.
    """
    default_res = 3.5, 3.5 # Neutro
    
    if teams_collection is None: return default_res

    # 1. FUNZIONE CERCA SQUADRA (Potenziata con ID)
    def find_team(t_id, t_name):
        # A. Cerca per ID (Metodo Sicuro al 100%)
        if t_id:
            # Assicuriamoci che sia un ObjectId valido
            if isinstance(t_id, str) and ObjectId.is_valid(t_id):
                res = teams_collection.find_one({"_id": ObjectId(t_id)})
                if res: return res
            elif isinstance(t_id, ObjectId):
                res = teams_collection.find_one({"_id": t_id})
                if res: return res

        # B. Fallback per Nome (se ID non trovato o non fornito)
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


# --- IL "BRACCIO": Funzione che aggiorna il Database ---
def run_updater():
    print("🚀 Avvio Update Fattore Campo (Ricerca per ID + Nome)...")
    
    if h2h_collection is None:
        print("❌ Errore: Impossibile connettersi alla collezione h2h_by_round")
        return

    # Prendi tutte le giornate
    rounds = list(h2h_collection.find({}))
    total_updated = 0

    for r in tqdm(rounds, desc="Elaborazione Giornate"):
        modified = False
        matches = r.get("matches", [])
        
        for m in matches:
            # 1. Recupera ID e Nomi dalla partita
            # Nota: Cerchiamo chiavi comuni per gli ID (home_id, home_team_id, id_home, etc.)
            h_id = m.get("home_team_id") or m.get("home_id") or m.get("id_home")
            a_id = m.get("away_team_id") or m.get("away_id") or m.get("id_away")
            
            h_name = m.get("home")
            a_name = m.get("away")

            # 2. Chiama il calcolatore (Restituisce 0-7)
            raw_h, raw_a = calculate_field_factor(h_id, h_name, a_id, a_name)
            
            # 3. Normalizza in Percentuale (0-100) per il Frontend
            # Formula: (Voto / 7) * 100
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
            
            # Se esiste già il blocco fattore_campo, aggiornalo, altrimenti crealo
            existing_fattore_campo = existing_h2h.get("fattore_campo", {})
            existing_fattore_campo.update(nuovo_dato)
            
            existing_h2h["fattore_campo"] = existing_fattore_campo
            
            # Salva in memoria
            m["h2h_data"] = existing_h2h
            modified = True
            total_updated += 1

        # 6. Salva su DB se la giornata è stata modificata
        if modified:
            h2h_collection.update_one(
                {"_id": r["_id"]}, 
                {"$set": {"matches": matches}}
            )

    print(f"✅ Completato! Aggiornate {total_updated} partite con successo.")
    
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