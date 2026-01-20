import os
import sys

# --- CONFIGURAZIONE ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR)) 
sys.path.append(PROJECT_ROOT)
sys.path.append(CURRENT_DIR)

try:
    from config import db
    print("✅ Connessione DB OK.\n")
except ImportError as e:
    print(f"❌ Errore importazione: {e}")
    sys.exit(1)

def clean_database():
    teams_col = db["teams"]
    print(f"{'='*60}")
    print(f"🧹 PULIZIA DATABASE (FIX LISTE ANNIDATE)")
    print(f"{'='*60}")
    print("Scansiono le squadre alla ricerca di formati errati (es. liste dentro liste)...")

    cursor = teams_col.find({})
    count_fixed = 0
    
    for team in cursor:
        updates = {}
        is_dirty = False
        name = team.get("name", "Sconosciuto")
        
        # --- CONTROLLO 1: ALIASES (Deve essere una lista di stringhe) ---
        aliases = team.get("aliases", [])
        if aliases and isinstance(aliases, list):
            new_aliases = []
            aliases_changed = False
            
            for item in aliases:
                # Se troviamo una lista dentro la lista (es. [['Alias']])
                if isinstance(item, list):
                    print(f"⚠️  [FIX] {name}: Trovata lista annidata in 'aliases': {item}")
                    # Appiattiamo
                    new_aliases.extend([str(x) for x in item])
                    aliases_changed = True
                else:
                    new_aliases.append(item)
            
            if aliases_changed:
                # Rimuoviamo duplicati
                updates["aliases"] = list(set(new_aliases))
                is_dirty = True

        # --- CONTROLLO 2: ALIASES_TRANSFERMARKT (Deve essere stringa) ---
        tm_alias = team.get("aliases_transfermarkt")
        if tm_alias is not None and isinstance(tm_alias, list):
            print(f"⚠️  [FIX] {name}: 'aliases_transfermarkt' è una LISTA {tm_alias} -> Converto in STRINGA")
            
            if len(tm_alias) > 0:
                # Prende il primo elemento come valore principale
                updates["aliases_transfermarkt"] = str(tm_alias[0])
                
                # Aggiunge TUTTI gli elementi agli alias normali per non perdere dati
                current_aliases = updates.get("aliases", team.get("aliases", []))
                # Assicuriamoci che current_aliases sia una lista piatta
                flat_aliases = []
                for a in current_aliases:
                    if isinstance(a, list): flat_aliases.extend(a)
                    else: flat_aliases.append(a)
                
                flat_aliases.extend([str(x) for x in tm_alias])
                updates["aliases"] = list(set(flat_aliases))
            else:
                updates["aliases_transfermarkt"] = None
            
            is_dirty = True

        # --- APPLICAZIONE FIX ---
        if is_dirty:
            try:
                teams_col.update_one({"_id": team["_id"]}, {"$set": updates})
                print(f"✅  {name} RIPARATA.")
                count_fixed += 1
            except Exception as e:
                print(f"❌  Errore nel salvare {name}: {e}")

    print("-" * 60)
    print(f"🏁 FINE. Squadre riparate: {count_fixed}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    clean_database()