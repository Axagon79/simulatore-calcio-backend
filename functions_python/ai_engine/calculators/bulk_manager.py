import time
import sys
from config import db


def get_all_data_bulk(home_team, away_team, league_name):
    """
    MAGAZZINO CENTRALE V3: Versione Omnicomprensiva.
    Preleva tutto ciò che l'Engine Core e i Calcolatori cercano,
    eliminando totalmente la latenza del Database durante la simulazione.
    """
    t_start = time.time()
    
    league_normalized = league_name.replace('_', ' ').title()
    league_map = {
        # ITALIA
        "Serie A": "Serie A",
        "Serie B": "Serie B",
        "Serie C Girone A": "Serie C - Girone A",
        "Serie C Girone B": "Serie C - Girone B",
        "Serie C Girone C": "Serie C - Girone C",
        
        # EUROPA TOP
        "Premier League": "Premier League",
        "La Liga": "La Liga",
        "Bundesliga": "Bundesliga",
        "Ligue 1": "Ligue 1",
        "Eredivisie": "Eredivisie",
        "Liga Portugal": "Liga Portugal",
        
        # EUROPA SERIE B
        "Championship": "Championship",
        "Laliga 2": "LaLiga 2",
        "2. Bundesliga": "2. Bundesliga",
        "Ligue 2": "Ligue 2",
        
        # EUROPA NORDICI + EXTRA
        "Scottish Premiership": "Scottish Premiership",
        "Allsvenskan": "Allsvenskan",
        "Eliteserien": "Eliteserien",
        "Superligaen": "Superligaen",
        "Jupiler Pro League": "Jupiler Pro League",
        "Süper Lig": "Süper Lig",
        "Super Lig": "Süper Lig",  # ✅ AGGIUNGI QUESTA RIGA!
        "Sper Lig": "Süper Lig",   # Fallback se arriva senza ü
        "League Of Ireland": "League of Ireland Premier Division",
        
        # AMERICHE
        "Brasileirão": "Brasileirão Serie A",
        "Primera División": "Primera División",
        "Mls": "Major League Soccer",
        
        # ASIA
        "J1 League": "J1 League"
    }
    league_normalized = league_map.get(league_normalized, league_normalized)
    
    # ✅ LOG 1: INPUT
    print(f"🔍 [BULK] INPUT: home={home_team}, away={away_team}, league={league_name}", file=sys.stderr)
    print(f"🔍 [BULK] League normalizzata: '{league_name}' -> '{league_normalized}'", file=sys.stderr)
    
    team_names = [home_team, away_team]
    player_query = {"team_name_fbref": {"$in": team_names}, "league_name": league_normalized}
    team_query = {"$or": [{"name": {"$in": team_names}}, {"aliases": {"$in": team_names}}]}

    # ✅ LOG 2: QUERY PLAYERS
    print(f"🔍 [BULK] Query players: {player_query}", file=sys.stderr)
    raw_players_gk = list(db["players_stats_fbref_gk"].find(player_query, {"_id": 0}))
    raw_players_def = list(db["players_stats_fbref_def"].find(player_query, {"_id": 0}))
    raw_players_mid = list(db["players_stats_fbref_mid"].find(player_query, {"_id": 0}))
    raw_players_att = list(db["players_stats_fbref_att"].find(player_query, {"_id": 0}))
    print(f"🔍 [BULK] Players trovati: GK={len(raw_players_gk)}, DEF={len(raw_players_def)}, MID={len(raw_players_mid)}, ATT={len(raw_players_att)}", file=sys.stderr)
    
    # ✅ LOG 3: QUERY TEAMS
    print(f"🔍 [BULK] Query teams: {team_query}", file=sys.stderr)
    raw_teams = list(db["teams"].find(team_query, {"_id": 0}))
    print(f"🔍 [BULK] Teams trovati: {len(raw_teams)}", file=sys.stderr)
    for team in raw_teams:
        name = team.get("name")
        league = team.get("league")
        has_scores = bool(team.get("scores"))
        scores_keys = list(team.get("scores", {}).keys()) if has_scores else []
        print(f"  - {name} (league={league}): scores={has_scores}, keys={scores_keys}", file=sys.stderr)
    
    raw_rounds = list(db["h2h_by_round"].find().sort("last_updated", -1))
    print(f"🔍 [BULK] Rounds totali caricati: {len(raw_rounds)}", file=sys.stderr)

    # 3. ESTRAZIONE DATI H2H SPECIFICI
    h2h_match_data = {"h_score": 0, "a_score": 0, "msg": "Dati non trovati", "extra": {}, "quotes": {}}
    
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
    print(f"🔍 [BULK] H2H pipeline risultati: {len(result)}", file=sys.stderr)
    
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
            "quotes": match.get("odds", {})
        }
        print(f"🔍 [BULK] H2H trovato: {h2h_match_data['msg']}", file=sys.stderr)

    # ✅ LOG 4: LEAGUE STATS (USA league_normalized)
    all_teams_league = list(db["teams"].find({"league": league_normalized}, {"ranking": 1}))
    print(f"🔍 [BULK] Teams nella lega '{league_normalized}': {len(all_teams_league)}", file=sys.stderr)
    
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
    print(f"🔍 [BULK] League stats: avg_home={avg_h_l:.2f}, avg_away={avg_a_l:.2f}", file=sys.stderr)

    # ✅ LOG 5: MASTER_DATA CONSTRUCTION
    print(f"🔍 [BULK] Costruzione MASTER_DATA per {len(raw_teams)} teams...", file=sys.stderr)
    master_map = {}
    for team in raw_teams:
        name = team.get("name")
        scores = team.get("scores", {})
        stats = team.get("stats", {})
        ranking = team.get("ranking", {})
        
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
        
        print(f"  - MASTER_DATA[{name}]: power={team_entry['power']}, attack={team_entry['attack']}, defense={team_entry['defense']}", file=sys.stderr)
        
        master_map[name] = team_entry
        for alias in team.get("aliases", []):
            master_map[alias] = team_entry
            
    print(f"🔍 [BULK] MASTER_DATA chiavi totali: {len(master_map)}", file=sys.stderr)
    
    # 6. CARICA STORICO H2H
    h2h_historical_stats = None
    
    h2h_doc = db.raw_h2h_data_v2.find_one({
        "$or": [
            {"team_a": home_team, "team_b": away_team},
            {"team_a": away_team, "team_b": home_team}
        ]
    })
    
    if h2h_doc and 'matches' in h2h_doc:
        matches = h2h_doc['matches']
        played_matches = [m for m in matches if m.get('score') != '-:-' and ':' in m.get('score', '')]
        
        if played_matches:
            over25_count = 0
            gg_count = 0
            
            for match in played_matches:
                try:
                    score = match['score']
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
            print(f"🔍 [BULK] H2H historical: {total_played} matches", file=sys.stderr)

    bulk_cache = {
        "ROSE": {
            "GK": raw_players_gk,
            "DEF": raw_players_def,
            "MID": raw_players_mid,
            "ATT": raw_players_att
        },
        "TEAMS": raw_teams,
        "MASTER_DATA": master_map,
        "ALL_ROUNDS": raw_rounds,
        "MATCH_H2H": h2h_match_data,
        "LEAGUE_STATS": {
            'league': league_normalized,  # ✅ AGGIUNGI QUESTA RIGA!
            "avg_home_league": avg_h_l,
            "avg_away_league": avg_a_l
        },
        "H2H_HISTORICAL": h2h_historical_stats
    }

    t_end = time.time() - t_start
    print(f"📦 [BULK V3] Pacco completo pronto in {t_end:.3f}s", file=sys.stderr)
    print(f"📦 [BULK] RIEPILOGO: TEAMS={len(raw_teams)}, MASTER_DATA_KEYS={len(master_map)}, ROUNDS={len(raw_rounds)}", file=sys.stderr)
    
    return bulk_cache

