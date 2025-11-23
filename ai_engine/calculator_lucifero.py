import pymongo
import os
from dotenv import load_dotenv
from datetime import datetime

# 1. CONFIGURAZIONE MONGODB
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', '.env')
load_dotenv(env_path)

MONGO_URI = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
client = pymongo.MongoClient(MONGO_URI)
db = client.get_database()
matches_collection = db['matches_history']

def parse_date(date_str):
    """Converte la data stringa in oggetto data per ordinare"""
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return datetime.min

def get_lucifero_score(team_name):
    """
    Calcola la POTENZA LUCIFERO (Forma) di una squadra.
    Max Punteggio = 13 (se la forma è 100%).
    """
    
    # 1. Cerca tutte le partite della squadra (Casa o Fuori)
    query = {
        "$or": [
            {"homeTeam": team_name},
            {"awayTeam": team_name}
        ]
    }
    
    all_matches = list(matches_collection.find(query))
    
    # 2. Ordina per data (dalla più recente alla più vecchia)
    all_matches.sort(key=lambda x: parse_date(x['date']), reverse=True)
    
    # Prende le ultime 6
    last_6 = all_matches[:6]
    
    if not last_6:
        print(f"⚠️ Nessuna partita trovata per {team_name}")
        return 0

    # 3. Calcolo Punti Lucifero
    weights = [6, 5, 4, 3, 2, 1] # Pesi decrescenti
    total_score = 0
    max_score = 63 # Punteggio massimo possibile (tutte vittorie)
    
    print(f"\n🔍 ANALISI LUCIFERO: {team_name}")
    
    for i, match in enumerate(last_6):
        weight = weights[i]
        
        # Chi ha vinto?
        result = match['result'] # '1', 'X', '2'
        is_home = (match['homeTeam'] == team_name)
        
        # Normalizza i risultati football-data (H,D,A) in 1,X,2
        if result == 'H': result = '1'
        if result == 'A': result = '2'
        if result == 'D': result = 'X'
        
        punti_match = 0
        esito = "S"
        
        if result == 'X':
            punti_match = 1
            esito = "P"
        elif (is_home and result == '1') or (not is_home and result == '2'):
            punti_match = 3
            esito = "V"
        else:
            punti_match = 0
            esito = "S"
            
        score_partita = punti_match * weight
        total_score += score_partita
        
        print(f"   {i+1}° Partita ({match['date']}): {esito} -> {punti_match}pt x {weight} = {score_partita}")

    # 4. Calcolo Finale
    forma_percentuale = (total_score / max_score) * 100
    
    # Calcolo Potenza su scala 13 (Peso Lucifero)
    potenza_reale = (forma_percentuale / 100) * 13
    
    print(f"   --------------------------------")
    print(f"   🔥 FORMA: {forma_percentuale:.2f}%")
    print(f"   ⚡ POTENZA LUCIFERO: {potenza_reale:.2f} (su 13 max)")
    print(f"   --------------------------------")
    
    return potenza_reale

# --- TEST PROVA ---
if __name__ == "__main__":
    # Scrivi qui una squadra che vuoi testare
    squadra = "Juventus" 
    get_lucifero_score(squadra)
