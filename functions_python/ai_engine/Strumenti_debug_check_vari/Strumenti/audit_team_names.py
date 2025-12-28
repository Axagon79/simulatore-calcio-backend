import os
import sys
from collections import defaultdict
from colorama import Fore, Style, init

# --- IMPORT RAPIDFUZZ ---
try:
    from rapidfuzz import fuzz, process
except ImportError:
    print("❌ Installa rapidfuzz: pip install rapidfuzz")
    sys.exit(1)

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
root_path = current_path
while not os.path.exists(os.path.join(root_path, 'config.py')):
    parent = os.path.dirname(root_path)
    if parent == root_path: break
    root_path = parent
sys.path.append(root_path)
if os.path.exists(os.path.join(root_path, 'ai_engine')):
    sys.path.append(os.path.join(root_path, 'ai_engine'))

try:
    from config import db
except:
    print("❌ Errore config DB")
    sys.exit(1)

init(autoreset=True)

def extract_strings(data):
    """Estrae TUTTE le stringhe da un JSON."""
    strings = set()
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ["_id", "date", "url", "link", "source", "last_updated", "logo", "image"]: continue
            strings.update(extract_strings(value))
    elif isinstance(data, list):
        for item in data: strings.update(extract_strings(item))
    elif isinstance(data, str):
        clean = data.strip()
        if len(clean) > 3 and not clean.isdigit() and ":" not in clean:
            strings.add(clean)
    return strings

def terminator_scan_v2():
    print(f"{Fore.RED}🤖 TERMINATOR SCAN V2: Ora con i Nomi Veri!{Style.RESET_ALL}\n")

    # 1. CARICA LA CONOSCENZA
    print("📥 Carico le squadre ufficiali...")
    
    name_to_id = {}      # Serve per trovare l'ID dal nome
    id_to_name = {}      # Serve per stampare il nome dall'ID (FIX DEL ???)
    official_names_list = []
    known_aliases = set()
    
    teams = list(db.teams.find({}, {"name": 1, "aliases": 1, "aliases_transfermarkt": 1}))
    for t in teams:
        tid = t["_id"]
        name = t["name"]
        
        name_to_id[name] = tid
        id_to_name[tid] = name  # <--- ECCO LA CHIAVE MANCANTE PRIMA
        
        official_names_list.append(name)
        known_aliases.add(name.lower())
        
        if "aliases" in t:
            for a in t["aliases"]: known_aliases.add(a.lower())
        if "aliases_transfermarkt" in t and t["aliases_transfermarkt"]:
            known_aliases.add(t["aliases_transfermarkt"].lower())
            
    print(f"✅ Conosco {len(teams)} squadre.\n")

    # 2. SCANSIONE TOTALE
    all_collections = db.list_collection_names()
    updates = defaultdict(list)
    processed_strings = set()

    for col_name in all_collections:
        if col_name == "teams": continue 
        
        print(f"🔥 Scansione collezione: {Fore.YELLOW}{col_name}{Style.RESET_ALL}")
        docs = list(db[col_name].find({}))
        
        candidates_in_col = set()
        for doc in docs:
            candidates_in_col.update(extract_strings(doc))
            
        print(f"   - Analizzo {len(candidates_in_col)} stringhe...")
        
        for text in candidates_in_col:
            text_lower = text.lower()
            if text_lower in known_aliases: continue
            if text_lower in processed_strings: continue
            processed_strings.add(text_lower)
            
            # MATCHING
            match = process.extractOne(text, official_names_list, scorer=fuzz.token_sort_ratio, score_cutoff=80)
            
            if match:
                best_name, score, idx = match
                
                # Filtri Sicurezza
                if len(text) < 4: continue 
                if score < 85 and len(text) < 6: continue
                
                # Escludi se è un nome di giocatore ovvio (euristica semplice)
                # Se il match è parziale ma il testo è molto lungo, è sospetto
                if len(text) > len(best_name) + 5: continue 

                tid = name_to_id[best_name]
                updates[tid].append((text, score, col_name))

    # 3. REPORT
    if not updates:
        print("\n🏁 Nessun nuovo alias trovato.")
        return

    print(f"\n{Fore.CYAN}💾 MODALITÀ APPRENDIMENTO (CONFERMA){Style.RESET_ALL}")
    
    for tid, props in updates.items():
        # ORA IL NOME VIENE RECUPERATO CORRETTAMENTE
        team_name = id_to_name.get(tid, "ERRORE_ID_NON_TROVATO")
        
        unique_props = list({p[0]: p for p in props}.values())
        unique_props.sort(key=lambda x: x[1], reverse=True)
        
        print(f"\nSquadra Ufficiale: {Fore.GREEN}{team_name.upper()}{Style.RESET_ALL}")
        
        for alias, score, src_col in unique_props:
            # Coloriamo lo score per evidenziare il rischio
            score_color = Fore.GREEN if score > 90 else Fore.YELLOW
            
            print(f"  Trovato in '{src_col}': {Fore.WHITE}'{alias}'{Style.RESET_ALL} (Simile al {score_color}{score:.0f}%{Style.RESET_ALL})")
            ans = input("  È un alias corretto? (s/n): ").lower()
            
            if ans == 's':
                db.teams.update_one({"_id": tid}, {"$addToSet": {"aliases": alias}})
                print("    ✅ Aggiunto.")

if __name__ == "__main__":
    terminator_scan_v2()
