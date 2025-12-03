from datetime import datetime, timedelta
from config import db

def check_database_health():
    """
    Controlla quante partite hanno dati H2H scaduti o mancanti.
    Non scarica nulla, conta solo.
    """
    print("\n🏥 ESEGUO CHECK-UP DATABASE...")
    
    col = db["h2h_by_round"]
    
    # Impostiamo la data limite (oggi - 30 giorni)
    giorni_limite = 30
    data_limite = datetime.now() - timedelta(days=giorni_limite)
    
    # Contatori
    partite_totali = 0
    partite_scadute = 0
    leghe_da_aggiornare = set() # Usiamo un set per non avere duplicati
    
    # Prendiamo solo i campi necessari per essere veloci
    cursor = col.find({}, {"matches": 1, "league": 1})
    
    for doc in cursor:
        matches = doc.get("matches", [])
        nome_lega = doc.get("league", "Sconosciuto")
        
        for m in matches:
            partite_totali += 1
            h2h = m.get("h2h_data")
            
            stato_critico = False
            
            # Caso 1: Dati mai scaricati
            if not h2h:
                stato_critico = True
            # Caso 2: Dati presenti ma vecchi
            elif isinstance(h2h.get("last_check"), datetime):
                if h2h["last_check"] < data_limite:
                    stato_critico = True
            # Caso 3: Vecchio formato dati (senza data)
            elif not h2h.get("last_check"):
                 stato_critico = True
                 
            if stato_critico:
                partite_scadute += 1
                leghe_da_aggiornare.add(nome_lega)

    # --- REPORT PER L'ADMIN ---
    print("-" * 50)
    percentuale = 0
    if partite_totali > 0:
        percentuale = (partite_scadute / partite_totali) * 100
        
    if partite_scadute == 0:
        print("✅ TUTTO VERDE: Il database è aggiornatissimo!")
    elif percentuale < 20:
        print(f"⚠️  ATTENZIONE LIEVE: Ci sono {partite_scadute} partite scadute.")
        print("   Il 'Portiere' può gestirle tranquillamente al bisogno.")
    else:
        print(f"🚨 ALLARME ROSSO: {partite_scadute} partite scadute ({percentuale:.1f}%)!")
        print("   Il sistema sta invecchiando.")
        print("   Leghe critiche:", ", ".join(list(leghe_da_aggiornare)[:5]), "...")
        print("\n💡 CONSIGLIO: Lancia lo script 'Matrix' stanotte prima di dormire.")
    print("-" * 50 + "\n")

# Se vuoi lanciarlo da solo per provare:
if __name__ == "__main__":
    check_database_health()
