import pymongo
from datetime import datetime

# CONFIGURAZIONE DB
MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/pup_pals_db?retryWrites=true&w=majority"

client = pymongo.MongoClient(MONGO_URI)
db = client["pup_pals_db"]
teams = db["teams"]

def safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

def main():
    print("🏗  Costruzione/aggiornamento stats.ranking_c da ranking (home/away) per tutte le leghe...")

    # Prendiamo le squadre che hanno già ranking home/away
    cursor = teams.find({
        "ranking.homePoints": {"$exists": True},
        "ranking.awayPoints": {"$exists": True},
        "ranking.homeStats.played": {"$exists": True},
        "ranking.awayStats.played": {"$exists": True},
        "league": {"$exists": True},
    })

    # Raggruppa per lega
    leagues = {}
    for team in cursor:
        league = team.get("league")
        if not league:
            continue
        leagues.setdefault(league, []).append(team)

    total_updated = 0

    for league, league_teams in leagues.items():
        print(f"\n🏆 {league}")

        agg = []
        for t in league_teams:
            r = t.get("ranking", {})
            h_stats = r.get("homeStats", {})
            a_stats = r.get("awayStats", {})

            home_pts = safe_int(r.get("homePoints", 0))
            away_pts = safe_int(r.get("awayPoints", 0))
            total_pts = home_pts + away_pts

            played_home = safe_int(h_stats.get("played", 0))
            played_away = safe_int(a_stats.get("played", 0))
            total_played = played_home + played_away

            gf_home = safe_int(h_stats.get("goalsFor", 0))
            gf_away = safe_int(a_stats.get("goalsFor", 0))
            ga_home = safe_int(h_stats.get("goalsAgainst", 0))
            ga_away = safe_int(a_stats.get("goalsAgainst", 0))

            gf_total = gf_home + gf_away
            ga_total = ga_home + ga_away
            goal_diff = gf_total - ga_total

            agg.append({
                "team": t,
                "points": total_pts,
                "played": total_played,
                "gf": gf_total,
                "ga": ga_total,
                "gd": goal_diff,
            })

        if not agg:
            print("   ℹ️ Nessuna squadra con ranking valido, salto.")
            continue

        # Ordiniamo per punti desc, poi differenza reti, poi nome
        agg.sort(
            key=lambda x: (
                -x["points"],
                -x["gd"],
                x["team"].get("name", "")
            )
        )

        now_str = datetime.utcnow().strftime("%Y-%m-%d")
        updated_league = 0

        for pos, info in enumerate(agg, start=1):
            t = info["team"]
            pts = info["points"]
            played = info["played"]
            gf = info["gf"]
            ga = info["ga"]

            ranking_c = {
                "position": pos,
                "played": played,
                "wins": 0,          # non li abbiamo qui, ma non servono per la motivazione
                "draws": 0,
                "losses": 0,
                "goalsFor": gf,
                "goalsAgainst": ga,
                "points": pts,
                "league": league,
                "source": "soccerstats_aggregate",
                "lastUpdated": now_str,
            }

            teams.update_one(
                {"_id": t["_id"]},
                {"$set": {"stats.ranking_c": ranking_c}}
            )
            updated_league += 1
            total_updated += 1

            print(
                f"   ✅ {t.get('name','???')[:20]:<20} | pos={pos:2d} pts={pts:3d} "
                f"| played={played:2d} gf={gf:3d} ga={ga:3d}"
            )

        print(f"   🔄 Aggiornate {updated_league} squadre in {league}.")

    print(f"\n✅ Completato. Creati/aggiornati stats.ranking_c per {total_updated} squadre.")

if __name__ == "__main__":
    main()
