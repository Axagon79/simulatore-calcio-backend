import os
import sys
from config import db

# --- CONFIGURAZIONE ---
rankings_col = db['classifiche']

def check_results():
    print("🕵️  ANALISI QUALITÀ SCRAPING & MATCHING TEAMS")
    print("-" * 60)
    
    cursor = rankings_col.find({})
    
    total_ok = 0
    total_ko = 0
    
    for doc in cursor:
        league = doc['league']
        country = doc.get('country', '??')
        
        teams_ok = 0
        teams_ko = 0
        missing_names = []
        
        for row in doc['table']:
            # Se c'è team_id, il matching con la collezione 'teams' è riuscito
            if row.get('team_id'):
                teams_ok += 1
                total_ok += 1
            else:
                teams_ko += 1
                total_ko += 1
                missing_names.append(row['team'])
        
        # Stampa report per campionato
        status_icon = "✅" if teams_ko == 0 else "⚠️"
        print(f"{status_icon} {league} ({country})")
        print(f"   Riconosciute: {teams_ok} | Sconosciute: {teams_ko}")
        
        if missing_names:
            print(f"   ❌ Nomi non trovati in 'teams': {missing_names}")
        print("-" * 30)

    print("\n📊 RIEPILOGO TOTALE")
    print(f"Squadre collegate al DB (ID trovato): {total_ok}")
    print(f"Squadre orfane (Nessun match in teams): {total_ko}")
    
    if total_ko > 0:
        print("\n💡 CONSIGLIO: Per le squadre 'orfane', aggiungi il loro nome")
        print("   nell'array 'aliases' dentro la tua collezione 'teams'.")

if __name__ == "__main__":
    check_results()