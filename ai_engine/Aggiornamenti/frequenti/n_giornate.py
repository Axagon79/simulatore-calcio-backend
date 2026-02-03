import os
import sys
from dotenv import load_dotenv

# Fix percorsi
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path: break
    current_path = parent
sys.path.append(current_path)

from config import db

doc = db["h2h_by_round"].find_one({"league": "Brasileirão Serie A"})
if doc:
    match = doc.get("matches", [])[0]
    h2h = match.get("h2h_data", {})
    print(f"home_rank: {h2h.get('home_rank')}")
    print(f"home_points: {h2h.get('home_points')}")
    print(f"away_rank: {h2h.get('away_rank')}")
    print(f"away_points: {h2h.get('away_points')}")