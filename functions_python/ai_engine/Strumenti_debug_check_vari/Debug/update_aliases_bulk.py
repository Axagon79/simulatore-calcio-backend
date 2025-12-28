import sys
import os

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir)) 
project_root = os.path.dirname(ai_engine_dir)
sys.path.append(current_dir)
sys.path.append(r"C:\Progetti\simulatore-calcio-backend\ai_engine") 

try:
    from config import db
    print(f"✅ DB Connesso: {db.name}")
except ImportError:
    print("❌ Errore critico: Impossibile trovare config.py")
    sys.exit(1)

# --- LISTA OTTIMIZZATA GIRO 2 ---
replacements = {
    # --- ITALIANIZZAZIONI (Probabilmente nel tuo DB sono in italiano) ---
    "Barcellona": "barcellona",
    "Siviglia": "siviglia",
    "Magonza": "magonza",
    "Colonia": "colonia",
    "Friburgo": "friburgo",
    "Stoccarda": "stoccarda",
    "Lipsia": "lipsia",
    "Marsiglia": "marsiglia",
    "Nizza": "nizza",
    
    # --- CASI SPECIFICI RIMASTI ---
    "Vitoria": "vitoria", # Riprova generico
    "Guimaraes": "vitoria guimaraes", # Se si chiama Guimaraes
    
    # --- UNDER 23 (Proviamo chiavi diverse) ---
    "Juve Next": "juventus",
    "Juventus Next": "juventus",
    "Juventus U23": "juventus",
    "Milan Futuro": "milan",
    "Milan U23": "milan",
    
    # --- ERRORI DI BATTITURA O VARIANTI ---
    "Sudtirol": "sudtirol", # Riprova caso maiuscolo/minuscolo
    "Südtirol": "sudtirol"
}


def execute_migration():
    print("🚀 Avvio Migrazione Alias (Giro 2)...")
    count = 0
    
    # Usiamo direttamente replacements senza unire nulla
    for db_name_hint, alias_to_add in replacements.items():
        alias_clean = alias_to_add.lower().strip()
        
        # Cerca squadre che contengono la chiave nel nome (es. "Bayern" trova "FC Bayern Munchen")
        team = db.teams.find_one({"name": {"$regex": f"{db_name_hint}", "$options": "i"}})
        
        if team:
            res = db.teams.update_one(
                {"_id": team["_id"]},
                {"$addToSet": {"aliases": alias_clean}}
            )
            
            if res.modified_count > 0:
                print(f"   ✅ {team['name']}: Aggiunto alias '{alias_clean}'")
                count += 1
            else:
                print(f"   zzz {team['name']}: Alias '{alias_clean}' già presente.")
        else:
            print(f"   ⚠️  NON TROVATA: Nessuna squadra contiene '{db_name_hint}'")

    print(f"\n🏁 Operazione completata. Aggiornate {count} squadre.")

if __name__ == "__main__":
    execute_migration()
