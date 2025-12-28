import os
import sys
from config import db
import difflib  # Libreria standard per trovare somiglianze nel testo

# --- CONFIGURAZIONE ---
standings_col = db['classifiche']
matches_col = db['h2h_by_round']

def normalize_name(name):
    """La stessa logica usata nell'injector"""
    if not name: return ""
    return name.lower().replace(" ", "").strip()

def find_best_match(target, options):
    """Cerca il nome più simile nella lista delle opzioni disponibili"""
    matches = difflib.get_close_matches(target, options, n=1, cutoff=0.6)
    return matches[0] if matches else None

def check_missing():
    print("🕵️  AVVIO DIAGNOSTICA MANCATI MATCH...")
    
    # 1. CARICHIAMO LE CLASSIFICHE DISPONIBILI
    # Struttura: available_teams["Serie A"] = {"inter": "Inter", "milan": "Milan"}
    available_teams = {}
    
    standings_cursor = standings_col.find({})
    for doc in standings_cursor:
        league_name = doc['league']
        if league_name not in available_teams:
            available_teams[league_name] = {}
            
        for row in doc['table']:
            clean = normalize_name(row['team'])
            original = row['team']
            available_teams[league_name][clean] = original
            
    print(f"📚 Classifiche caricate per: {list(available_teams.keys())}\n")

    # 2. CERCHIAMO I BUCHI NEI MATCH
    rounds_cursor = matches_col.find({})
    missing_report = {} # Per raggruppare gli errori
    
    total_checked = 0
    total_missing = 0

    for round_doc in rounds_cursor:
        matches = round_doc.get('matches', [])
        # Recupera nome lega
        league_source = round_doc.get('league_name') or round_doc.get('league') or "Sconosciuta"
        
        # Trova la lega corrispondente (Logica Fuzzy)
        target_league_key = None
        if league_source in available_teams:
            target_league_key = league_source
        else:
            for key in available_teams.keys():
                if key in league_source or league_source in key:
                    target_league_key = key
                    break
        
        if not target_league_key:
            # Se manca proprio il campionato, saltiamo (o lo segnaliamo a parte)
            continue

        for match in matches:
            total_checked += 2 # Casa e Ospite
            
            # Controlliamo Casa
            home = match.get('home', 'Sconosciuto')
            h_clean = normalize_name(home)
            if h_clean not in available_teams[target_league_key]:
                if target_league_key not in missing_report: missing_report[target_league_key] = set()
                missing_report[target_league_key].add(home)
                total_missing += 1

            # Controlliamo Ospite
            away = match.get('away', 'Sconosciuto')
            a_clean = normalize_name(away)
            if a_clean not in available_teams[target_league_key]:
                if target_league_key not in missing_report: missing_report[target_league_key] = set()
                missing_report[target_league_key].add(away)
                total_missing += 1

    # 3. STAMPA DEL REPORT DETTAGLIATO
    print("-" * 60)
    print(f"📊 REPORT ERRORI MATCHING")
    print("-" * 60)
    
    if total_missing == 0:
        print("\n✅ OTTIMO! Tutte le squadre hanno trovato una corrispondenza!")
    else:
        for league, teams in missing_report.items():
            print(f"\n🏆 CAMPIONATO: {league}")
            available_names_clean = list(available_teams[league].keys())
            
            for missing_team in sorted(teams):
                # Cerchiamo un suggerimento
                clean_missing = normalize_name(missing_team)
                suggestion_clean = find_best_match(clean_missing, available_names_clean)
                
                suggestion_display = ""
                if suggestion_clean:
                    real_name = available_teams[league][suggestion_clean]
                    suggestion_display = f" --> Forse intendevi: '{real_name}'?"
                
                print(f"   ❌ MANCA: '{missing_team}'{suggestion_display}")

    print("-" * 60)
    print(f"Totale squadre controllate: {total_checked}")
    print(f"Totale squadre senza classifica: {total_missing}")

if __name__ == "__main__":
    check_missing()