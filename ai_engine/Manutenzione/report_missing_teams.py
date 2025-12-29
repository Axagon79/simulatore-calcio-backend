import os
import sys
import importlib.util
from datetime import datetime

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
aggiornamenti_dir = os.path.dirname(current_dir)
ai_engine_dir = os.path.dirname(aggiornamenti_dir)
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    spec = importlib.util.spec_from_file_location("config", os.path.join(project_root, "config.py"))
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)
    db = config_module.db
    print(f"✅ DB Connesso: {db.name}\n")
except Exception as e:
    print(f"❌ Errore Import Config: {e}")
    sys.exit(1)

# --- COLLECTION ---
h2h_col = db["h2h_by_round"]

# --- CONFIGURAZIONE FIX ---
WRONG_TM_ID = "1075"
CORRECT_TM_ID = "336"
TEAM_NAME = "Sporting"

def find_matches_to_fix():
    """Cerca tutti i match da correggere SENZA modificare"""
    
    print("🔍 FASE 1: RICERCA MATCH DA CORREGGERE")
    print("="*80)
    print(f"Team: {TEAM_NAME}")
    print(f"TM_ID Sbagliato da cercare: {WRONG_TM_ID}")
    print(f"TM_ID Corretto da impostare: {CORRECT_TM_ID}")
    print("="*80 + "\n")
    
    matches_to_fix = []
    
    # Cerca home
    for doc in h2h_col.find({"matches.home": TEAM_NAME}):
        doc_id = doc.get('_id')
        for match in doc.get('matches', []):
            if match.get('home') == TEAM_NAME and str(match.get('home_tm_id', '')) == WRONG_TM_ID:
                matches_to_fix.append({
                    'doc_id': doc_id,
                    'match': match,
                    'position': 'home',
                    'match_str': f"{match['home']} - {match['away']}"
                })
    
    # Cerca away
    for doc in h2h_col.find({"matches.away": TEAM_NAME}):
        doc_id = doc.get('_id')
        for match in doc.get('matches', []):
            if match.get('away') == TEAM_NAME and str(match.get('away_tm_id', '')) == WRONG_TM_ID:
                matches_to_fix.append({
                    'doc_id': doc_id,
                    'match': match,
                    'position': 'away',
                    'match_str': f"{match['home']} - {match['away']}"
                })
    
    return matches_to_fix

def apply_fixes(matches_to_fix):
    """Applica le correzioni ai match trovati"""
    
    print("\n🔧 FASE 2: APPLICAZIONE CORREZIONI")
    print("="*80 + "\n")
    
    docs_to_update = {}
    
    # Raggruppa per documento
    for item in matches_to_fix:
        doc_id = item['doc_id']
        if doc_id not in docs_to_update:
            docs_to_update[doc_id] = h2h_col.find_one({"_id": doc_id})
    
    docs_updated = 0
    matches_fixed = 0
    
    # Applica correzioni
    for doc_id, doc in docs_to_update.items():
        matches = doc.get('matches', [])
        modified = False
        
        for match in matches:
            # Fix home
            if match.get('home') == TEAM_NAME and str(match.get('home_tm_id', '')) == WRONG_TM_ID:
                match['home_tm_id'] = int(CORRECT_TM_ID)
                modified = True
                matches_fixed += 1
                print(f"   ✅ {doc_id}: {match['home']} - {match['away']} (home) → {CORRECT_TM_ID}")
            
            # Fix away
            if match.get('away') == TEAM_NAME and str(match.get('away_tm_id', '')) == WRONG_TM_ID:
                match['away_tm_id'] = int(CORRECT_TM_ID)
                modified = True
                matches_fixed += 1
                print(f"   ✅ {doc_id}: {match['home']} - {match['away']} (away) → {CORRECT_TM_ID}")
        
        if modified:
            h2h_col.update_one(
                {"_id": doc_id},
                {"$set": {"matches": matches, "last_updated": datetime.now()}}
            )
            docs_updated += 1
    
    return docs_updated, matches_fixed

def main():
    print("🔧 CORREZIONE TM_ID SPORTING CP")
    print("="*80)
    print("Questo script corregge il TM_ID dello Sporting CP")
    print("da 1075 (sbagliato) a 336 (corretto) in h2h_by_round\n")
    
    # FASE 1: Trova cosa correggere
    matches_to_fix = find_matches_to_fix()
    
    if not matches_to_fix:
        print("✅ Nessun match da correggere trovato!")
        print("   Possibili cause:")
        print("   - TM_ID già corretti in precedenza")
        print("   - Nome squadra diverso da 'Sporting'")
        print("   - TM_ID diverso da 1075")
        return
    
    # Mostra tutti i match trovati
    print(f"📋 TROVATI {len(matches_to_fix)} MATCH DA CORREGGERE:")
    print("-"*80)
    
    for idx, item in enumerate(matches_to_fix, 1):
        current_tm_id = item['match'].get(f"{item['position']}_tm_id")
        print(f"{idx:2}. {item['doc_id']}")
        print(f"    Match: {item['match_str']}")
        print(f"    Position: {item['position']}")
        print(f"    TM_ID attuale: {current_tm_id} → Verrà cambiato in: {CORRECT_TM_ID}")
        if idx % 5 == 0 and idx < len(matches_to_fix):
            print()
    
    print("-"*80)
    print(f"\n📊 RIEPILOGO:")
    print(f"   • Match da correggere: {len(matches_to_fix)}")
    print(f"   • Documenti coinvolti: {len(set(item['doc_id'] for item in matches_to_fix))}")
    print(f"   • TM_ID: {WRONG_TM_ID} → {CORRECT_TM_ID}")
    
    # FASE 2: Chiedi conferma ORA che l'utente sa cosa verrà modificato
    print("\n" + "="*80)
    print("⚠️ CONFERMA NECESSARIA")
    print("="*80)
    risposta = input("\nVuoi procedere con le correzioni? (scrivi 'SI' per confermare): ")
    
    if risposta.strip().upper() != "SI":
        print("\n❌ Operazione annullata dall'utente.")
        print("   Nessuna modifica è stata effettuata al database.")
        return
    
    # FASE 3: Applica correzioni
    docs_updated, matches_fixed = apply_fixes(matches_to_fix)
    
    # Report finale
    print("\n" + "="*80)
    print("📊 REPORT FINALE")
    print("="*80)
    print(f"✅ Documenti aggiornati: {docs_updated}")
    print(f"✅ Match corretti: {matches_fixed}")
    print("="*80)
    print("\n🎉 Correzione completata con successo!")
    print("💡 Ora puoi rieseguire lo scraper per aggiornare i risultati dello Sporting")

if __name__ == "__main__":
    main()