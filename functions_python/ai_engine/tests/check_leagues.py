import os
import sys
from config import db

# --- CONFIGURAZIONE ---
standings_col = db['classifiche']
matches_col = db['h2h_by_round']

def check_league_names():
    print("🕵️  CONFRONTO NOMI CAMPIONATI")
    print("-" * 50)

    # 1. Nomi nello Scraper (Transfermarkt)
    scraper_leagues = set()
    cursor = standings_col.find({})
    for doc in cursor:
        scraper_leagues.add(doc['league'])
        
    print(f"🌍 Campionati scaricati (Scraper):")
    for l in sorted(scraper_leagues):
        print(f"   - {l}")

    print("-" * 50)

    # 2. Nomi nel Tuo DB (Partite)
    db_leagues = set()
    cursor = matches_col.find({})
    for doc in cursor:
        # Qui cerchiamo di capire come chiami il campionato
        # Prova a prendere 'league_name', o 'league', o 'league_id'
        name = doc.get('league_name') or doc.get('league') or "NOME_NON_TROVATO"
        db_leagues.add(str(name))

    print(f"🗄️  Campionati nel tuo DB (Partite):")
    for l in sorted(db_leagues):
        print(f"   - {l}")

    print("-" * 50)
    print("Se i nomi sopra sono diversi (es. 'Serie A' vs 'Italia - Serie A'),")
    print("lo script di iniezione non funzionerà mai senza una mappa.")

if __name__ == "__main__":
    check_league_names()