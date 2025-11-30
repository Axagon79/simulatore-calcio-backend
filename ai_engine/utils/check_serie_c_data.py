import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

teams = db["teams"]
avail = db["players_availability_tm"]

print("🔍 CHECK DATI SERIE C")
print("=" * 60)

gironi = ["ITA3A", "ITA3B", "ITA3C"]
league_names = ["Serie C - Girone A", "Serie C - Girone B", "Serie C - Girone C"]

for i, girone in enumerate(gironi):
    print(f"\n🏆 SERIE C - {girone}")
    print("-" * 40)
    
    # SQUADRE - cerca per league_name
    league_name = league_names[i]
    team_count = teams.count_documents({"league": league_name})
    print(f"📊 Squadre (league='{league_name}'): {team_count}")
    
    # STRENGTH SCORES
    strength_stats = teams.aggregate([
        {"$match": {"league": league_name}},
        {"$group": {
            "_id": None,
            "min_strength": {"$min": "$stats.strengthScore09"},
            "max_strength": {"$max": "$stats.strengthScore09"},
            "avg_strength": {"$avg": "$stats.strengthScore09"}
        }}
    ])
    for stat in strength_stats:
        print(f"⭐ StrengthScore09: {stat.get('min_strength',0):.2f} - {stat.get('max_strength',0):.2f} (media: {stat.get('avg_strength',0):.2f})")
    
    # DISPONIBILITÀ GIOCATORI - cerca per league_code
    avail_count = avail.count_documents({"league_code": girone})
    print(f"👥 Giocatori availability_tm (league_code='{girone}'): {avail_count}")
    
    # TOP 5 SQUADRE per strength
    top_teams = teams.find({"league": league_name}).sort("stats.strengthScore09", -1).limit(5)
    print("🏅 TOP 5:")
    for team in top_teams:
        name = team.get("name", "N/D")
        strength = team.get("stats", {}).get("strengthScore09", 0)
        print(f"   {strength:.2f} - {name}")
    
    print()