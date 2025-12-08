import os
import sys
from datetime import datetime
import re

# --- FIX PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) 

if project_root not in sys.path: sys.path.insert(0, project_root)

try:
    from config import db
except ImportError as e:
    print(f"❌ ERRORE: Non trovo il database. {e}")
    sys.exit(1)

def get_round_number(round_name):
    try:
        num = re.search(r'\d+', str(round_name))
        return int(num.group()) if num else 0
    except: return 0

def cleaner_menu():
    print("\n🧹 PULITORE DATABASE (Database Cleaner)")
    print("="*40)
    
    # 1. SCELTA TARGET
    print("Su quale collezione vuoi operare?")
    print("   [1] SANDBOX (Test)")
    print("   [2] UFFICIALE (Produzione)")
    
    try:
        choice = input("   Scelta: ").strip()
        if choice == '2':
            coll_name = 'predictions_official'
        else:
            coll_name = 'predictions_sandbox'
    except: return

    collection = db[coll_name]
    count = collection.count_documents({})
    
    print(f"\n📂 Collezione: {coll_name}")
    print(f"📄 Documenti attuali: {count}")
    
    if count == 0:
        print("✅ Il database è già vuoto.")
        return

    # 2. SCELTA AZIONE
    print("\nCosa vuoi eliminare?")
    print("   [1] L'ULTIMA Giornata inserita (Undo)")
    print("   [2] Una Giornata SPECIFICA (es. Serie A - Giornata 15)")
    print("   [3] Un RANGE di giornate (es. dalla 10 alla 12)")
    print("   [4] TUTTO (Reset Totale)")
    print("   [0] Esci")

    action = input("   Azione: ").strip()

    if action == '0': return

    # --- AZIONE 1: ULTIMA GIORNATA ---
    if action == '1':
        # Trova l'ultimo timestamp inserito
        last_entry = collection.find_one(sort=[("meta.timestamp", -1)])
        if not last_entry: return
        
        target_league = last_entry['meta']['league']
        # Risaliamo al nome della giornata tramite la data o facciamo una query approssimativa?
        # Meglio cancellare per data di inserimento (timestamp), è più sicuro per l'Undo.
        last_time = last_entry['meta']['timestamp']
        
        # Conta quanti record hanno quel timestamp (o molto vicino)
        # Usiamo un filtro per cancellare tutto ciò che è stato inserito negli ultimi 5 minuti rispetto all'ultimo record
        # Oppure cancelliamo proprio per "meta.date" e "meta.league" dell'ultimo record.
        target_date = last_entry['meta']['date']
        
        query = {
            "meta.league": target_league,
            "meta.date": target_date
        }
        del_count = collection.count_documents(query)
        
        print(f"\nStai per cancellare {del_count} partite di {target_league} del {str(target_date)[:10]}.")
        if input("Confermi? (S/N): ").upper() == 'S':
            res = collection.delete_many(query)
            print(f"✅ Cancellati {res.deleted_count} record.")

    # --- AZIONE 2: GIORNATA SPECIFICA ---
    elif action == '2':
        # Mostra le leghe disponibili
        leagues = collection.distinct("meta.league")
        print("\nLeghe disponibili:")
        for i, l in enumerate(leagues): print(f"{i+1}. {l}")
        l_idx = int(input("Scegli Lega: ")) - 1
        sel_league = leagues[l_idx]
        
        # Mostra le date disponibili per quella lega
        dates = collection.distinct("meta.date", {"meta.league": sel_league})
        dates.sort(reverse=True)
        print(f"\nDate salvate per {sel_league}:")
        for i, d in enumerate(dates): print(f"{i+1}. {str(d)[:10]}")
        
        d_idx = int(input("Scegli Data (Giornata): ")) - 1
        sel_date = dates[d_idx]
        
        query = {"meta.league": sel_league, "meta.date": sel_date}
        del_count = collection.count_documents(query)
        
        print(f"\nStai per cancellare {del_count} partite.")
        if input("Confermi? (S/N): ").upper() == 'S':
            res = collection.delete_many(query)
            print(f"✅ Cancellati {res.deleted_count} record.")

    # --- AZIONE 3: RANGE ---
    elif action == '3':
        print("\n⚠️  Cancellazione per Range di Date.")
        # Simile a sopra, seleziona lega
        leagues = collection.distinct("meta.league")
        for i, l in enumerate(leagues): print(f"{i+1}. {l}")
        sel_league = leagues[int(input("Scegli Lega: ")) - 1]
        
        print("Inserisci data INIZIO (YYYY-MM-DD):")
        start_str = input("> ")
        print("Inserisci data FINE (YYYY-MM-DD):")
        end_str = input("> ")
        
        try:
            d_start = datetime.strptime(start_str, "%Y-%m-%d")
            d_end = datetime.strptime(end_str, "%Y-%m-%d")
            
            query = {
                "meta.league": sel_league,
                "meta.date": {"$gte": d_start, "$lte": d_end}
            }
            del_count = collection.count_documents(query)
            print(f"\nStai per cancellare {del_count} partite tra il {start_str} e il {end_str}.")
            if input("Confermi? (S/N): ").upper() == 'S':
                res = collection.delete_many(query)
                print(f"✅ Cancellati {res.deleted_count} record.")
        except:
            print("❌ Formato data errato.")

    # --- AZIONE 4: TUTTO ---
    elif action == '4':
        print(f"\n☢️  ATTENZIONE: STAI PER SVUOTARE INTERAMENTE {coll_name}!")
        print("Questa azione è IRREVERSIBILE.")
        confirm = input("Scrivi 'CANCELLA' per confermare: ")
        
        if confirm == "CANCELLA":
            res = collection.delete_many({})
            print(f"💀 Tabula Rasa. Cancellati {res.deleted_count} record.")
        else:
            print("Operazione annullata.")

if __name__ == "__main__":
    cleaner_menu()
