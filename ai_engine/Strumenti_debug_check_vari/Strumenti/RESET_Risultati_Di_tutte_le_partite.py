import os
import sys

# Percorsi per configurazione
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(BASE_DIR)

try:
    from config import db
    print("✅ Connessione al database caricata correttamente")
except ImportError:
    print("❌ Errore: Non trovo config.py")
    sys.exit(1)

def reset_risultati_e_stato():
    """
    Resetta selettivamente SOLO i campi:
    - real_score
    - status
    SENZA toccare altri dati
    """
    h2h_collection = db['h2h_by_round']
    
    try:
        documents = list(h2h_collection.find({}))
    except Exception as e:
        print(f"❌ Errore di connessione: {e}")
        return

    print(f"🧹 Reset selettivo risultati e stato su {len(documents)} giornate...")

    total_reset = 0
    league_reset = {}
    
    for doc in documents:
        matches_array = doc.get('matches', [])
        modificato = False
        
        for match in matches_array:
            # Memorizza valori originali per logging
            old_score = match.get('real_score')
            old_status = match.get('status')
            
            # RESETTA SOLO QUESTI DUE CAMPI
            if 'real_score' in match:
                match['real_score'] = "-"  # Reset a trattino
                modificato = True
            
            if 'status' in match:
                match['status'] = "Scheduled"  # Reset a programmata
                modificato = True
            
            # Log dettagliato se c'era qualcosa
            if modificato and (old_score or old_status):
                league = doc.get('league', 'Unknown')
                league_reset[league] = league_reset.get(league, 0) + 1
                total_reset += 1
                
                if total_reset <= 5:  # Log prime 5 modifiche
                    home = match.get('home', '?')
                    away = match.get('away', '?')
                    print(f"   ↳ {home} vs {away}: {old_score} ({old_status}) → - (Scheduled)")

        # Salva solo se modificato
        if modificato:
            h2h_collection.update_one(
                {"_id": doc['_id']},
                {"$set": {"matches": matches_array}}
            )

    # Report finale
    print(f"\n📊 REPORT RESET RISULTATI:")
    print(f"   Totale match resettati: {total_reset}")
    
    if league_reset:
        print(f"   Per lega:")
        for league, count in league_reset.items():
            print(f"     • {league}: {count} match")
    
    print("\n✅ Reset COMPLETAMENTE SICURO: Solo real_score e status modificati.")
    print("   ❌ Non toccati: date_obj, odds, h2h_data, tm_id, quote, classifiche")

if __name__ == "__main__":
    # Chiedi conferma per sicurezza
    print("⚠️  ATTENZIONE: Questo script resetta SOLO risultati e stato delle partite")
    print("   Verranno impostati: real_score='-' e status='Scheduled'")
    print("   Tutti gli altri dati (date, quote, h2h_data, etc.) RESTANO INTATTI")
    
    conferma = input("\n❓ Continuare? (scrivi 'SI' per confermare): ")
    
    if conferma.strip().upper() == "SI":
        reset_risultati_e_stato()
    else:
        print("❌ Operazione annullata dall'utente")