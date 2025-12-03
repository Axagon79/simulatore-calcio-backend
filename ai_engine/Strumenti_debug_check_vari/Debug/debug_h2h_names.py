import sys
import os
from colorama import Fore, Style, init

# --- FIX PERCORSI BLINDATO ---
current_dir = os.path.dirname(os.path.abspath(__file__)) # calculators
parent_dir = os.path.dirname(current_dir) # ai_engine
root_dir = os.path.dirname(parent_dir) # simulatore-calcio-backend

sys.path.insert(0, root_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)
# -----------------------------

try:
    from config import db
except ImportError:
    print("ERRORE: Non trovo config.py nemmeno cercandolo ovunque.")
    sys.exit(1)

init(autoreset=True)

print(f"{Fore.CYAN}--- DIAGNOSTICA DATABASE H2H ---{Style.RESET_ALL}")

# 1. Contiamo quanti dati storici ABBIAMO DAVVERO
count_h2h = db.raw_h2h_data.count_documents({})
print(f"📁 Documenti in 'raw_h2h_data': {Fore.YELLOW}{count_h2h}{Style.RESET_ALL}")

if count_h2h == 0:
    print(f"{Fore.RED}🚨 ERRORE GRAVE: La collezione 'raw_h2h_data' è VUOTA!{Style.RESET_ALL}")
    print("   Lo script non trova nulla perché non hai mai salvato i dati storici.")
    print("   Devi lanciare lo scraper dei precedenti (quello che scarica lo storico) prima di fare i calcoli.")
    sys.exit()

# 2. Prendiamo un esempio di nome dall'archivio storico
sample_h2h = db.raw_h2h_data.find_one()
if sample_h2h:
    print(f"   Esempio dati storici: {sample_h2h.get('team_a')} vs {sample_h2h.get('team_b')}")

# 3. Prendiamo un esempio dal Calendario (h2h_by_round)
print("\n--- CONFRONTO NOMI ---")
round_doc = db.h2h_by_round.find_one()
if round_doc and "matches" in round_doc and len(round_doc["matches"]) > 0:
    match = round_doc["matches"][0]
    home_cal = match.get("home")
    away_cal = match.get("away")
    
    print(f"📅 Nel Calendario (h2h_by_round) cerco: {Fore.GREEN}'{home_cal}'{Style.RESET_ALL} vs {Fore.GREEN}'{away_cal}'{Style.RESET_ALL}")
    
    # Proviamo a cercarli ESATTAMENTE così nel DB storico
    found = db.raw_h2h_data.find_one({
        "$or": [
            {"team_a": home_cal, "team_b": away_cal},
            {"team_a": away_cal, "team_b": home_cal}
        ]
    })
    
    if found:
        print(f"✅ {Fore.GREEN}TROVATO! La corrispondenza esiste.{Style.RESET_ALL}")
    else:
        print(f"❌ {Fore.RED}NON TROVATO con questi nomi esatti.{Style.RESET_ALL}")
        print("   Cerco se esistono con nomi simili...")
        # Cerca parziale
        similar = db.raw_h2h_data.find_one({"team_a": {"$regex": home_cal}})
        if similar:
             print(f"   💡 Ma ho trovato: '{similar.get('team_a')}' (Forse c'è uno spazio in più o diverso?)")
        else:
             print("   Non trovo nemmeno nomi simili. Sicuro di aver scaricato questo campionato?")

print("\n--------------------------------")
