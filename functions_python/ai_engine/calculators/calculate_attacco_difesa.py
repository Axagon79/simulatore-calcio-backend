import os
import sys
import time
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

teams_collection = db['teams']

# ======================================================================
# 1. LOGICA MATEMATICA PURA (RANGE 0-15 ATT / 0-10 DIF)
# ======================================================================

def compute_team_scores(team_doc, avg_gf_h, avg_ga_h, avg_gf_a, avg_ga_a):
    """Esegue il calcolo dei punteggi basato sulle medie della lega fornite"""
    r = team_doc.get("ranking", {})
    h = r.get("homeStats", {})
    a = r.get("awayStats", {})

    # --- CALCOLO CASA ---
    gp_h = h.get("played", 0)
    if gp_h > 0:
        att_h_ratio = (h.get("goalsFor", 0) / gp_h) / avg_gf_h
        pct_att_h = max(0, min(100, 50 + (att_h_ratio - 1) * 50))
        
        my_ga_avg = h.get("goalsAgainst", 0) / gp_h
        def_h_ratio = (my_ga_avg if my_ga_avg > 0 else 0.1) / avg_ga_h
        pct_def_h = max(0, min(100, 50 - (def_h_ratio - 1) * 50))
    else:
        pct_att_h = pct_def_h = 50

    # --- CALCOLO TRASFERTA ---
    gp_a = a.get("played", 0)
    if gp_a > 0:
        att_a_ratio = (a.get("goalsFor", 0) / gp_a) / avg_gf_a
        pct_att_a = max(0, min(100, 50 + (att_a_ratio - 1) * 50))
        
        my_ga_avg_a = a.get("goalsAgainst", 0) / gp_a
        def_a_ratio = (my_ga_avg_a if my_ga_avg_a > 0 else 0.1) / avg_ga_a
        pct_def_a = max(0, min(100, 50 - (def_a_ratio - 1) * 50))
    else:
        pct_att_a = pct_def_a = 50

    # Conversione Range Finali
    scores = {
        "attack_home": round((pct_att_h / 100) * 15, 2),
        "defense_home": round((pct_def_h / 100) * 10, 2),
        "attack_away": round((pct_att_a / 100) * 15, 2),
        "defense_away": round((pct_def_a / 100) * 10, 2)
    }
    scores['home_power'] = round(scores['attack_home'] + scores['defense_home'], 2)
    scores['away_power'] = round(scores['attack_away'] + scores['defense_away'], 2)
    
    return scores

# ======================================================================
# 2. FUNZIONE PER L'ENGINE (MODALITÀ BULK)
# ======================================================================

def get_scores_live_bulk(home_name, away_name, league_name, bulk_cache):
    """Calcola i punteggi usando i dati in memoria nel Bulk"""
    if not bulk_cache or "TEAMS" not in bulk_cache:
        return None, None

    # Estraiamo tutte le squadre della lega dal pacco per calcolare le medie gol
    league_teams = [t for t in bulk_cache["TEAMS"] if t.get("league") == league_name]
    if not league_teams:
        return None, None

    # Calcolo medie gol lega istantaneo
    tot_gf_h = tot_ga_h = tot_gp_h = 0
    tot_gf_a = tot_ga_a = tot_gp_a = 0

    for t in league_teams:
        r = t.get("ranking", {})
        h, a = r.get("homeStats", {}), r.get("awayStats", {})
        tot_gf_h += h.get("goalsFor", 0); tot_ga_h += h.get("goalsAgainst", 0); tot_gp_h += h.get("played", 0)
        tot_gf_a += a.get("goalsFor", 0); tot_ga_a += a.get("goalsAgainst", 0); tot_gp_a += a.get("played", 0)

    avg_gf_h = tot_gf_h / tot_gp_h if tot_gp_h > 0 else 1.0
    avg_ga_h = tot_ga_h / tot_gp_h if tot_gp_h > 0 else 1.0
    avg_gf_a = tot_gf_a / tot_gp_a if tot_gp_a > 0 else 1.0
    avg_ga_a = tot_ga_a / tot_gp_a if tot_gp_a > 0 else 1.0

    # Recupero i documenti specifici casa/fuori dal pacco (Fix Alias Blindato)
    def _match(t, target):
        a = t.get("aliases", [])
        return t["name"] == target or (target in a if isinstance(a, list) else target in a.values())

    home_doc = next((t for t in league_teams if _match(t, home_name)), None)
    away_doc = next((t for t in league_teams if _match(t, away_name)), None)

    if not home_doc or not away_doc:
        return None, None

    home_scores = compute_team_scores(home_doc, avg_gf_h, avg_ga_h, avg_gf_a, avg_ga_a)
    away_scores = compute_team_scores(away_doc, avg_gf_h, avg_ga_h, avg_gf_a, avg_ga_a)

    return home_scores, away_scores

# ======================================================================
# 3. AGGIORNAMENTO MASSIVO DB (MODALITÀ BATCH)
# ======================================================================

def calculate_all():
    print("🚀 AVVIO CALCOLO TOTALE (ATTACCO + DIFESA)...")
    leagues = teams_collection.distinct("league")
    total_updated = 0

    for league in leagues:
        if not league: continue
        teams = list(teams_collection.find({"league": league}))
        if not teams: continue

        # Calcolo medie lega
        tot_gf_h = sum(t.get("ranking", {}).get("homeStats", {}).get("goalsFor", 0) for t in teams)
        tot_gp_h = sum(t.get("ranking", {}).get("homeStats", {}).get("played", 0) for t in teams)
        tot_ga_h = sum(t.get("ranking", {}).get("homeStats", {}).get("goalsAgainst", 0) for t in teams)
        
        tot_gf_a = sum(t.get("ranking", {}).get("awayStats", {}).get("goalsFor", 0) for t in teams)
        tot_gp_a = sum(t.get("ranking", {}).get("awayStats", {}).get("played", 0) for t in teams)
        tot_ga_a = sum(t.get("ranking", {}).get("awayStats", {}).get("goalsAgainst", 0) for t in teams)

        avg_gf_h = tot_gf_h / tot_gp_h if tot_gp_h > 0 else 1.0
        avg_ga_h = tot_ga_h / tot_gp_h if tot_gp_h > 0 else 1.0
        avg_gf_a = tot_gf_a / tot_gp_a if tot_gp_a > 0 else 1.0
        avg_ga_a = tot_ga_a / tot_gp_a if tot_gp_a > 0 else 1.0

        for t in teams:
            scores = compute_team_scores(t, avg_gf_h, avg_ga_h, avg_gf_a, avg_ga_a)
            teams_collection.update_one({"_id": t["_id"]}, {"$set": {"scores": scores}})
            total_updated += 1

    print(f"\n✅ AGGIORNAMENTO COMPLETATO! {total_updated} squadre aggiornate.")

if __name__ == "__main__":
    calculate_all()