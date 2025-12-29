import os
import sys
import importlib.util
from collections import defaultdict

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

# --- COLLECTIONS ---
teams_col = db["teams"]
h2h_col = db["h2h_by_round"]

def build_teams_reference():
    """Crea dizionario di riferimento usando NAME + ALIASES"""
    print("📚 Caricamento dati da collection 'teams'...")
    
    # Dizionario: ogni possibile nome/alias punta al TM_ID corretto
    alias_to_tmid = {}
    
    for team in teams_col.find({}):
        tm_id = team.get('transfermarkt_id')
        if not tm_id:
            continue
        
        tm_id_str = str(tm_id)
        team_name = team.get('name', '')
        aliases = team.get('aliases', [])
        
        # Aggiungi il nome principale
        if team_name:
            alias_to_tmid[team_name.strip()] = {
                'tm_id': tm_id_str,
                'canonical_name': team_name,
                '_id': team.get('_id')
            }
        
        # Aggiungi tutti gli aliases
        for alias in aliases:
            alias_clean = alias.strip()
            if alias_clean:
                alias_to_tmid[alias_clean] = {
                    'tm_id': tm_id_str,
                    'canonical_name': team_name,
                    '_id': team.get('_id')
                }
    
    print(f"   ✅ Caricate {len(alias_to_tmid)} varianti di nomi squadre\n")
    return alias_to_tmid

def audit_h2h_collection(teams_ref):
    """Controlla tutti i TM_ID in h2h_by_round usando EXACT MATCH su aliases"""
    print("🔍 Audit collection 'h2h_by_round' (EXACT MATCH su aliases)...")
    print("="*80)
    
    issues = {
        'missing_tm_id': [],
        'wrong_tm_id': [],
        'team_not_found': [],
        'correct': 0
    }
    
    total_matches = 0
    docs_processed = 0
    
    for doc in h2h_col.find({}):
        doc_id = doc.get('_id')
        docs_processed += 1
        
        for match in doc.get('matches', []):
            total_matches += 1
            
            home_name = match.get('home', '').strip()
            away_name = match.get('away', '').strip()
            home_tm_id = str(match.get('home_tm_id', '')).strip() if match.get('home_tm_id') else ''
            away_tm_id = str(match.get('away_tm_id', '')).strip() if match.get('away_tm_id') else ''
            
            # --- CHECK HOME TEAM (EXACT MATCH) ---
            if home_name in teams_ref:
                correct_tm_id = teams_ref[home_name]['tm_id']
                canonical_name = teams_ref[home_name]['canonical_name']
                
                if not home_tm_id:
                    issues['missing_tm_id'].append({
                        'doc': doc_id,
                        'team': home_name,
                        'position': 'home',
                        'match': f"{home_name} - {away_name}",
                        'correct_tm_id': correct_tm_id,
                        'canonical_name': canonical_name
                    })
                elif home_tm_id != correct_tm_id:
                    issues['wrong_tm_id'].append({
                        'doc': doc_id,
                        'team': home_name,
                        'position': 'home',
                        'match': f"{home_name} - {away_name}",
                        'current_tm_id': home_tm_id,
                        'correct_tm_id': correct_tm_id,
                        'canonical_name': canonical_name
                    })
                else:
                    issues['correct'] += 1
            else:
                issues['team_not_found'].append({
                    'doc': doc_id,
                    'team': home_name,
                    'position': 'home',
                    'match': f"{home_name} - {away_name}",
                    'current_tm_id': home_tm_id
                })
            
            # --- CHECK AWAY TEAM (EXACT MATCH) ---
            if away_name in teams_ref:
                correct_tm_id = teams_ref[away_name]['tm_id']
                canonical_name = teams_ref[away_name]['canonical_name']
                
                if not away_tm_id:
                    issues['missing_tm_id'].append({
                        'doc': doc_id,
                        'team': away_name,
                        'position': 'away',
                        'match': f"{home_name} - {away_name}",
                        'correct_tm_id': correct_tm_id,
                        'canonical_name': canonical_name
                    })
                elif away_tm_id != correct_tm_id:
                    issues['wrong_tm_id'].append({
                        'doc': doc_id,
                        'team': away_name,
                        'position': 'away',
                        'match': f"{home_name} - {away_name}",
                        'current_tm_id': away_tm_id,
                        'correct_tm_id': correct_tm_id,
                        'canonical_name': canonical_name
                    })
                else:
                    issues['correct'] += 1
            else:
                issues['team_not_found'].append({
                    'doc': doc_id,
                    'team': away_name,
                    'position': 'away',
                    'match': f"{home_name} - {away_name}",
                    'current_tm_id': away_tm_id
                })
    
    print(f"✅ Documenti processati: {docs_processed}")
    print(f"✅ Partite analizzate: {total_matches} ({total_matches * 2} team checks)")
    print("="*80)
    
    return issues

