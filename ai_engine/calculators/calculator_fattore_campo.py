import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

# CONFIGURAZIONE DB
teams_collection = db['teams']

def get_league_averages(league_name):
    """
    Calcola la media punti casalinga e in trasferta dell'intero campionato.
    """
    # Cerca tutte le squadre di quel campionato
    teams = list(teams_collection.find({"ranking.league": league_name}))

    if not teams:
        # Fallback: ricerca parziale (es. "Serie C" trova "Serie C - Girone A")
        teams = list(teams_collection.find({"ranking.league": {"$regex": league_name, "$options": "i"}}))

    if not teams:
        # Se ancora non trova nulla, usa valori standard (Casa avvantaggiata)
        return 1.60, 1.10 

    total_home_ppg = 0
    total_away_ppg = 0
    count = 0

    for team in teams:
        rank = team.get('ranking', {})

        h_pts = rank.get('homePoints', 0)
        a_pts = rank.get('awayPoints', 0)

        h_played = rank.get('homeStats', {}).get('played', 0)
        a_played = rank.get('awayStats', {}).get('played', 0)

        if h_played > 0:
            total_home_ppg += (h_pts / h_played)
        
        if a_played > 0:
            total_away_ppg += (a_pts / a_played)
            
        if h_played > 0 or a_played > 0:
            count += 1

    if count == 0: return 1.60, 1.10

    # Media delle medie del campionato
    avg_home_league = total_home_ppg / count
    avg_away_league = total_away_ppg / count

    return avg_home_league, avg_away_league

def calculate_field_factor(home_team_name, away_team_name, league_name=None):
    """
    Restituisce il punteggio Fattore Campo (0-7) per Casa e Trasferta.
    Se league_name è None, prova a recuperarlo dalla squadra di casa.
    """
    
    # 1. TROVA SQUADRE
    def find_team(name):
        return teams_collection.find_one({
            "$or": [
                {"name": name},
                {"aliases": name},
                {"aliases.soccerstats": name}
            ]
        })

    home_team = find_team(home_team_name)
    away_team = find_team(away_team_name)

    if not home_team or not away_team:
        print(f"   ❌ FieldFactor: Squadre non trovate ({home_team_name}, {away_team_name})")
        return 3.5, 3.5 # Default neutro

    # 2. DETERMINA LEGA (Se non passata)
    if not league_name:
        # Prendi la lega dal ranking della squadra di casa
        league_name = home_team.get("ranking", {}).get("league", "Unknown")

    # 3. OTTIENI MEDIE CAMPIONATO
    avg_h_league, avg_a_league = get_league_averages(league_name)

    # Protezione divisione per zero
    if avg_h_league < 0.1: avg_h_league = 1.5
    if avg_a_league < 0.1: avg_a_league = 1.0

    # --- CALCOLO CASA ---
    h_rank = home_team.get('ranking', {})
    h_pts = h_rank.get('homePoints', 0)
    h_played = h_rank.get('homeStats', {}).get('played', 0)
    
    if h_played > 0:
        home_ppg = h_pts / h_played
    else:
        home_ppg = avg_h_league # Se non ha giocato, diamogli la media lega

    # Formula: Quanto sei meglio della media casalinga?
    # Bonus base +1.0 per il fattore campo intrinseco
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

    # Formula: Quanto sei meglio della media trasferta?
    away_ratio = away_ppg / avg_a_league
    away_score = away_ratio * 3.5
    if away_score > 7.0: away_score = 7.0

    print(f"\n🏟️  --- ANALISI CAMPO ({league_name}) ---")
    print(f"   Media Lega: Casa {avg_h_league:.2f} pti | Fuori {avg_a_league:.2f} pti")
    print(f"   {home_team_name} (Casa): {home_ppg:.2f} pti/partita -> Score: {home_score:.2f}")
    print(f"   {away_team_name} (Fuori): {away_ppg:.2f} pti/partita -> Score: {away_score:.2f}")

    return round(home_score, 2), round(away_score, 2)

if __name__ == "__main__":
    # Test
    calculate_field_factor("Juventus U23", "Dolomiti")
