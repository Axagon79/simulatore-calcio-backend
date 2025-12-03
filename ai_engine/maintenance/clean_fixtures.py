import sys
import os

# Setup path per config
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

def clean_empty_fixtures():
    print("🧹 Inizio pulizia collezione 'fixtures'...")
    
    col = db['fixtures']
    
    # Contiamo quanti sono prima
    total_before = col.count_documents({})
    print(f"📄 Totale documenti attuali: {total_before}")
    
    # 1. CANCELLA documenti dove homeTeam è vuoto, null o non esiste
    query_bad = {
        "$or": [
            {"homeTeam": ""},
            {"homeTeam": None},
            {"homeTeam": {"$exists": False}},
            {"awayTeam": ""},
            {"awayTeam": None}
        ]
    }
    
    bad_docs = col.count_documents(query_bad)
    print(f"⚠️ Documenti 'vuoti' o corrotti trovati: {bad_docs}")
    
    if bad_docs > 0:
        result = col.delete_many(query_bad)
        print(f"✅ Rimossi {result.deleted_count} documenti vuoti.")
    else:
        print("✅ Nessun documento vuoto da rimuovere.")
        
    # Contiamo quanti sono dopo
    total_after = col.count_documents({})
    print(f"📄 Totale documenti validi rimasti: {total_after}")

if __name__ == "__main__":
    clean_empty_fixtures()
