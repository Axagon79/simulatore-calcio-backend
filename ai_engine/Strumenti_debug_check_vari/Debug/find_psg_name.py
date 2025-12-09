import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir)) 
sys.path.append(r"C:\Progetti\simulatore-calcio-backend\ai_engine") 

try:
    from config import db
    print(f"✅ DB Connesso")
except: sys.exit(1)

print("\n🔍 CERCO SQUADRE CHE POSSONO ESSERE IL PSG...")

# Cerca qualsiasi squadra che contiene "Paris", "Saint", "Germain" o "PSG"
candidates = db.teams.find({
    "$or": [
        {"name": {"$regex": "Paris", "$options": "i"}},
        {"name": {"$regex": "Saint", "$options": "i"}},
        {"name": {"$regex": "Germain", "$options": "i"}},
        {"name": {"$regex": "PSG", "$options": "i"}}
    ]
})

found = False
for team in candidates:
    print(f"   👉 Trovato: '{team['name']}' (ID: {team['_id']})")
    found = True

if not found:
    print("   ❌ Nessuna squadra trovata con quei nomi. Molto strano!")
