import os
import sys
from datetime import datetime

# --- SETUP PERCORSI ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import db
    print(f"✅ Connesso al Database: {db.name}\n")
except ImportError:
    print("❌ Errore: Assicurati che config.py sia accessibile.")
    sys.exit(1)

def run_matching_audit():
    # 1. Caricamento dell'Anagrafica Teams
    teams_docs = list(db.teams.find({}))
    print(f"📊 Squadre censite nella collezione 'teams': {len(teams_docs)}")
    
    # Mappa per ricerca rapida: associa ogni possibile nome/alias all'ID della squadra
    lookup_map = {}
    for team in teams_docs:
        t_id = team.get('_id')
        main_name = team.get('name', '').lower().strip()
        
        # Aggiungi Nome Principale
        if main_name:
            lookup_map[main_name] = t_id
        
        # Aggiungi Alias Normali (lista o dizionario)
        aliases = team.get('aliases', [])
        if isinstance(aliases, list):
            for a in aliases:
                if a: lookup_map[a.lower().strip()] = t_id
        elif isinstance(aliases, dict):
            for a in aliases.values():
                if a: lookup_map[a.lower().strip()] = t_id
                
        # Aggiungi Alias Transfermarkt
        tm_aliases = team.get('aliases_transfermarkt', [])
        if isinstance(tm_aliases, list):
            for a in tm_aliases:
                if a: lookup_map[a.lower().strip()] = t_id

    # 2. Analisi dei Nomi nello Storico Match
    history_col = db["matches_history_betexplorer"]
    
    # Recupera tutti i nomi unici presenti nello storico (casa e trasferta)
    unique_names_home = history_col.distinct("homeTeam")
    unique_names_away = history_col.distinct("awayTeam")
    all_history_names = set([n.lower().strip() for n in unique_names_home + unique_names_away if n])
    
    print(f"🔍 Nomi unici trovati nello storico match: {len(all_history_names)}")
    print("-" * 60)

    # 3. Verifica del Matching
    matched = []
    failed = []

    for h_name in all_history_names:
        if h_name in lookup_map:
            matched.append(h_name)
        else:
            failed.append(h_name)

    # 4. Report Finale
    print(f"✅ MATCHING RIUSCITO: {len(matched)} nomi")
    print(f"❌ MATCHING FALLITO:  {len(failed)} nomi")
    
    if failed:
        print("\n⚠️ ESEMPI DI NOMI NON RICONOSCIUTI (Primi 20):")
        for name in sorted(failed)[:20]:
            print(f"   • {name}")
            
    success_rate = (len(matched) / len(all_history_names)) * 100 if all_history_names else 0
    print(f"\n📈 TASSO DI COPERTURA: {success_rate:.1f}%")

if __name__ == "__main__":
    run_matching_audit()