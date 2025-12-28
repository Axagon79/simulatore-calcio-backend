import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir)) 
sys.path.append(r"C:\Progetti\simulatore-calcio-backend\ai_engine") 

try:
    from config import db
    print(f"✅ DB Connesso")
except: sys.exit(1)

def apply_fix():
    print("🚑 FIX FINALE PSG...")
    
    # Cerchiamo la squadra che si chiama ESATTAMENTE "PSG"
    team = db.teams.find_one({"name": "PSG"})
    
    if team:
        # Aggiungiamo questi alias fondamentali
        # Se il sito scrive "Paris Saint Germain", l'alias "paris" farà scattare il match
        aliases = ["paris", "paris saint germain", "paris sg"]
        
        db.teams.update_one(
            {"_id": team["_id"]},
            {"$addToSet": {"aliases": {"$each": aliases}}}
        )
        print(f"✅ FATTO! Aggiornato '{team['name']}' con alias: {aliases}")
    else:
        print("❌ Assurdo, non la trovo nemmeno ora.")

if __name__ == "__main__":
    apply_fix()
