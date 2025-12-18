import os
import sys
import math
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import db

# Nomi delle collezioni
COLLECTION_HISTORY = "matches_history_betexplorer"
COLLECTION_TEAMS = "teams"

# Manteniamo questa funzione per non rompere il codice sotto che la richiama
def connect_db():
    return db

def get_team_aliases(db, team_name):
    """Cerca gli alias della squadra per trovarla nello storico anche se il nome è diverso."""
    team = db[COLLECTION_TEAMS].find_one({"name": team_name})
    aliases = [team_name]
    if team:
        # Aggiungi alias da oggetto o lista
        if isinstance(team.get('aliases'), list):
            aliases.extend(team['aliases'])
        elif isinstance(team.get('aliases'), dict):
            aliases.extend(team['aliases'].values())
    return [a.lower() for a in aliases] # Tutto minuscolo per confronti sicuri

def get_team_league(db, team_name):
    """Recupera il campionato della squadra da teams (per ricerca intelligente)."""
    team = db[COLLECTION_TEAMS].find_one({"name": team_name})
    return team.get('league') if team else None

def calculate_reliability(team_name, specific_league=None):
    """
    Calcola l'indice di affidabilità (0-10) basandosi su media e deviazione standard.
    Ricerca intelligente a 3 livelli:
    1. Lega specifica + nome esatto
    2. Lega specifica + alias  
    3. Globale con alias (fallback)
    Logica:
    - Sei affidabile se vinci da favorita e perdi da sfavorita.
    - Sei inaffidabile se perdi da favorita (delusione) o vinci da sfavorita (sorpresa).
    """
    history_col = db[COLLECTION_HISTORY]
    aliases = get_team_aliases(db, team_name)
    
    # Determina lega target (priorità: specific_league → league da teams → nessuna)
    target_league = specific_league or get_team_league(db, team_name)
    
    matches = []
    
    # LIVELLO 1: Lega + Nome Esatto (più preciso)
    if target_league:
        query_l1 = {
            "league": target_league,
            "$or": [{"homeTeam": team_name}, {"awayTeam": team_name}]
        }
        matches = list(history_col.find(query_l1))
    
    # LIVELLO 2: Lega + Alias (se L1 non trova nulla)
    if not matches and target_league:
        regex_pattern = "|".join([f"^{a}$" for a in aliases])
        query_l2 = {
            "league": target_league,
            "$or": [
                {"homeTeam": {"$regex": regex_pattern, "$options": "i"}},
                {"awayTeam": {"$regex": regex_pattern, "$options": "i"}}
            ]
        }
        matches = list(history_col.find(query_l2))
    
    # LIVELLO 3: Globale con Alias (fallback disperato)
    if not matches:
        regex_pattern = "|".join([f"^{a}$" for a in aliases])
        matches = list(history_col.find({
            "$or": [
                {"homeTeam": {"$regex": regex_pattern, "$options": "i"}},
                {"awayTeam": {"$regex": regex_pattern, "$options": "i"}}
            ]
        }))

    if not matches:
        return 5.0 # Valore neutro se nessuna partita trovata

    # --- NUOVA LOGICA: Lista dei colpi per partita ---
    scores_list = []
    valid_matches = 0

    scores_list = []
    valid_matches = 0

    for m in matches:
        # Adattamento nomi chiavi (homeTeam, homeGoals...)
        h_name_db = m.get('homeTeam', '')
        
        # Verifica se è in casa usando i nomi corretti
        is_home = h_name_db.lower() in [a.lower() for a in aliases] or team_name.lower() in h_name_db.lower()

        # Dati partita
        gh = m.get('homeGoals')
        ga = m.get('awayGoals')
        o1 = m.get('odds_1')
        o2 = m.get('odds_2')

        if not o1 or not o2: continue

        try:
            gh = float(gh)
            ga = float(ga)
            o1 = float(o1)
            o2 = float(o2)
        except (ValueError, TypeError):
            continue

        # Determina Risultato per la squadra
        if is_home:
            my_odds = o1
            won = gh > ga
            lost = gh < ga
            draw = gh == ga
        else:
            my_odds = o2
            won = ga > gh
            lost = ga < gh
            draw = gh == ga

        # --- LOGICA PUNTEGGIO (IDENTICA ALLA VECCHIA) ---
        colpo = 0.0
        # 1. SQUADRA FAVORITA (Quota < 2.00)
        if my_odds <= 2.00:
            if won:
                colpo = 0.8
            elif draw:
                colpo = -0.5
            elif lost:
                colpo = -1.2

        # 2. SQUADRA SFAVORITA (Quota > 3.00)
        elif my_odds >= 3.00:
            if lost:
                colpo = 0.2
            elif won:
                colpo = -0.5
            elif draw:
                colpo = -0.3

        # 3. PARTITA EQUILIBRATA (2.00 < Quota < 3.00)
        else:
            if won: colpo = 0.7
            if draw: colpo = -0.70
            if lost: colpo = -1.40

        scores_list.append(colpo)
        valid_matches += 1
        
        # DEBUG: Quanti match validi usa il calcolo reale?
        if valid_matches <= 5:  # Stampa solo i primi 5
            

            if not scores_list:
                return 5.0

    # --- NUOVA NORMALIZZAZIONE LINEARE (Media + Deviazione Standard) ---
    # 1. Media dei colpi
    avg_score = sum(scores_list) / len(scores_list)
    
    # 2. Deviazione standard (misura irregolarità)
    variance = sum((x - avg_score) ** 2 for x in scores_list) / len(scores_list)
    std_dev = math.sqrt(variance)
    
    # 3. Formula lineare finale
    # Base 5.0 + effetto media (x4) - penalità irregolarità (x1.2)
    final_score = 5.0 + (avg_score * 4.0) - (std_dev * 1.2)

    # Cap 0-10
    if final_score > 10: final_score = 10.0
    if final_score < 0: final_score = 0.0

    # Correzione per poche partite (Regressione verso la media) - IDENTICA ALLA VECCHIA
    if valid_matches < 5:
        # Regressione proporzionale ai match
        weight = valid_matches / 5.0  # 0-1
        final_score = final_score * weight + 5.0 * (1 - weight)

    return round(final_score, 2)

