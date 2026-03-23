"""
BULK MANAGER C — Versione dedicata al Sistema C
================================================
Copia da bulk_manager.py, modificata per caricare TUTTE le squadre
di una lega in una sola chiamata. L'originale bulk_manager.py resta intatto.

Uso:
    league_cache = load_league_cache(all_team_names, league_name)
    bulk_cache = build_match_cache(league_cache, home, away)
"""
import time
import sys
from config import db


# ==================== LEAGUE MAP (copiata da bulk_manager) ====================
_LEAGUE_MAP = {
    "Serie A": "Serie A",
    "Serie B": "Serie B",
    "Serie C Girone A": "Serie C - Girone A",
    "Serie C Girone B": "Serie C - Girone B",
    "Serie C Girone C": "Serie C - Girone C",
    "Premier League": "Premier League",
    "La Liga": "La Liga",
    "Bundesliga": "Bundesliga",
    "Ligue 1": "Ligue 1",
    "Eredivisie": "Eredivisie",
    "Liga Portugal": "Liga Portugal",
    "Championship": "Championship",
    "Laliga 2": "LaLiga 2",
    "2. Bundesliga": "2. Bundesliga",
    "Ligue 2": "Ligue 2",
    "Scottish Premiership": "Scottish Premiership",
    "Allsvenskan": "Allsvenskan",
    "Eliteserien": "Eliteserien",
    "Superligaen": "Superligaen",
    "Jupiler Pro League": "Jupiler Pro League",
    "Süper Lig": "Süper Lig",
    "Super Lig": "Süper Lig",
    "Sper Lig": "Süper Lig",
    "League Of Ireland": "League of Ireland Premier Division",
    "Brasileirão": "Brasileirão Serie A",
    "Primera División": "Primera División",
    "Mls": "Major League Soccer",
    "J1 League": "J1 League"
}


def _normalize_league(league_name):
    league_normalized = league_name.replace('_', ' ').title()
    return _LEAGUE_MAP.get(league_normalized, league_normalized)


def load_league_cache(all_team_names, league_name):
    """
    Carica TUTTI i dati pesanti per una lega in UNA sola chiamata.
    Chiamare UNA VOLTA per lega, poi usare build_match_cache() per ogni partita.

    Args:
        all_team_names: lista di TUTTE le squadre della lega per quel giorno
        league_name: nome della lega
    Returns:
        league_cache: dizionario con dati condivisi
    """
    t_start = time.time()
    league_normalized = _normalize_league(league_name)

    print(f"🔍 [BULK-C] Caricamento lega: {league_name} -> {league_normalized}", file=sys.stderr)
    print(f"🔍 [BULK-C] Squadre: {len(all_team_names)} — {all_team_names}", file=sys.stderr)

    # 1. PLAYERS — tutte le squadre in una query
    player_query = {"team_name_fbref": {"$in": all_team_names}, "league_name": league_normalized}
    raw_players_gk = list(db["players_stats_fbref_gk"].find(player_query, {"_id": 0}))
    raw_players_def = list(db["players_stats_fbref_def"].find(player_query, {"_id": 0}))
    raw_players_mid = list(db["players_stats_fbref_mid"].find(player_query, {"_id": 0}))
    raw_players_att = list(db["players_stats_fbref_att"].find(player_query, {"_id": 0}))
    print(f"🔍 [BULK-C] Players: GK={len(raw_players_gk)}, DEF={len(raw_players_def)}, MID={len(raw_players_mid)}, ATT={len(raw_players_att)}", file=sys.stderr)

    # 2. TEAMS — tutte le squadre in una query
    team_query = {"$or": [{"name": {"$in": all_team_names}}, {"aliases": {"$in": all_team_names}}]}
    raw_teams = list(db["teams"].find(team_query, {"_id": 0}))
    print(f"🔍 [BULK-C] Teams trovati: {len(raw_teams)}", file=sys.stderr)

    # 3. ROUNDS — solo le ultime 12 giornate (bastano per Lucifero)
    raw_rounds = list(db["h2h_by_round"].find({"league": league_normalized}).sort("last_updated", -1).limit(12))
    print(f"🔍 [BULK-C] Rounds caricati: {len(raw_rounds)} (limit 12)", file=sys.stderr)

    # Fallback se 0 rounds
    if not raw_rounds and all_team_names:
        fallback = list(db["h2h_by_round"].aggregate([
            {"$unwind": "$matches"},
            {"$match": {"matches.home": all_team_names[0]}},
            {"$limit": 1}
        ]))
        if fallback:
            actual_league = fallback[0].get("league")
            print(f"⚠️ [BULK-C] Fallback lega: {actual_league}", file=sys.stderr)
            raw_rounds = list(db["h2h_by_round"].find({"league": actual_league}).sort("last_updated", -1).limit(12))
            league_normalized = actual_league

    # 4. LEAGUE STATS
    all_teams_league = list(db["teams"].find({"league": league_normalized}, {"ranking": 1}))
    total_h_ppg = total_a_ppg = count = 0
    for t in all_teams_league:
        r = t.get('ranking', {})
        hs = r.get('homeStats', {}).get('played', 0)
        as_stat = r.get('awayStats', {}).get('played', 0)
        if hs > 0:
            total_h_ppg += (r.get('homePoints', 0) / hs)
            count += 1
        if as_stat > 0:
            total_a_ppg += (r.get('awayPoints', 0) / as_stat)

    avg_h_l = total_h_ppg / count if count > 0 else 1.60
    avg_a_l = total_a_ppg / count if count > 0 else 1.10
    print(f"🔍 [BULK-C] League stats: avg_home={avg_h_l:.2f}, avg_away={avg_a_l:.2f}", file=sys.stderr)

    t_end = time.time() - t_start
    print(f"📦 [BULK-C] Cache lega pronta in {t_end:.1f}s — Teams={len(raw_teams)}, Rounds={len(raw_rounds)}", file=sys.stderr)

    return {
        "ROSE": {
            "GK": raw_players_gk,
            "DEF": raw_players_def,
            "MID": raw_players_mid,
            "ATT": raw_players_att
        },
        "TEAMS": raw_teams,
        "ALL_ROUNDS": raw_rounds,
        "LEAGUE_STATS": {
            "league": league_normalized,
            "avg_home_league": avg_h_l,
            "avg_away_league": avg_a_l
        },
        "_league_normalized": league_normalized
    }


