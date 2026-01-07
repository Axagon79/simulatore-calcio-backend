import time
from config import db


def get_all_data_bulk(home_team, away_team, league_name):
    """
    MAGAZZINO CENTRALE V3: Versione Omnicomprensiva.
    Preleva tutto ciò che l'Engine Core e i Calcolatori cercano,
    eliminando totalmente la latenza del Database durante la simulazione.
    """
    t_start = time.time()
    
    # 1. PARAMETRI E QUERY
    team_names = [home_team, away_team]
    player_query = {"team_name_fbref": {"$in": team_names}, "league_name": league_name}
    team_query = {"$or": [{"name": {"$in": team_names}}, {"aliases": {"$in": team_names}}]}

    # 2. DOWNLOAD MASSIVO
    # Recupero Rose (4 collezioni)
    raw_players_gk = list(db["players_stats_fbref_gk"].find(player_query, {"_id": 0}))
    raw_players_def = list(db["players_stats_fbref_def"].find(player_query, {"_id": 0}))
    raw_players_mid = list(db["players_stats_fbref_mid"].find(player_query, {"_id": 0}))
    raw_players_att = list(db["players_stats_fbref_att"].find(player_query, {"_id": 0}))
    
    # Recupero Documenti Squadra
    raw_teams = list(db["teams"].find(team_query, {"_id": 0}))
    
    # ✅ RECUPERO TUTTI I ROUND (come fa il BVS - senza filtro su _id)
    raw_rounds = list(db["h2h_by_round"].find().sort("last_updated", -1))

    # 3. ESTRAZIONE DATI H2H SPECIFICI (METODO BVS)
    h2h_match_data = {"h_score": 0, "a_score": 0, "msg": "Dati non trovati", "extra": {}, "quotes": {}}
    
    # ✅ USA AGGREGATION PIPELINE (come fa calculator_bvs.py)
    pipeline = [
        {"$unwind": "$matches"},
        {"$match": {
            "$or": [
                {"matches.home": home_team, "matches.away": away_team, "matches.h2h_data": {"$exists": True}},
                {"matches.home": {"$regex": f"^{home_team}$", "$options": "i"},
                 "matches.away": {"$regex": f"^{away_team}$", "$options": "i"},
                 "matches.h2h_data": {"$exists": True}}
            ]
        }},
        {"$sort": {"last_updated": -1}},
        {"$limit": 1},
        {"$project": {"match": "$matches"}}
    ]
    
    result = list(db["h2h_by_round"].aggregate(pipeline))
    
    if result:
        match = result[0]["match"]
        h2h = match.get("h2h_data", {})
        
        h2h_match_data = {
            "h_score": h2h.get("home_score", 0),
            "a_score": h2h.get("away_score", 0),
            "msg": h2h.get("history_summary", "H2H Caricato"),
            "extra": {
                "avg_goals_home": h2h.get("avg_goals_home", 1.2),
                "avg_goals_away": h2h.get("avg_goals_away", 1.0)
            },
            "quotes": match.get("odds", {})  # ✅ Quote REALI dal campo "odds" del match
        }

    # 4. CALCOLO MEDIE LEGA (PER FATTORE CAMPO)
    all_teams_league = list(db["teams"].find({"league": league_name}, {"ranking": 1}))
    total_h_ppg = total_a_ppg = count = 0
    for t in all_teams_league:
        r = t.get('ranking', {})
        hs, as_stat = r.get('homeStats', {}).get('played', 0), r.get('awayStats', {}).get('played', 0)
        if hs > 0: 
            total_h_ppg += (r.get('homePoints', 0) / hs)
            count += 1
        if as_stat > 0: 
            total_a_ppg += (r.get('awayPoints', 0) / as_stat)
    
    avg_h_l = total_h_ppg / count if count > 0 else 1.60
    avg_a_l = total_a_ppg / count if count > 0 else 1.10

    # 5. COSTRUZIONE MASTER_DATA (Mappa tecnica per l'Engine)
    master_map = {}
    for team in raw_teams:
        name = team.get("name")
        scores = team.get("scores", {})
        stats = team.get("stats", {})
        ranking = team.get("ranking", {})
        
        # Calcolo PPG (Punti Per Partita) istantaneo per Fattore Campo
        h_played = ranking.get("homeStats", {}).get("played", 1)
        a_played = ranking.get("awayStats", {}).get("played", 1)
        h_ppg = ranking.get("homePoints", 0) / h_played if h_played > 0 else 0
        a_ppg = ranking.get("awayPoints", 0) / a_played if a_played > 0 else 0

        team_entry = {
            "power": scores.get("home_power") if name == home_team else scores.get("away_power"),
            "attack": scores.get("attack_home") if name == home_team else scores.get("attack_away"),
            "defense": scores.get("defense_home") if name == home_team else scores.get("defense_away"),
            "motivation": stats.get("motivation", 10.0),
            "strength_score": stats.get("strengthScore09", 5.0),
            "reliability": stats.get("reliability", 5.0) or scores.get("reliability", 5.0),
            "rating_stored": team.get("rating_5_25"),
            "ppg_home": h_ppg,
            "ppg_away": a_ppg,
            "formation": team.get("formation")
        }
        
        # Mapping su Nome Ufficiale e Alias per massima compatibilità
        master_map[name] = team_entry
        for alias in team.get("aliases", []):
            master_map[alias] = team_entry
            
    # 6. CARICA STORICO H2H DA raw_h2h_data_v2
    h2h_historical_stats = None
    
    # Cerca in entrambe le direzioni (A vs B o B vs A)
    h2h_doc = db.raw_h2h_data_v2.find_one({
        "$or": [
            {"team_a": home_team, "team_b": away_team},
            {"team_a": away_team, "team_b": home_team}
        ]
    })
    
    if h2h_doc and 'matches' in h2h_doc:
        matches = h2h_doc['matches']
        
        # Filtra solo partite giocate (non future "-:-")
        played_matches = [m for m in matches if m.get('score') != '-:-' and ':' in m.get('score', '')]
        
        if played_matches:
            # Calcola statistiche Over/Under 2.5
            over25_count = 0
            gg_count = 0
            
            for match in played_matches:
                try:
                    score = match['score']
                    # Gestisci casi tipo "0:1d.t.s." (dopo tempi supplementari)
                    score_clean = score.split('d.t.s.')[0].strip()
                    
                    gh, ga = map(int, score_clean.split(':'))
                    total = gh + ga
                    
                    if total > 2.5:
                        over25_count += 1
                    
                    if gh > 0 and ga > 0:
                        gg_count += 1
                except:
                    continue
            
            total_played = len(played_matches)
            
            h2h_historical_stats = {
                'total_matches': total_played,
                'over25_pct': round(over25_count / total_played * 100, 2) if total_played > 0 else 0,
                'under25_pct': round((total_played - over25_count) / total_played * 100, 2) if total_played > 0 else 0,
                'gg_pct': round(gg_count / total_played * 100, 2) if total_played > 0 else 0,
                'ng_pct': round((total_played - gg_count) / total_played * 100, 2) if total_played > 0 else 0
            }

    # 7. PACCO CACHE FINALE
    bulk_cache = {
        "ROSE": {
            "GK": raw_players_gk, "DEF": raw_players_def, 
            "MID": raw_players_mid, "ATT": raw_players_att
        },
        "TEAMS": raw_teams,
        "MASTER_DATA": master_map,
        "ALL_ROUNDS": raw_rounds,
        "MATCH_H2H": h2h_match_data,
        "LEAGUE_STATS": {
            "avg_home_league": avg_h_l, 
            "avg_away_league": avg_a_l
        },
        "H2H_HISTORICAL": h2h_historical_stats
    }

    t_end = time.time() - t_start
    print(f"📦 [BULK V3] Pacco completo pronto in {t_end:.3f}s")
    
    return bulk_cache