def get_all_data_bulk_cups(home_team, away_team, competition):
    """
    BULK CACHE PER COPPE EUROPEE
    Versione ottimizzata per Champions League e Europa League.
    Carica tutti i dati necessari UNA VOLTA SOLA per velocizzare le simulazioni.
    
    Args:
        home_team: nome squadra casa
        away_team: nome squadra trasferta  
        competition: "UCL" o "UEL"
    
    Returns:
        bulk_cache: dizionario con tutti i dati pre-caricati
    """
    t_start = time.time()
    
    # Mappa competizione -> collezione
    teams_map = {
        "UCL": "teams_champions_league",
        "UEL": "teams_europa_league"
    }

    matches_map = {
        "UCL": "matches_champions_league",
        "UEL": "matches_europa_league"
    }

    teams_collection = teams_map.get(competition)
    matches_collection = matches_map.get(competition)
    
    if not teams_collection:
        print(f"❌ [BULK CUPS] Competizione non valida: {competition}", file=sys.stderr)
        return None
    
    print(f"🏆 [BULK CUPS] INPUT: home={home_team}, away={away_team}, competition={competition}", file=sys.stderr)
    print(f"🏆 [BULK CUPS] Collections: teams={teams_collection}, matches={matches_collection}", file=sys.stderr)
    
    # 1. CARICA TEAMS (con aliases!)
    team_query = {
        "$or": [
            {"name": {"$in": [home_team, away_team]}},
            {"aliases": {"$in": [home_team, away_team]}}
        ]
    }
    
    raw_teams = list(db[teams_collection].find(team_query, {"_id": 0}))
    print(f"🏆 [BULK CUPS] Teams trovati: {len(raw_teams)}", file=sys.stderr)
    
    for team in raw_teams:
        name = team.get("name")
        elo = team.get("elo_rating", 0)
        rosa = team.get("valore_rosa_transfermarkt", 0)
        print(f"  - {name}: ELO={elo}, Rosa={rosa}", file=sys.stderr)
    
    # 2. CARICA MATCH DATA (per odds e info partita)
    # Crea lista di TUTTI i possibili nomi (reale + aliases) per ogni squadra
    home_names = [home_team]
    away_names = [away_team]

    for team in raw_teams:
        name = team.get('name')
        aliases = team.get('aliases', [])
        
        if name == home_team or home_team in aliases:
            home_names.append(name)
            home_names.extend(aliases)
        
        if name == away_team or away_team in aliases:
            away_names.append(name)
            away_names.extend(aliases)

    # Rimuovi duplicati
    home_names = list(set(home_names))
    away_names = list(set(away_names))

    print(f"🔍 [BULK CUPS] Nomi possibili Home: {home_names}", file=sys.stderr)
    print(f"🔍 [BULK CUPS] Nomi possibili Away: {away_names}", file=sys.stderr)

    # Cerca con TUTTI i nomi possibili
    match_query = {
        "home_team": {"$in": home_names},
        "away_team": {"$in": away_names},
        "season": "2025-2026"
    }

    match_doc = db[matches_collection].find_one(match_query, {"_id": 0})
    
    
    
    if match_doc:
        print(f"✅ [BULK CUPS] Match trovato: {match_doc.get('homeTeam')} vs {match_doc.get('awayTeam')}", file=sys.stderr)
        odds = match_doc.get('odds', {})
        print(f"  Odds: Home={odds.get('home')}, Draw={odds.get('draw')}, Away={odds.get('away')}", file=sys.stderr)
    else:
        print(f"❌ [BULK CUPS] NESSUN MATCH TROVATO!", file=sys.stderr)
        match_doc = {}
    
    # 3. CARICA TUTTI I TEAM DELLA COMPETIZIONE (per normalizzazione)
    all_teams_competition = list(db[teams_collection].find({}, {"_id": 0, "valore_rosa_transfermarkt": 1, "elo_rating": 1}))
    print(f"🏆 [BULK CUPS] Teams totali in competizione: {len(all_teams_competition)}", file=sys.stderr)
    
    # Calcola min/max per normalizzazione
    rosa_values = [t.get("valore_rosa_transfermarkt", 0) for t in all_teams_competition if t.get("valore_rosa_transfermarkt")]
    elo_values = [t.get("elo_rating", 1500) for t in all_teams_competition if t.get("elo_rating")]
    
    rosa_min = min(rosa_values) if rosa_values else 0
    rosa_max = max(rosa_values) if rosa_values else 1000000000
    elo_min = min(elo_values) if elo_values else 1400
    elo_max = max(elo_values) if elo_values else 2000
    
    print(f"📊 [BULK CUPS] Rosa range: {rosa_min:,.0f} - {rosa_max:,.0f}", file=sys.stderr)
    print(f"📊 [BULK CUPS] ELO range: {elo_min} - {elo_max}", file=sys.stderr)
    
    # 4. COSTRUISCI MASTER_DATA (simile ai campionati)
    master_map = {}
    
    for team in raw_teams:
        name = team.get("name")
        
        # Per le coppe non abbiamo power/attack/defense pre-calcolati
        # Li calcoleremo dal rating in preload_match_data
        team_entry = {
            "valore_rosa": team.get("valore_rosa_transfermarkt", 0),
            "elo_rating": team.get("elo_rating", 1500),
            "country": team.get("country", "Unknown"),
            "status": team.get("status", "active")
        }
        
        master_map[name] = team_entry
        
        # Aggiungi aliases
        for alias in team.get("aliases", []):
            master_map[alias] = team_entry
    
    print(f"🏆 [BULK CUPS] MASTER_DATA chiavi totali: {len(master_map)}", file=sys.stderr)
    
    # 5. COSTRUISCI BULK_CACHE
    bulk_cache = {
        "TEAMS": raw_teams,
        "MASTER_DATA": master_map,
        "MATCH_DATA": match_doc,
        "ALL_TEAMS_COMPETITION": all_teams_competition,
        "NORMALIZATION": {
            "rosa_min": rosa_min,
            "rosa_max": rosa_max,
            "elo_min": elo_min,
            "elo_max": elo_max
        },
        "COMPETITION_INFO": {
            "name": "Champions League" if competition == "UCL" else "Europa League",
            "code": competition,
            "teams_collection": teams_collection,
            "matches_collection": matches_collection
        },
        # Placeholder per compatibilità con engine_core
        "MATCH_H2H": {
            "h_score": 0,
            "a_score": 0,
            "msg": "H2H non disponibile per coppe",
            "extra": {"avg_goals_home": 1.5, "avg_goals_away": 1.2},
            "quotes": match_doc.get("odds", {})
        },
        "LEAGUE_STATS": {
            "league": competition,
            "avg_home_league": 1.50,  # Media europea
            "avg_away_league": 1.20
        },
        "H2H_HISTORICAL": None  # Non disponibile per coppe
    }
    
    t_end = time.time() - t_start
    print(f"📦 [BULK CUPS] Pacco completo pronto in {t_end:.3f}s", file=sys.stderr)
    print(f"📦 [BULK CUPS] RIEPILOGO: TEAMS={len(raw_teams)}, MASTER_DATA_KEYS={len(master_map)}, ALL_TEAMS={len(all_teams_competition)}", file=sys.stderr)
    
    return bulk_cache