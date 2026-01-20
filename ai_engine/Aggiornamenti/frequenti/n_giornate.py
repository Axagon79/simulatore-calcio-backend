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

def trova_squadre_rotte():
    print("🔍 Cerco squadre senza campo 'league'...")
    count = 0
    # Cerca documenti dove 'league' non esiste o è null o è stringa vuota
    cursor = db.teams.find({
        "$or": [
            {"league": {"$exists": False}},
            {"league": None},
            {"league": ""}
        ]
    })
    
    for team in cursor:
        print(f"❌ Squadra corrotta: {team.get('name')} (ID: {team.get('_id')})")
        count += 1
        
    if count == 0:
        print("✅ Nessuna squadra corrotta trovata.")
    else:
        print(f"⚠️ Trovate {count} squadre senza lega. Eliminale o correggile nel DB.")

if __name__ == "__main__":
    trova_squadre_rotte()