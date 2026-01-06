import os
import sys
from datetime import datetime

# --- FIX PERCORSI ---
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

# Punta alla collezione NUOVA (quella sicura che abbiamo appena creato)
h2h_collection = db['h2h_by_round']

def parse_date(date_str):
    """Converte stringa data in oggetto datetime per ordinamento"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except:
        return datetime.min

# // modificato per: logica bulk
def get_lucifero_score(team_name, bulk_cache=None):
    """
    Calcola la POTENZA LUCIFERO (Forma Recente).
    Max Punteggio = 25 (se la forma è 100%).
    Legge dalla collezione 'h2h_by_round' (organizzata per giornate).
    Supporta Bulk Cache per evitare query ripetitive.
    """
    
    # 1. Recupero round (Priorità al Bulk Cache per performance Engine)
    if bulk_cache and "ALL_ROUNDS" in bulk_cache:
        all_rounds = bulk_cache["ALL_ROUNDS"]
    else:
        # Fallback originale su DB
        # Prendi le giornate ordinate dalla più recente (last_updated decrescente)
        all_rounds = list(h2h_collection.find({}).sort('last_updated', -1))
    
    # 2. Cerca gli ultimi 6 MATCH della squadra (non giornate, ma partite!)
    team_matches = []
    
    for round_doc in all_rounds:
        # Scorri i match di questa giornata
        for match in round_doc.get('matches', []):
            if match.get('status') == 'Finished':
                # È un match della nostra squadra?
                if match.get('home') == team_name or match.get('away') == team_name:
                    # Aggiungi anche la data dalla giornata per ordinamento
                    match['_round_date'] = round_doc.get('last_updated')
                    team_matches.append(match)
                    
                    # Hai già 6 match? Stop
                    if len(team_matches) >= 6:
                        break
        
        if len(team_matches) >= 6:
            break
    
    if not team_matches:
        return 0.0
    
    # Prende le ultime 6 (già in ordine perché abbiamo scorso dalla giornata più recente)
    last_6 = team_matches[:6]
    
    if not last_6: return 0.0

    # 3. Calcolo Punti (Preservato riga 54)
    weights = [6, 5, 4, 3, 2, 1] # Pesi decrescenti (la più recente pesa 6)
    total_score = 0
    max_score = 0 # Calcoliamo il max possibile in base a quante partite abbiamo
    
    print(f"\n🔥 ANALISI LUCIFERO: {team_name}")
    
    for i, match in enumerate(last_6):
        weight = weights[i]
        max_score += (3 * weight) # 3 punti vittoria * peso
        
        # Chi ha vinto?
        score = match.get('real_score', '0:0').split(':')
        home_goals = int(score[0])
        away_goals = int(score[1])
        
        is_home = (match.get('home') == team_name)
        
        punti_match = 0
        esito = "S"
        
        if home_goals == away_goals:
            punti_match = 1
            esito = "P"
        elif (is_home and home_goals > away_goals) or (not is_home and away_goals > home_goals):
            punti_match = 3
            esito = "V"
        else:
            punti_match = 0
            esito = "S"
            
        score_partita = punti_match * weight
        total_score += score_partita
        
        opponent = match.get('away') if is_home else match.get('home')
        date_str = match.get('date_obj', 'N/A')
        print(f"   {i+1}° ({date_str}) vs {opponent}: {esito} ({match.get('real_score')}) -> {punti_match}pt x {weight} = {score_partita}")

    # 4. Normalizzazione su scala 25
    if max_score == 0: return 0.0
    forma_pct = (total_score / max_score)
    lucifero_value = forma_pct * 25.0 # Max 25 punti
    print(f" ⚡ POTENZA LUCIFERO: {lucifero_value:.2f}/25.0")
    return round(lucifero_value, 2)

if __name__ == "__main__":
    # Test
    get_lucifero_score("Getafe CF")
    get_lucifero_score("Rayo Vallecano")