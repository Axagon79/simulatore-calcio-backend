import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

# CONFIGURAZIONE DATABASE
DB_NAME = "pup_pals_db"
COLLECTION_TEAMS = "teams"

def connect_db():
    return db[COLLECTION_TEAMS]

def get_league_averages(league_name, teams_collection):
    """
    Calcola la media punti casalinga e in trasferta dell'intero campionato specifico.
    """
    # Cerca tutte le squadre di quel campionato
    teams = list(teams_collection.find({"ranking.league": league_name}))

    if not teams:
        # Fallback: ricerca case-insensitive
        teams = list(teams_collection.find({"ranking.league": {"$regex": league_name, "$options": "i"}}))

    if not teams:
        # Se ancora non trova nulla, usa valori di default neutri per non bloccare tutto
        return 1.5, 1.0 

    total_home_points = 0
    total_away_points = 0
    count = 0

    for team in teams:
        rank = team.get('ranking', {})

        # Recupera i punti salvati dallo scraper
        h_pts = rank.get('homePoints', 0)
        a_pts = rank.get('awayPoints', 0)

        # Recupera le partite giocate per fare la media
        # Se mancano, usiamo 1 per evitare divisioni per zero (ma i dati dovrebbero esserci)
        h_played = rank.get('homeStats', {}).get('played', 1)
        a_played = rank.get('awayStats', {}).get('played', 1)

        if h_played == 0: h_played = 1
        if a_played == 0: a_played = 1

        # Calcola media punti singola squadra
        total_home_points += (h_pts / h_played)
        total_away_points += (a_pts / a_played)
        count += 1

    if count == 0: return 1.5, 1.0

    # Media delle medie del campionato
    avg_home_league = total_home_points / count
    avg_away_league = total_away_points / count

    return avg_home_league, avg_away_league

def calculate_field_factor(home_team_name, away_team_name, league_name):
    """
    Funzione principale.
    Restituisce il punteggio Fattore Campo (0-7) per Casa e Trasferta.
    """
    teams_col = connect_db()

    # 1. Ottieni dati squadre (con ricerca flessibile per nome o alias)
    # Usiamo la logica "smart" anche qui per trovarle
    def find_team(name):
        return teams_col.find_one({
            "$or": [
                {"name": name},
                {"aliases.soccerstats": name},
                {"aliases": name}
            ]
        })

    home_team = find_team(home_team_name)
    away_team = find_team(away_team_name)

    if not home_team or not away_team:
        print(f"❌ Errore: Una delle squadre non trovata ({home_team_name}, {away_team_name})")
        return 3.5, 3.5 # Default medio

    # 2. Ottieni medie campionato
    avg_home_league, avg_away_league = get_league_averages(league_name, teams_col)

    # Protezione divisione per zero
    if avg_home_league < 0.1: avg_home_league = 1.5
    if avg_away_league < 0.1: avg_away_league = 1.0

    # --- CALCOLO CASA ---
    h_rank = home_team.get('ranking', {})
    h_pts = h_rank.get('homePoints', 0)
    h_played = h_rank.get('homeStats', {}).get('played', 1)
    if h_played == 0: h_played = 1

    home_avg = h_pts / h_played

    # Formula: (Ratio * 3.5) + 1 Bonus
    home_ratio = home_avg / avg_home_league
    home_score = (home_ratio * 3.5) + 1.0

    # Cap a 7
    if home_score > 7: home_score = 7.0

    # --- CALCOLO OSPITE ---
    a_rank = away_team.get('ranking', {})
    a_pts = a_rank.get('awayPoints', 0)
    a_played = a_rank.get('awayStats', {}).get('played', 1)
    if a_played == 0: a_played = 1

    away_avg = a_pts / a_played

    # Formula: Ratio * 3.5
    away_ratio = away_avg / avg_away_league
    away_score = away_ratio * 3.5

    # Cap a 7
    if away_score > 7: away_score = 7.0

    return round(home_score, 2), round(away_score, 2)
if __name__ == "__main__":
    casa = "Inter"
    trasferta = "Napoli"
    league = "Serie A"  # modifica se necessario

    home_factor, away_factor = calculate_field_factor(casa, trasferta, league)
    print(f"Fattore campo: {casa} = {home_factor}, {trasferta} = {away_factor}")
