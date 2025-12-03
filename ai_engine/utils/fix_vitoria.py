import sys
import os

# --- FIX PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
root_dir = os.path.dirname(parent_dir)
sys.path.insert(0, root_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)

from config import db

# AGGIUNGIAMO L'ALIAS MANCANTE
result = db.teams.update_one(
    {"name": "Guimaraes"},
    {"$addToSet": {"aliases": "Vit. Guimarães"}} 
)

if result.matched_count > 0:
    print("✅ Alias 'Vit. Guimarães' aggiunto a Guimaraes!")
else:
    print("⚠️ Squadra 'Guimaraes' non trovata. Sicuro del nome?")
