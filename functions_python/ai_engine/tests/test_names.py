import os
import sys

# Aggiungi la cartella principale al path di sistema
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ora l'import dovrebbe funzionare
from config import db


# Collezioni da interrogare
teams_col = db['teams']                  # Per Rating, Valore Rosa, Motivazione
stats_col = db['team_seasonal_stats']    # Per Volume FBRef
h2h_col = db['h2h_by_round']             # Per H2H
history_col = db['matches_history']      # Per Affidabilità
bet_col = db['matches_history_betexplorer'] # Per Lucifero (Forma)

def check_team_data(team_name):
    print(f"\n🔎 INDAGINE DATI PER: '{team_name}'")
    print("="*60)

    # 1. TEAMS COLLECTION (Il cuore: Rating, Rosa, Motivazione)
    # Cerchiamo per nome esatto o alias
    team_doc = teams_col.find_one({"$or": [{"name": team_name}, {"aliases": team_name}]})
    
    if team_doc:
        print(f"✅ TEAMS DB: Trovato! -> Nome Ufficiale: '{team_doc.get('name')}'")
        # Controlliamo i campi critici
        stats = team_doc.get('stats', {})
        print(f"   - Rating (rating_5_25): {team_doc.get('rating_5_25', 'ASSENTE')}")
        print(f"   - Valore Rosa (strengthScore09): {stats.get('strengthScore09', 'ASSENTE')}")
        print(f"   - Motivazione: {stats.get('motivation', 'ASSENTE')}")
        
        # Controlliamo Attacco/Difesa (che sono nel campo 'scores')
        scores = team_doc.get('scores', {})
        if scores:
            print(f"   - Attacco Casa: {scores.get('attack_home', 'ASSENTE')}")
            print(f"   - Difesa Casa: {scores.get('defense_home', 'ASSENTE')}")
        else:
            print(f"   ❌ SCORES (Att/Dif): Campo 'scores' ASSENTE nel documento!")
            
    else:
        print(f"❌ TEAMS DB: NESSUNA TRACCIA di '{team_name}' (né nome né alias)")

    print("-" * 60)

    # 2. LUCIFERO (Forma) - Cerca in matches_history_betexplorer
    # Lucifero cerca per 'homeTeam' o 'awayTeam'
    luc_match = bet_col.find_one({"$or": [{"homeTeam": team_name}, {"awayTeam": team_name}]})
    if luc_match:
        print(f"✅ LUCIFERO DB: Trovata almeno una partita (es. vs {luc_match.get('awayTeam')})")
    else:
        print(f"❌ LUCIFERO DB: Nessuna partita trovata con nome '{team_name}'")

    print("-" * 60)

    # 3. STATS (FBRef Volume)
    stats_doc = stats_col.find_one({"team": team_name})
    if stats_doc:
        print(f"✅ STATS DB: Trovato! Volume: {stats_doc.get('total_volume_avg', 'N/A')}")
    else:
        # Proviamo a vedere se esiste qualcosa di simile
        print(f"❌ STATS DB: Non trovato '{team_name}'.")
        # Ricerca parziale per suggerire
        suggest = stats_col.find_one({"team": {"$regex": team_name, "$options": "i"}})
        if suggest:
            print(f"   (Suggerimento: Forse intendevi '{suggest['team']}'?)")

if __name__ == "__main__":
    check_team_data("Milan")
    check_team_data("AC Milan")
    check_team_data("Sassuolo")