def print_report(issues):
    """Stampa report dettagliato"""
    total_checks = issues['correct'] + len(issues['missing_tm_id']) + len(issues['wrong_tm_id']) + len(issues['team_not_found'])
    
    print(f"\n📊 REPORT FINALE")
    print("="*80)
    print(f"✅ TM_ID Corretti: {issues['correct']}/{total_checks} ({issues['correct']*100/total_checks:.1f}%)")
    print(f"⚠️ TM_ID Mancanti: {len(issues['missing_tm_id'])}")
    print(f"❌ TM_ID Sbagliati: {len(issues['wrong_tm_id'])}")
    print(f"🔍 Squadre non trovate in 'teams': {len(issues['team_not_found'])}")
    print("="*80)
    
    # --- DETTAGLIO TM_ID SBAGLIATI (PIÙ IMPORTANTE) ---
    if issues['wrong_tm_id']:
        print(f"\n❌ TM_ID SBAGLIATI ({len(issues['wrong_tm_id'])}) - DA CORREGGERE!")
        print("-"*80)
        for issue in issues['wrong_tm_id'][:30]:
            print(f"Doc: {issue['doc']}")
            print(f"   Match: {issue['match']}")
            print(f"   Team: {issue['team']} ({issue['position']})")
            print(f"   ❌ TM_ID Attuale: {issue['current_tm_id']}")
            print(f"   ✅ TM_ID Corretto: {issue['correct_tm_id']}")
            print(f"   📝 Nome Canonico: {issue['canonical_name']}")
            print()
        if len(issues['wrong_tm_id']) > 30:
            print(f"... e altri {len(issues['wrong_tm_id']) - 30}\n")
    
    # --- DETTAGLIO TM_ID MANCANTI ---
    if issues['missing_tm_id']:
        print(f"\n⚠️ TM_ID MANCANTI ({len(issues['missing_tm_id'])})")
        print("-"*80)
        for issue in issues['missing_tm_id'][:20]:
            print(f"Doc: {issue['doc']}")
            print(f"   Match: {issue['match']}")
            print(f"   Team: {issue['team']} ({issue['position']})")
            print(f"   Dovrebbe avere TM_ID: {issue['correct_tm_id']}")
            print(f"   📝 Nome Canonico: {issue['canonical_name']}")
            print()
        if len(issues['missing_tm_id']) > 20:
            print(f"... e altri {len(issues['missing_tm_id']) - 20}\n")
    
    # --- SQUADRE NON TROVATE ---
    if issues['team_not_found']:
        print(f"\n🔍 SQUADRE NON IN 'teams' ({len(issues['team_not_found'])})")
        print("-"*80)
        unique_teams = {}
        for issue in issues['team_not_found']:
            team = issue['team']
            if team not in unique_teams:
                unique_teams[team] = issue
        
        for team, issue in list(unique_teams.items())[:20]:
            print(f"   - '{team}' (TM_ID attuale: {issue['current_tm_id'] or 'N/A'})")
        if len(unique_teams) > 20:
            print(f"... e altre {len(unique_teams) - 20}\n")
        
        print("\n💡 Suggerimento: Aggiungi queste squadre agli 'aliases' in 'teams'")
    
    # --- CONCLUSIONE ---
    print("\n" + "="*80)
    if len(issues['wrong_tm_id']) > 0 or len(issues['missing_tm_id']) > 0:
        print("💡 AZIONE CONSIGLIATA:")
        print("   Esegui 'fix_tm_ids.py' per correggere automaticamente i TM_ID")
        print(f"   Verranno corretti: {len(issues['wrong_tm_id']) + len(issues['missing_tm_id'])} errori")
    else:
        print("✅ Tutti i TM_ID sono corretti!")
    print("="*80)

def main():
    print("🔍 AUDIT TM_ID: h2h_by_round vs teams")
    print("="*80)
    print("Confronta TM_ID usando EXACT MATCH su name + aliases\n")
    
    # 1. Carica reference da teams (name + aliases)
    teams_ref = build_teams_reference()
    
    # 2. Audita h2h_by_round
    issues = audit_h2h_collection(teams_ref)
    
    # 3. Stampa report
    print_report(issues)

if __name__ == "__main__":
    main()