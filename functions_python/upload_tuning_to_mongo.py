# upload_tuning_to_mongo.py
# Script per caricare tuning_settings.json su MongoDB

import json
import os
import sys

# Aggiungi vari path possibili per trovare config
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

sys.path.insert(0, current_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, os.path.join(current_dir, "ai_engine"))
sys.path.insert(0, os.path.join(current_dir, "ai_engine", "engine"))

try:
    from config import db
    print("✅ Config importato!")
except ImportError as e:
    print(f"❌ Errore import config: {e}")
    print(f"   Cercato in: {sys.path[:5]}")
    print("\n   Dimmi dove si trova il file config.py!")
    exit(1)

TUNING_FILE = os.path.join(current_dir, "ai_engine", "engine", "tuning_settings.json")

def upload_tuning():
    """Carica tuning_settings.json su MongoDB nella collection 'tuning_settings'"""
    
    # 1. Leggi il file JSON locale
    if not os.path.exists(TUNING_FILE):
        print(f"❌ File non trovato: {TUNING_FILE}")
        return False
    
    with open(TUNING_FILE, "r", encoding="utf-8") as f:
        tuning_data = json.load(f)
    
    print(f"✅ File caricato: {len(tuning_data)} sezioni trovate")
    print(f"   Sezioni: {list(tuning_data.keys())}")
    
    # 2. Salva su MongoDB (upsert - aggiorna se esiste, crea se non esiste)
    collection = db['tuning_settings']
    
    # Usiamo un documento unico con _id fisso
    result = collection.update_one(
        {"_id": "main_config"},
        {"$set": {"config": tuning_data}},
        upsert=True
    )
    
    if result.upserted_id:
        print("✅ Documento CREATO su MongoDB")
    else:
        print(f"✅ Documento AGGIORNATO su MongoDB (modified: {result.modified_count})")
    
    # 3. Verifica
    saved = collection.find_one({"_id": "main_config"})
    if saved:
        print(f"✅ Verifica OK - Sezioni salvate: {list(saved['config'].keys())}")
    
    return True


if __name__ == "__main__":
    print("\n🔧 UPLOAD TUNING SETTINGS SU MONGODB\n")
    upload_tuning()
    print("\n✅ FATTO!")