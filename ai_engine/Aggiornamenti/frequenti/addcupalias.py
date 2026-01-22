import sys
import os
from pathlib import Path

# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

print("\n=== PARTITE CHAMPIONS LEAGUE ===")
matches = list(db['matches_champions_league'].find({}).limit(5))
for m in matches:
    print(f"{m['home_team']} vs {m['away_team']}")

print("\n=== PARTITE EUROPA LEAGUE ===")
matches = list(db['matches_europa_league'].find({}).limit(5))
for m in matches:
    print(f"{m['home_team']} vs {m['away_team']}")
