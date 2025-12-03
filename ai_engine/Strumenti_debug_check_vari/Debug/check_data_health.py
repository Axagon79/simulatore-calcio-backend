import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

teams = db["teams"]

# Leghe per cui vuoi controllare alias Transfermarkt
LEAGUES_NEED_TM = [
    "Serie A",
    "Serie B",
    "Serie C - Girone A",
    "Serie C - Girone B",
    "Serie C - Girone C",
    "Premier League",
    "La Liga",
    "Bundesliga",
    "Ligue 1",
    "Eredivisie",
    "Liga Portugal",
]


def check_duplicates_name_league():
    print("🔍 [1] Cerco doppioni per (name, league)...")
    pipeline = [
        {
            "$group": {
                "_id": {"name": "$name", "league": "$league"},
                "ids": {"$push": "$_id"},
                "count": {"$sum": 1},
            }
        },
        {
            "$match": {
                "count": {"$gt": 1}
            }
        },
    ]
    dups = list(teams.aggregate(pipeline))
    if not dups:
        print("   ✅ Nessun doppione (name+league) trovato.")
    else:
        for grp in dups:
            key = grp["_id"]
            ids = grp["ids"]
            print(f"\n   ⚠️ Doppione: name='{key['name']}', league='{key['league']}' (count={len(ids)})")
            for _id in ids:
                print(f"      - _id = { _id }")


def check_missing_or_zero_stats():
    print("\n🔍 [2] Cerco squadre con marketValue/avgAge mancanti o a zero...")
    q_missing = {
        "$or": [
            {"stats.marketValue": {"$exists": False}},
            {"stats.avgAge": {"$exists": False}},
            {"stats.marketValue": {"$lte": 0}},
            {"stats.avgAge": {"$lte": 0}},
        ]
    }
    cur = teams.find(q_missing)
    problems = list(cur)
    if not problems:
        print("   ✅ Tutte le squadre hanno marketValue e avgAge > 0.")
        return

    by_league = {}
    for t in problems:
        league = t.get("league", "??")
        by_league.setdefault(league, []).append(t)

    for league, items in by_league.items():
        print(f"\n   ⚠️ {league} - {len(items)} squadre con dati mancanti/zero:")
        for t in items:
            name = t.get("name", "???")
            mv = t.get("stats", {}).get("marketValue")
            age = t.get("stats", {}).get("avgAge")
            print(f"      - {name} | marketValue={mv} | avgAge={age}")


def check_outliers_basic():
    print("\n🔍 [3] Cerco valori sospetti (età fuori range, valori rosa troppo bassi)...")
    leagues = {}
    cur = teams.find({
        "stats.marketValue": {"$exists": True},
        "stats.avgAge": {"$exists": True},
    })
    for t in cur:
        league = t.get("league")
        if not league:
            continue
        leagues.setdefault(league, []).append(t)

    for league, league_teams in leagues.items():
        ages = [t["stats"].get("avgAge", 0) for t in league_teams]
        vals = [t["stats"].get("marketValue", 0) for t in league_teams]

        ages = [a for a in ages if isinstance(a, (int, float)) and a > 0]
        vals = [v for v in vals if isinstance(v, (int, float)) and v > 0]

        if not ages or not vals:
            continue

        min_val, max_val = min(vals), max(vals)
        low_val_threshold = min_val * 0.5  # troppo sotto il minimo reale -> sospetto

        bad_age = []
        bad_val = []

        for t in league_teams:
            name = t.get("name", "???")
            stats = t.get("stats", {})
            age = stats.get("avgAge")
            val = stats.get("marketValue")

            # età fuori da [16, 40]
            if isinstance(age, (int, float)) and (age < 16 or age > 40):
                bad_age.append((name, age))

            # valore rosa negativo o molto più basso del vero minimo
            if isinstance(val, (int, float)) and val > 0 and val < low_val_threshold:
                bad_val.append((name, val))

        if not bad_age and not bad_val:
            continue

        print(f"\n   ⚠️ {league}:")
        if bad_age:
            print("      Età sospette (<16 o >40):")
            for name, age in bad_age:
                print(f"         - {name}: avgAge={age}")
        if bad_val:
            print("      Valori di mercato molto bassi (sotto 50% del minimo):")
            for name, val in bad_val:
                print(f"         - {name}: marketValue={val:,.0f}€")


def check_missing_aliases_transfermarkt():
    print("\n🔍 [4] Cerco squadre senza aliases_transfermarkt nelle leghe principali...")
    q = {
        "league": {"$in": LEAGUES_NEED_TM},
        "$or": [
            {"aliases_transfermarkt": {"$exists": False}},
            {"aliases_transfermarkt": None},
            {"aliases_transfermarkt": ""},
        ],
    }
    cur = teams.find(q)
    missing = list(cur)
    if not missing:
        print("   ✅ Tutte le squadre delle leghe selezionate hanno aliases_transfermarkt.")
        return

    by_league = {}
    for t in missing:
        league = t.get("league", "??")
        by_league.setdefault(league, []).append(t)

    for league, items in by_league.items():
        print(f"\n   ⚠️ {league} - {len(items)} squadre SENZA aliases_transfermarkt:")
        for t in items:
            print(f"      - {t.get('name', '???')} (id={t.get('_id')})")


def main():
    print("🩺 CHECK COMPLETO STATO DATI TEAMS\n")

    check_duplicates_name_league()
    check_missing_or_zero_stats()
    check_outliers_basic()
    check_missing_aliases_transfermarkt()

    print("\n✅ Fine check.")


if __name__ == "__main__":
    main()