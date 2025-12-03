import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

def inspect_suspicious_docs():
    print("🔍 Ispezione documenti sospetti in 'fixtures'...")
    col = db['fixtures']
    
    # Cerca documenti senza nome squadra
    query = {"homeTeam": ""}
    
    suspicious = list(col.find(query).limit(5))
    
    if not suspicious:
        print("✅ Nessun documento con homeTeam vuoto trovato.")
        return

    print(f"⚠️ Trovati {col.count_documents(query)} documenti con homeTeam vuoto.")
    print("Esempio dei primi 5:")
    
    for doc in suspicious:
        print("-" * 40)
        print(f"ID: {doc.get('_id')}")
        print(f"Date: '{doc.get('date')}'")
        print(f"League: '{doc.get('league')}'")
        print(f"Score: {doc.get('score')}") # Vediamo se c'è un risultato
        print(f"Status: {doc.get('status')}")
        print(f"Odds: {doc.get('odds')}") # Vediamo se hanno quote (improbabile)

if __name__ == "__main__":
    inspect_suspicious_docs()
