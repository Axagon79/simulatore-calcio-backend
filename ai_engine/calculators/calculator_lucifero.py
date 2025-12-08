import os
import sys
from datetime import datetime

# --- FIX PERCORSI ---
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

# Punta alla collezione NUOVA (quella sicura che abbiamo appena creato)
matches_collection = db['matches_history_betexplorer']

def parse_date(date_str):
    """Converte stringa data in oggetto datetime per ordinamento"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except:
        return datetime.min

def get_lucifero_score(team_name):
    """
    Calcola la POTENZA LUCIFERO (Forma Recente).
    Max Punteggio = 13 (se la forma è 100%).
    Legge dalla collezione 'matches_history_betexplorer'.
    """
    
    # 1. Cerca squadra (per nome esatto, BetExplorer è standard)
    # Nota: Se i nomi differiscono (es "Inter" vs "Inter Milan"), servirebbe un gestore alias.
    # Per ora proviamo con il nome diretto.
    
    query = {
        "$or": [
            {"homeTeam": team_name},
            {"awayTeam": team_name}
        ]
    }
    
    all_matches = list(matches_collection.find(query))
    
    if not all_matches:
        # Tentativo con Alias (se necessario, implementare logica alias qui)
        # print(f"   ⚠️ Lucifero: Nessuna partita trovata per {team_name}")
        return 0.0

    # 2. Ordina per data (dalla più recente alla più vecchia)
    # Fondamentale: scartare le partite future (se ce ne fossero) o senza data
    valid_matches = [m for m in all_matches if m.get('date') != "Unknown"]
    valid_matches.sort(key=lambda x: parse_date(x['date']), reverse=True)
    
    # Prende le ultime 6
    last_6 = valid_matches[:6]
    
    if not last_6: return 0.0

    # 3. Calcolo Punti
    weights = [6, 5, 4, 3, 2, 1] # Pesi decrescenti (la più recente pesa 6)
    total_score = 0
    max_score = 0 # Calcoliamo il max possibile in base a quante partite abbiamo (magari ne ha giocate solo 3)
    
    print(f"\n🔥 ANALISI LUCIFERO: {team_name}")
    
    for i, match in enumerate(last_6):
        weight = weights[i]
        max_score += (3 * weight) # 3 punti vittoria * peso
        
        # Chi ha vinto?
        res = match['result'] # '1', 'X', '2'
        is_home = (match['homeTeam'] == team_name)
        
        punti_match = 0
        esito = "S"
        
        if res == 'X':
            punti_match = 1
            esito = "P"
        elif (is_home and res == '1') or (not is_home and res == '2'):
            punti_match = 3
            esito = "V"
        else:
            punti_match = 0
            esito = "S"
            
        score_partita = punti_match * weight
        total_score += score_partita
        
        print(f"   {i+1}° ({match['date']}) vs {match['awayTeam'] if is_home else match['homeTeam']}: {esito} -> {punti_match}pt x {weight} = {score_partita}")

    # 4. Normalizzazione su scala 25
    if max_score == 0: return 0.0
    forma_pct = (total_score / max_score)
    lucifero_value = forma_pct * 25.0 # Max 25 punti
    print(f" ⚡ POTENZA LUCIFERO: {lucifero_value:.2f}/25.0")
    return round(lucifero_value, 2)

if __name__ == "__main__":
    # Test
    get_lucifero_score("Trento")
    get_lucifero_score("Cittadella")
