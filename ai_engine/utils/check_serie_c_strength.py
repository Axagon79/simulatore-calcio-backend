import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

teams = db["teams"]

print("🔍 STRENGTH SCORE SERIE C GIRON A:")
teams_serie_c = teams.find({"league": "Serie C - Girone A"}, 
                          {"name": 1, "strengthScore09": 1, "stats.position": 1}).sort("stats.position", 1).limit(20)

for team in teams_serie_c:
    name = team["name"]
    strength = team.get("strengthScore09", "MANCANTE")
    pos = team.get("stats", {}).get("position", "?")
    print(f"{pos:2}. {name:<25} | strengthScore09: {strength}")