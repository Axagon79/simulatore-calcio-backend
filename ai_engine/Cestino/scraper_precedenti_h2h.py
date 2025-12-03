import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import os
import sys
import re

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_h2h_scores(home_team_name, away_team_name):
    print(f"\n⚔️  Analisi H2H Dual: {home_team_name} (Casa) vs {away_team_name} (Trasferta)")

    home_team = db.teams.find_one({"name": home_team_name})
    away_team = db.teams.find_one({"name": away_team_name})

    if not home_team or not away_team:
        return {'home_score': 3.5, 'away_score': 3.5}

    id_home = home_team.get("transfermarkt_id")
    slug_home = home_team.get("transfermarkt_slug")
    id_away = away_team.get("transfermarkt_id")

    if not id_home or not id_away:
        return {'home_score': 3.5, 'away_score': 3.5}

    url = (
        f"https://www.transfermarkt.it/{slug_home}/bilanzdetail/verein/{id_home}"
        f"/saison_id/0/wettbewerb_id//datum_von/0000-00-00/datum_bis/0000-00-00"
        f"/gegner_id/{id_away}/day/0/plus/1"
    )
    
    try:
        time.sleep(10)
        response = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(response.content, "html.parser")
        rows = soup.select("table.items tbody tr")
        
        # Accumulatori separati
        # HOME TEAM
        h_points = 0.0
        h_max_possible = 0.0
        h_streak = 0
        h_wins = 0
        
        # AWAY TEAM
        a_points = 0.0
        a_max_possible = 0.0
        a_streak = 0
        a_wins = 0
        
        current_year = datetime.now().year
        valid_matches = 0

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 10: continue

            # DATA
            date_text = cols[5].get_text(strip=True)
            if not date_text or date_text == "-": continue
            try:
                match_date = datetime.strptime(date_text, "%d/%m/%Y")
            except ValueError: continue
            
            years_ago = current_year - match_date.year
            if years_ago > 20: continue

            # RISULTATO
            res_text = cols[9].get_text(strip=True)
            if res_text == "-:-": continue
            
            try:
                parts = res_text.split(":")
                score_left = int(parts[0]) 
                score_right = int(parts[1])
            except: continue

            valid_matches += 1

            # CHI ERA IN CASA NELLO STORICO?
            host_text = cols[7].get_text(strip=True).lower()
            host_clean = re.sub(r'\(\d+\.\)', '', host_text).strip()
            
            # 'we_are_home' significa: Nel match storico, Team HOME (Inter) era in casa.
            we_are_home_historic = home_team_name.lower() in host_clean or host_clean in home_team_name.lower()
            
            # CALCOLO PUNTI MATCH PER LE DUE SQUADRE
            pts_for_home = 0
            pts_for_away = 0
            
            # Logica Chi ha vinto?
            # Left = Host storico, Right = Guest storico
            
            if score_left > score_right: 
                # Ha vinto HOST
                if we_are_home_historic: 
                    pts_for_home = 3 # Inter era Host -> Inter vince
                    pts_for_away = 0
                else:
                    pts_for_home = 0 # Lecce era Host -> Inter perde
                    pts_for_away = 3
            elif score_right > score_left:
                # Ha vinto GUEST
                if we_are_home_historic:
                    pts_for_home = 0 # Inter era Host -> Inter perde
                    pts_for_away = 3
                else:
                    pts_for_home = 3 # Lecce era Host -> Inter vince
                    pts_for_away = 0
            else:
                # Pareggio
                pts_for_home = 1
                pts_for_away = 1.5

            # Aggiornamento Strisce
            if pts_for_home == 3: h_streak += 1; h_wins += 1
            elif pts_for_home == 0: h_streak = 0
            else: h_streak += 1 # Pareggio mantiene striscia?
            
            if pts_for_away == 3: a_streak += 1; a_wins += 1
            elif pts_for_away == 0: a_streak = 0
            else: a_streak += 1

            # PESI (Uguali per l'età, diversi per il contesto Casa/Fuori)
            base_weight = 1.0
            if years_ago <= 5: base_weight = 1.0
            elif years_ago <= 10: base_weight = 0.75
            else: base_weight = 0.50

            # PESO CASA:
            # L'Inter di oggi gioca in CASA. Quindi le partite storiche dove era CASA valgono di più per lei.
            w_home = base_weight
            if we_are_home_historic: w_home *= 1.5
            
            # PESO TRASFERTA:
            # Il Lecce di oggi gioca FUORI. Quindi le partite storiche dove era FUORI (cioè Inter Casa) valgono di più per lui (per capire quanto soffre fuori).
            w_away = base_weight
            if we_are_home_historic: w_away *= 1.5 
            
            h_points += pts_for_home * w_home
            h_max_possible += 3 * w_home
            
            a_points += pts_for_away * w_away
            a_max_possible += 3 * w_away

        # CALCOLO FINALE
        def calc_final(pts, max_pts, streak):
            if max_pts == 0: return 3.5
            rate = pts / max_pts
            score = rate * 5.0
            bonus = min(streak * 0.4, 2.0)
            final = score + bonus
            return min(final, 7.0)

        final_home = calc_final(h_points, h_max_possible, h_streak)
        final_away = calc_final(a_points, a_max_possible, a_streak)
        
        print(f"📊 Stats: Inter V{h_wins} | Lecce V{a_wins} (su {valid_matches})")
        print(f"🧮 Home Score: {final_home:.2f} | Away Score: {final_away:.2f}")
        
        return {'home_score': round(final_home, 2), 'away_score': round(final_away, 2)}

    except Exception as e:
        print(f"❌ Errore: {e}")
        return {'home_score': 3.5, 'away_score': 3.5}

if __name__ == "__main__":
    get_h2h_scores("Inter", "Lecce")
