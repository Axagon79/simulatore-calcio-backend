import os
import sys
import re
from datetime import datetime

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)
if ai_engine_dir not in sys.path: sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

try:
    from config import db
    print(f"✅ DB Connesso: {db.name}")
except ImportError:
    print("❌ Errore Import Config")
    sys.exit(1)

# --- CONFIGURAZIONE ---
COLLECTION_TEAMS = "teams"
COLLECTION_H2H = "h2h_by_round"
LOG_FILE = "squadre_da_sistemare.txt"

# 🚩 TEST MODE: Se True, non scrive nulla nel DB. Mettilo a False quando la lista è ok.
DRY_RUN = False 

def normalize(name):
    """ Normalizzazione identica per evitare errori di battitura o spazi extra """
    if not name: return ""
    return name.lower().strip()

def build_strict_team_map():
    """ Crea mappa ID usando nomi ufficiali, alias comuni e alias specifici transfermarkt """
    print("🔍 Recupero nomi e alias dalla collezione 'teams'...")
    teams_col = db[COLLECTION_TEAMS]
    team_map = {}
    
    for team in teams_col.find():
        tm_id = team.get("transfermarkt_id")
        if not tm_id: continue
        
        # 1. Raccogliamo tutte le varianti di nome possibili nel tuo database
        valid_names = []
        
        # Nome principale
        if team.get("name"): valid_names.append(team.get("name"))
        
        # Alias generici (array)
        aliases = team.get("aliases", [])
        if isinstance(aliases, list):
            valid_names.extend(aliases)
            
        # Alias specifici per Transfermarkt (stringa) - NOVITÀ
        tm_alias = team.get("aliases_transfermarkt")
        if tm_alias:
            valid_names.append(tm_alias)
            
        # Slug di Transfermarkt (utile come ultima spiaggia)
        slug = team.get("transfermarkt_slug")
        if slug:
            valid_names.append(slug.replace("-", " "))

        # 2. Inseriamo nella mappa tutte le versioni normalizzate
        for n in valid_names:
            norm_n = normalize(n)
            if norm_n:
                team_map[norm_n] = tm_id
                
    return team_map

def run_sync():
    team_map = build_strict_team_map()
    h2h_col = db[COLLECTION_H2H]
    
    print(f"\n🚀 Analisi match (DRY_RUN={DRY_RUN})...")
    
    docs = list(h2h_col.find())
    total_matches = 0
    updated_matches = 0
    missing_teams = set()

    for doc in docs:
        matches = doc.get("matches", [])
        doc_id = doc.get("_id")
        modified = False
        
        for m in matches:
            total_matches += 1
            h_name = m.get("home")
            a_name = m.get("away")
            
            # Confronto IDENTICO sui nomi normalizzati
            h_id = team_map.get(normalize(h_name))
            a_id = team_map.get(normalize(a_name))
            
            if h_id and a_id:
                # Se troviamo entrambi gli ID e non sono già salvati correttamente
                if m.get("home_tm_id") != h_id or m.get("away_tm_id") != a_id:
                    m["home_tm_id"] = h_id
                    m["away_tm_id"] = a_id
                    modified = True
                    updated_matches += 1
            else:
                # Se uno dei due manca, lo aggiungiamo alla lista della spesa
                if not h_id: missing_teams.add(h_name)
                if not a_id: missing_teams.add(a_name)

        if modified and not DRY_RUN:
            h2h_col.update_one({"_id": doc_id}, {"$set": {"matches": matches}})

    # --- GENERAZIONE LISTA DELLA SPESA ---
    if missing_teams:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("--- LISTA SQUADRE SENZA MATCH (DA AGGIUNGERE NEI TEAMS ALIASES) ---\n")
            for team in sorted(list(missing_teams)):
                f.write(f"{team}\n")
        print(f"📝 Generata 'lista della spesa' aggiornata in: {LOG_FILE}")
    elif os.path.exists(LOG_FILE):
        # Se la lista è vuota, rimuoviamo il file vecchio per pulizia
        os.remove(LOG_FILE)

    print(f"\n📊 REPORT AGGIORNATO:")
    print(f"   - Match totali: {total_matches}")
    print(f"   - Match pronti per l'inserimento ID: {updated_matches}")
    print(f"   - Squadre ancora ignote: {len(missing_teams)}")
    
    if DRY_RUN:
        if len(missing_teams) > 0:
            print("\n⚠️  QUASI CI SIAMO: Controlla le ultime squadre nel file .txt.")
        else:
            print("\n🎯 PERFETTO: Tutte le squadre sono state riconosciute!")
            print("   Ora imposta DRY_RUN = False per scrivere gli ID nel database.")
    else:
        print(f"\n✅ OPERAZIONE COMPLETATA: {updated_matches} match aggiornati con successo.")

if __name__ == "__main__":
    run_sync()