from datetime import datetime
from ai_engine.Cestino.scraper_precedenti_h2h import get_h2h_scores  # Importa il Musicista
from config import db  # Importa il Database

def ottieni_dati_partita(home, away):
    """
    Questa funzione è la gestione dei dati per il h2h tra due squadre.
    1. Cerca nel DB.
    2. Se il dato è fresco (< 30 gg), te lo dà subito.
    3. Se è vecchio o manca, chiama il Musicista, aggiorna e poi te lo dà.
    """
    
    print(f"🔍 Gestore Dati: Cerco dati per {home} - {away}...")
    
    # 1. CERCHIAMO LA PARTITA NEL DB (nella collezione delle giornate o in una dedicata)
    # Nota: Qui assumiamo che tu cerchi dentro una struttura o una collezione specifica.
    # Per semplicità, immaginiamo di cercare in una collezione di "cache" o direttamente nei match.
    
    # Esempio: Cerchiamo se esiste già un documento H2H salvato per questa coppia
    # (Potresti dover adattare la query in base a come hai strutturato il DB esatto)
    cache_col = db["h2h_cache"] 
    
    # Cerchiamo la coppia (indipendentemente da chi gioca in casa/fuori per lo storico)
    dati_salvati = cache_col.find_one({
        "$or": [
            {"team_a": home, "team_b": away},
            {"team_a": away, "team_b": home}
        ]
    })

    bisogna_scaricare = False

    if not dati_salvati:
        print("❌ Dati non presenti nel database.")
        bisogna_scaricare = True
    else:
        last_check = dati_salvati.get("last_check")
        if not last_check:
            bisogna_scaricare = True
        else:
            giorni_passati = (datetime.now() - last_check).days
            print(f"📅 Dati vecchi di {giorni_passati} giorni.")
            
            if giorni_passati >= 30:
                print("⚠️ Dati SCADUTI ( > 30 giorni).")
                bisogna_scaricare = True
            else:
                print("✅ Dati FRESCHI. Uso quelli in memoria.")
                return dati_salvati["scores"] # Ritorna subito i dati! Strada A

    # 2. SE SIAMO QUI, DOBBIAMO CHIAMARE IL MUSICISTA (Strada B)
    if bisogna_scaricare:
        print("🎻 Chiamo il MUSICISTA per scaricare i dati aggiornati...")
        
        try:
            # Chiamata allo scraper (Musicista)
            nuovi_dati = get_h2h_scores(home, away)
            
            # Salviamo nel DB per la prossima volta
            record = {
                "team_a": home,
                "team_b": away,
                "scores": nuovi_dati,
                "last_check": datetime.now()
            }
            
            # Usiamo update_one con upsert=True per salvare o aggiornare
            cache_col.update_one(
                {"team_a": home, "team_b": away},
                {"$set": record},
                upsert=True
            )
            
            print("💾 Dati salvati nel DB.")
            return nuovi_dati
            
        except Exception as e:
            print(f"❌ Errore durante lo scaricamento: {e}")
            return None