def build_match_cache(league_cache, home_team, away_team):
    """
    Costruisce il bulk_cache per una singola partita a partire dal cache lega.
    Query leggere: solo H2H specifico + MASTER_DATA per 2 squadre.

    Returns:
        bulk_cache compatibile con engine_core / preload_match_data
    """
    t_start = time.time()
    league_normalized = league_cache["_league_normalized"]

    # 1. MASTER_DATA — estrai solo le 2 squadre dal teams già caricato
    raw_teams = league_cache["TEAMS"]
    master_map = {}
    match_teams = []

    for team in raw_teams:
        name = team.get("name")
        aliases = team.get("aliases", [])

        # Controlla se questa squadra è home o away
        is_home = (name == home_team or home_team in aliases)
        is_away = (name == away_team or away_team in aliases)

        if not is_home and not is_away:
            continue

        match_teams.append(team)
        scores = team.get("scores", {})
        stats = team.get("stats", {})
        ranking = team.get("ranking", {})

        h_played = ranking.get("homeStats", {}).get("played", 1)
        a_played = ranking.get("awayStats", {}).get("played", 1)
        h_ppg = ranking.get("homePoints", 0) / h_played if h_played > 0 else 0
        a_ppg = ranking.get("awayPoints", 0) / a_played if a_played > 0 else 0

        team_entry = {
            "power": scores.get("home_power") if is_home else scores.get("away_power"),
            "attack": scores.get("attack_home") if is_home else scores.get("attack_away"),
            "defense": scores.get("defense_home") if is_home else scores.get("defense_away"),
            "motivation": stats.get("motivation", 10.0),
            "strength_score": stats.get("strengthScore09", 5.0),
            "reliability": stats.get("reliability", 5.0) or scores.get("reliability", 5.0),
            "rating_stored": team.get("rating_5_25"),
            "ppg_home": h_ppg,
            "ppg_away": a_ppg,
            "formation": team.get("formation")
        }

        master_map[name] = team_entry
        for alias in aliases:
            master_map[alias] = team_entry

    # 2. H2H SPECIFICO (query leggera — aggregation su indice)
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

    # 3. H2H STORICO (query leggera — find_one)
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
            over25_count = sum(1 for m in played_matches if _safe_total_goals(m) > 2.5)
            gg_count = sum(1 for m in played_matches if _safe_both_scored(m))
            total_played = len(played_matches)
            h2h_historical_stats = {
                'total_matches': total_played,
                'over25_pct': round(over25_count / total_played * 100, 2) if total_played > 0 else 0,
                'under25_pct': round((total_played - over25_count) / total_played * 100, 2) if total_played > 0 else 0,
                'gg_pct': round(gg_count / total_played * 100, 2) if total_played > 0 else 0,
                'ng_pct': round((total_played - gg_count) / total_played * 100, 2) if total_played > 0 else 0
            }

    elapsed = time.time() - t_start

    return {
        "ROSE": league_cache["ROSE"],
        "TEAMS": league_cache["TEAMS"],  # TUTTI i team della lega (serve a motivation + value_rosa)
        "MASTER_DATA": master_map,
        "ALL_ROUNDS": league_cache["ALL_ROUNDS"],
        "MATCH_H2H": h2h_match_data,
        "LEAGUE_STATS": league_cache["LEAGUE_STATS"],
        "H2H_HISTORICAL": h2h_historical_stats
    }


# ==================== Helper ====================
def _safe_total_goals(m):
    try:
        score = m['score'].split('d.t.s.')[0].strip()
        gh, ga = map(int, score.split(':'))
        return gh + ga
    except:
        return 0

def _safe_both_scored(m):
    try:
        score = m['score'].split('d.t.s.')[0].strip()
        gh, ga = map(int, score.split(':'))
        return gh > 0 and ga > 0
    except:
        return False
