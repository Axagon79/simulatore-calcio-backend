import os
import sys

# Trova config.py
currentpath = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(currentpath, 'config.py')):
    parent = os.path.dirname(currentpath)
    if parent == currentpath:
        raise FileNotFoundError("Impossibile trovare config.py!")
    currentpath = parent
sys.path.append(currentpath)

from config import db

# Collezione h2h_by_round
col = db['h2h_by_round']

# Trova tutti i documenti del Brasileirão senza campo country
query = {
    "league": "Brasileirão Serie A",
    "country": {"$exists": False}
}

# Conta documenti da aggiornare
count = col.count_documents(query)
print(f"Documenti trovati senza campo 'country': {count}")

if count > 0:
    # Aggiorna aggiungendo il campo country
    result = col.update_many(
        query,
        {"$set": {"country": "Brazil"}}
    )

    print(f"✓ Aggiornati {result.modified_count} documenti")
    print(f"  - League: Brasileirão Serie A")
    print(f"  - Country aggiunto: Brazil")

    # Verifica
    verify = col.count_documents({"league": "Brasileirão Serie A", "country": "Brazil"})
    print(f"\n✓ Verifica: {verify} documenti ora hanno country='Brazil'")
else:
    print("Nessun documento da aggiornare (tutti hanno già il campo country)")

print("\n" + "="*60)
print("COMPLETATO - Riavvia il web simulator per vedere Brazil nel menu")
print("="*60)