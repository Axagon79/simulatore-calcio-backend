import os
import sys
import re

# --- CONFIGURAZIONE ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR)) 
sys.path.append(PROJECT_ROOT)
sys.path.append(CURRENT_DIR)

try:
    from config import db
    print("✅ Connessione DB OK.\n")
except ImportError as e:
    print(f"❌ Errore importazione: {e}")
    sys.exit(1)

teams_col = db["teams"]
players_col = db["players_stats_fbref_def"]

def select_league():
    print(f"{'='*60}")
    print(f"🔒 REVERSE LINKER - ZERO TOLERANCE (V7)")
    print(f"{'='*60}")
    
    available_leagues = sorted(teams_col.distinct("league"))
    
    print(f"   [0] 🌍 CONTROLLA TUTTO (Sequenza Completa)")
    print(f"{'-'*60}")

    for i, league in enumerate(available_leagues, 1):
        print(f"   [{i}] {league}")
    
    while True:
        choice = input(f"\n👉 Scegli il campionato (numero): ").strip()
        
        if choice == "0":
            return "ALL"

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(available_leagues):
                return available_leagues[idx]
        except: pass
        print("❌ Scelta non valida.")

def is_strict_match(target_league, source_league):
    """
    Funzione 'Buttafuori': Accetta solo match esatti o varianti autorizzate.
    Rifiuta tutto ciò che è ambiguo.
    """
    t = target_league.lower().strip()
    s = source_league.lower().strip()

    # --- REGOLE FERREE PER I BIG 5 ---

    # 1. SERIE A (Italia)
    if t == "serie a":
        # Accettiamo solo questi esatti. Niente "Brasileirão" prima.
        allowed = ["serie a", "serie a tim", "serie a enilive"]
        return s in allowed

    # 2. PREMIER LEAGUE (Inghilterra)
    if t == "premier league":
        # Deve essere ESATTAMENTE "premier league".
        # Rifiuta "Russian Premier League", "Canadian...", ecc.
        return s == "premier league"

    # 3. BUNDESLIGA (Germania)
    if t == "bundesliga":
        # Rifiuta "2. Bundesliga" o "Austrian Bundesliga"
        return s == "bundesliga"

    # 4. LIGUE 1 (Francia)
    if t == "ligue 1":
        # Accetta "Ligue 1" o con sponsor "Ligue 1 Uber Eats" / "McDonald's"
        # Rifiuta "Ligue 2" o "Tunisian Ligue 1"
        return s.startswith("ligue 1") and "tunisia" not in s

    # 5. LALIGA (Spagna)
    if t == "laliga" or t == "la liga":
        return "laliga" in s or "la liga" in s and "2" not in s and "hypermotion" not in s

    # --- REGOLE GENERALI PER GLI ALTRI CAMPIONATI ---
    
    # Se il nome contiene "2", "B", "Second" e il target no -> SCARTA
    blocklist_words = ["2", "second", "women", "femminile", "u21", "u19", "reserve"]
    for word in blocklist_words:
        if word in s and word not in t:
            return False

    # Se il nome della lega sorgente contiene parole geografiche che NON sono nel target
    # Es: Target="Super League" (Svizzera) vs Source="Chinese Super League" -> SCARTA
    geo_blocklist = ["china", "chinese", "indian", "russian", "saudi", "brasil", "brazil", "argentina"]
    for geo in geo_blocklist:
        if geo in s and geo not in t:
            return False

    # Se siamo qui, facciamo un check standard di contenimento
    if t in s:
        return True
        
    return False

def get_orphans_for_league(target_league):
    print(f"⏳ Cerco nomi orfani per: {target_league}...")
    
    known_names = set()
    my_teams = list(teams_col.find({"league": target_league}))
    
    for t in my_teams:
        known_names.add(t["name"])
        for a in t.get("aliases", []):
            known_names.add(a)

    # Regex search (Generica, poi filtriamo col buttafuori)
    safe_search_term = re.escape(target_league)
    pipeline = [
        {"$match": {"league_name": {"$regex": safe_search_term, "$options": "i"}}},
        {"$group": {"_id": "$team_name_fbref", "full_league": {"$first": "$league_name"}}}
    ]
    
    player_teams = list(players_col.aggregate(pipeline))
    
    orphans = []
    for item in player_teams:
        name = item["_id"]
        league_source = item["full_league"]
        
        # --- FILTRO ZERO TOLERANCE ---
        if not is_strict_match(target_league, league_source):
            # Se la funzione dice False, scartiamo silenziosamente
            continue 

        if name not in known_names:
            orphans.append((name, league_source))
            
    return orphans, my_teams

def process_single_league(league_name):
    print(f"\n{'='*80}")
    print(f"📂 ANALISI: {league_name}")
    print(f"{'='*80}")

    orphans, my_teams = get_orphans_for_league(league_name)
    
    if not orphans:
        print(f"✅ Nessun nome orfano trovato in {league_name}.")
        return True 

    print(f"⚠️  TROVATI {len(orphans)} NOMI DA COLLEGARE IN '{league_name}'.")
    
    my_teams.sort(key=lambda x: x["name"])

    for idx_orph, (orphan_name, origin_league) in enumerate(orphans, 1):
        print(f"\n[{idx_orph}/{len(orphans)}] Nome orfano:  👉  '{orphan_name}'")
        print(f"      (Fonte FBref: {origin_league})")
        print(f"{'-'*60}")
        print("      A quale delle tue squadre corrisponde?")
        
        for i, team in enumerate(my_teams, 1):
            t_name = team["name"]
            # Stella se c'è somiglianza
            mark = "⭐" if t_name[:4].lower() in orphan_name.lower() or orphan_name[:4].lower() in t_name.lower() else "  "
            print(f"      [{i}] {mark} {t_name}")
            
        print(f"      [s] Salta")
        print(f"      [x] Esci dallo script")
        
        while True:
            choice = input(f"      👉 Seleziona numero: ").strip().lower()
            
            if choice == 'x':
                print("👋 Uscita richiesta.")
                sys.exit(0)

            if choice == 's':
                print("      ⏩ Saltato.")
                break
                
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(my_teams):
                    target_team = my_teams[idx]
                    target_name = target_team["name"]
                    target_id = target_team["_id"]
                    
                    teams_col.update_one(
                        {"_id": target_id},
                        {"$addToSet": {"aliases": orphan_name}}
                    )
                    
                    print(f"      ✅ COLLEGATO! '{orphan_name}' -> '{target_name}'")
                    break
                else:
                    print("      ❌ Numero non valido.")
            else:
                print("      ❌ Input non valido.")
    
    return True

def run_linker():
    selection = select_league()
    
    if selection == "ALL":
        all_leagues = sorted(teams_col.distinct("league"))
        print(f"\n🚀 AVVIO MODALITÀ GLOBALE: Analisi di {len(all_leagues)} campionati...")
        for league in all_leagues:
            process_single_league(league)
        print("\n🎉 CONTROLLO GLOBALE COMPLETATO!")
    else:
        process_single_league(selection)
        print(f"\n🏁 Finito per {selection}.")

if __name__ == "__main__":
    run_linker()