import os
import sys
from config import db

# --- CONFIGURAZIONE ---
matches_col = db['h2h_by_round']

def check_existing_keys():
    print("🕵️  ANALISI DATABASE: Controllo chiavi esistenti in h2h_data...")
    
    found_keys = set() # Usiamo un set per non avere duplicati
    matches_checked = 0
    
    # Prende tutti i documenti (tutte le giornate)
    cursor = matches_col.find({})
    
    for round_doc in cursor:
        matches = round_doc.get('matches', [])
        
        for match in matches:
            h2h = match.get('h2h_data')
            
            # Se esiste h2h_data, guardiamo cosa c'è dentro
            if h2h and isinstance(h2h, dict):
                matches_checked += 1
                # Aggiunge tutte le chiavi trovate al nostro elenco
                for key in h2h.keys():
                    found_keys.add(key)

    print(f"\n📊 REPORT ANALISI")
    print(f"   Partite controllate: {matches_checked}")
    print(f"   Chiavi trovate dentro h2h_data: \n")
    
    if not found_keys:
        print("   [NESSUNA CHIAVE TROVATA] - h2h_data è vuoto o non esiste.")
    else:
        for k in sorted(found_keys):
            print(f"   - {k}")

    # VERIFICA CONFLITTI
    nuovi_campi = ['home_rank', 'home_points', 'away_rank', 'away_points']
    conflitti = [k for k in nuovi_campi if k in found_keys]
    
    print("\n⚖️  VERDETTO:")
    if conflitti:
        print(f"⚠️  ATTENZIONE! Questi nomi esistono già: {conflitti}")
        print("    Se prosegui, i vecchi valori di questi campi verranno SOVRASCRITTI.")
    else:
        print("✅  VIA LIBERA! I nomi 'rank' e 'points' sono nuovi.")
        print("    Puoi procedere con l'iniezione senza cancellare nessun dato esistente (come Lucifero).")

if __name__ == "__main__":
    check_existing_keys()