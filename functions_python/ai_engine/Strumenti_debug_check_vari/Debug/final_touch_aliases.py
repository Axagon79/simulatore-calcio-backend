import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir)) 
sys.path.append(r"C:\Progetti\simulatore-calcio-backend\ai_engine") 

try:
    from config import db
    print(f"✅ DB Connesso")
except: sys.exit(1)

def sniper_fix():
    print("🎯 AVVIO FIX CHIRURGICO...")

    # 1. FIX JUVENTUS NEXT GEN
    # Sappiamo che nel DB si chiama "Juventus U23" (visto dal log precedente)
    print("\n🔹 Fix Juventus U23...")
    res = db.teams.update_one(
        {"name": "Juventus U23"},
        {"$addToSet": {"aliases": {"$each": ["juve next gen", "next gen", "juventus next gen"]}}}
    )
    if res.modified_count > 0: print("   ✅ Aggiunti alias 'next gen' a Juventus U23")
    else: print("   zzz Alias Next Gen già presenti o squadra non trovata.")

    # 2. FIX VITORIA SC
    # Sappiamo che nel DB c'è una squadra che ha matchato con "Guimaraes"
    print("\n🔹 Fix Vitoria...")
    team_v = db.teams.find_one({"name": {"$regex": "Guimaraes", "$options": "i"}})
    if team_v:
        res = db.teams.update_one(
            {"_id": team_v["_id"]},
            {"$addToSet": {"aliases": "vitoria"}} # Aggiungiamo l'alias corto
        )
        print(f"   ✅ Aggiunto alias 'vitoria' a: {team_v['name']}")
    else:
        print("   ⚠️  Nessuna squadra 'Guimaraes' trovata (Strano, prima l'aveva trovata).")

    # 3. CACCIA AL MILAN FUTURO
    print("\n🔹 Caccia al Milan Futuro...")
    # Cerchiamo tutto ciò che contiene "Milan" ma NON è "Inter"
    candidates = db.teams.find({
        "$and": [
            {"name": {"$regex": "Milan", "$options": "i"}},
            {"name": {"$not": {"$regex": "Inter", "$options": "i"}}} # Escludiamo l'Inter
        ]
    })
    
    found_u23 = False
    for t in candidates:
        print(f"   🔎 Trovato nel DB: '{t['name']}' (Alias attuali: {t.get('aliases', [])})")
        
        # Se troviamo qualcosa che sembra l'U23, lo fixiamo al volo
        if "U23" in t['name'] or "Futuro" in t['name'] or "B" in t['name']:
            db.teams.update_one({"_id": t["_id"]}, {"$addToSet": {"aliases": "milan futuro"}})
            print(f"      ✨ AUTO-FIX: Aggiunto alias 'milan futuro' a '{t['name']}'")
            found_u23 = True

    if not found_u23:
        print("\n   ⚠️  ATTENZIONE: Non vedo nessuna squadra 'Milan U23' o 'Futuro'.")
        print("      Se il Milan Futuro è stato creato quest'anno, forse manca proprio nel DB delle squadre!")

if __name__ == "__main__":
    sniper_fix()