# TEST RAPIDO
# --- DEBUG DIAGNOSTICO ---
if __name__ == "__main__":
    from config import db # Assicuriamoci di avere il db
    
    t_name = "Inter" # O metti la squadra che stai cercando di testare
    
    print(f"\n🔍 DIAGNOSTICA PER: '{t_name}'")
    
    # 1. CONTROLLO CONNESSIONE E COLLEZIONE
    try:
        total_matches = db[COLLECTION_HISTORY].count_documents({})
        print(f"✅ Connessione OK. Totale partite nel DB ({COLLECTION_HISTORY}): {total_matches}")
    except Exception as e:
        print(f"❌ ERRORE CONNESSIONE: {e}")
        sys.exit()

    if total_matches == 0:
        print("⚠️ ATTENZIONE: La collezione 'matches_history' è VUOTA!")
    else:
        # 2. CONTROLLO NOMI CAMPI
        # Stampiamo una partita a caso per vedere come sono scritti i nomi delle squadre
        sample = db[COLLECTION_HISTORY].find_one()
        print(f"📋 Esempio struttura dati (primo record trovato):")
        print(f"   Casa: '{sample.get('homeTeam')}'") 
        print(f"   Fuori: '{sample.get('awayTeam')}'")

        # 3. CONTROLLO RICERCA SPECIFICA (usa la STESSA logica del calcolo reale)
        aliases = get_team_aliases(db, t_name)
        print(f"🔗 Alias trovati per '{t_name}': {aliases}")
        
        # Simuliamo la ricerca intelligente del calcolo reale
        league = get_team_league(db, t_name)
        print(f"🏆 Lega rilevata: '{league}'")
        
        # Usa la query Livello 1 (nome esatto + lega)
        real_query = {"$or": [{"homeTeam": t_name}, {"awayTeam": t_name}]}
        if league:
            real_query["league"] = league
            
        real_found = list(db[COLLECTION_HISTORY].find(real_query))
        print(f"🕵️ Partite usate dal CALCOLO: {len(real_found)}")

        if len(real_found) == 0:
            print("❌ NESSUNA PARTITA TROVATA. Possibili cause:")
            print("   1. Il nome nel DB è diverso (es. 'Internazionale' vs 'Inter')")
            print("   2. La Regex è troppo stretta")
            print("   3. Stai puntando al DB sbagliato nel file .env")
        else:
            val = calculate_reliability(t_name)
            print(f"✅ Calcolo funzionante! Affidabilità: {val}")
