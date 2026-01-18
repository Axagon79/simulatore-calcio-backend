import os
import sys
from datetime import datetime
import contextlib

# 1. CONFIGURAZIONE DEI PERCORSI
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR)) 
sys.path.append(PROJECT_ROOT)
sys.path.append(CURRENT_DIR)

# --- FIX EMOJI WINDOWS ---
# Modifichiamo il silenziatore per accettare UTF-8 (⚽, 🛡️, etc.)
@contextlib.contextmanager
def suppress_stdout():
    """Redirige stdout su devnull gestendo correttamente le emoji."""
    # 🔥 LA MODIFICA È QUI: encoding='utf-8'
    with open(os.devnull, "w", encoding='utf-8') as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout

try:
    from config import db
    import calculate_team_rating as rating_lib
    print("✅ [INJECTOR-V6] Connessione stabilita.")
except ImportError as e:
    print(f"❌ [INJECTOR-V6] Errore: {e}")
    sys.exit(1)

# --- FUNZIONE MENU INTERATTIVO ---
def select_leagues_interactive(h2h_col):
    """
    Mostra i campionati disponibili e chiede all'utente quali processare.
    Restituisce un filtro MongoDB query.
    """
    print(f"\n{'='*60}")
    print(f"🎮 MENU SELEZIONE CAMPIONATI")
    print(f"{'='*60}")
    
    # Recupera i campionati distinti presenti nel DB
    # Nota: Assumiamo che nei documenti h2h_by_round ci sia il campo "league"
    available_leagues = sorted(h2h_col.distinct("league"))
    
    if not available_leagues:
        print("⚠️  Nessun campo 'league' trovato in h2h_by_round.")
        print("   -> Procedo con l'elaborazione di TUTTO il database.")
        return {}

    print(f"   [0] 🌍 AGGIORNA TUTTO (Tutti i campionati)")
    print(f"{'-'*60}")
    
    for i, league in enumerate(available_leagues, 1):
        print(f"   [{i}] {league}")
    
    print(f"\n📝 ISTRUZIONI: Inserisci il numero del campionato.")
    print(f"   - Esempio singolo: 5")
    print(f"   - Esempio multiplo: 1, 3, 5 (separati da virgola)")
    
    while True:
        choice = input(f"\n👉 La tua scelta: ").strip()
        
        # SCELTA: TUTTO
        if choice == "0":
            print("\n✅ Hai scelto: TUTTI I CAMPIONATI")
            return {} # Filtro vuoto = prendi tutto
            
        try:
            # Parsing input (es. "1, 3") -> [0, 2] (indici array)
            selected_indexes = [int(x.strip()) - 1 for x in choice.split(",") if x.strip().isdigit()]
            
            # Verifica validità
            if not selected_indexes or any(idx < 0 or idx >= len(available_leagues) for idx in selected_indexes):
                print("❌ Scelta non valida. Riprova.")
                continue
                
            selected_names = [available_leagues[idx] for idx in selected_indexes]
            print(f"\n✅ Hai scelto: {', '.join(selected_names)}")
            
            # Restituisce il filtro MongoDB
            return {"league": {"$in": selected_names}}
            
        except ValueError:
            print("❌ Input non valido. Usa solo numeri e virgole.")

def run_injection(interactive=True):
    teams_col = db["teams"]
    h2h_col = db["h2h_by_round"]

# --- 1. GESTIONE MENU / AUTOMATICO ---
    if interactive:
        # Se siamo in modalità manuale, mostriamo il menu
        query_filter = select_leagues_interactive(h2h_col)
    else:
        # Se siamo in modalità AUTOMATICA (chiamata dal direttore d'orchestra)
        print("\n🤖 MODALITÀ AUTOMATICA ATTIVA: Aggiorno tutti i campionati.")
        query_filter = {} # Filtro vuoto = Tutto

    print("\n🚀 AVVIO INIEZIONE (Sherlock Mode)...")
    print("   Sto analizzando i dati... attendere prego.\n")

    # --- STATISTICHE ---
    stats = {
        "processed_matches": 0,
        "skipped_matches": 0,
        "found_by_id": 0,
        "found_by_name": 0,
        "found_by_alias": 0,
    }
    failed_teams_log = {}
    data_cache = {}

    def find_team_document(tm_id, team_name_str):
        # 1. ID
        if tm_id:
            try:
                doc = teams_col.find_one({"transfermarkt_id": int(tm_id)})
                if doc: return doc, "ID"
            except: pass
        
        # 2. NOME
        if team_name_str:
            doc = teams_col.find_one({"name": team_name_str})
            if doc: return doc, "NAME"
            
            # 3. ALIAS
            doc = teams_col.find_one({"aliases": team_name_str})
            if doc: return doc, "ALIAS"
            
            # 4. REGEX
            doc = teams_col.find_one({"name": {"$regex": f"^{team_name_str}$", "$options": "i"}})
            if doc: return doc, "REGEX"

        return None, None

    def get_processed_data(tm_id, team_name_str):
        cache_key = str(tm_id) if tm_id else team_name_str
        
        if cache_key in data_cache:
            return data_cache[cache_key]

        team_doc, method = find_team_document(tm_id, team_name_str)
        
        if not team_doc:
            failed_teams_log[team_name_str] = "❌ NON TROVATA NEL DB (Controlla nomi/ID teams)"
            return None

        # Aggiorna contatori
        if method == "ID": stats["found_by_id"] += 1
        elif method == "NAME": stats["found_by_name"] += 1
        else: stats["found_by_alias"] += 1
        
        official_name = team_doc.get("name")

        try:
            with suppress_stdout():
                result = rating_lib.calculate_team_rating(official_name)
            
            if result:
                processed = {
                    "tec_perc": round(result.get("rating_5_25", 0) * 4, 1),
                    "starters": result.get("starters", []),
                    "bench": result.get("bench", []),
                    "formation": result.get("formation", "N/D")
                }
                data_cache[cache_key] = processed
                return processed
            else:
                failed_teams_log[team_name_str] = "⚠️  DB GIOCATORI VUOTO (Nessun player collegato)"
        
        except Exception as e:
            failed_teams_log[team_name_str] = f"💥 ERRORE SCRIPT: {str(e)}"
            pass
        
        return None

    # --- 2. RECUPERO ROUND FILTRATI ---
    all_rounds = list(h2h_col.find(query_filter))
    total_rounds = len(all_rounds)
    
    if total_rounds == 0:
        print("❌ Nessun round trovato con i criteri selezionati.")
        return

    # Ciclo principale
    for i, round_doc in enumerate(all_rounds):
        progress = (i + 1) / total_rounds * 100
        # Aggiungiamo info sulla lega corrente nel print di progresso
        current_league = round_doc.get("league", "Sconosciuta")
        print(f"\r⏳ [{current_league}] Round {i+1}/{total_rounds} ({progress:.1f}%) - Match OK: {stats['processed_matches']}", end="")

        round_id = round_doc["_id"]
        matches = round_doc.get("matches", [])
        modified = False
        
        for match in matches:
            id_home = match.get("home_tm_id")
            name_home = match.get("home") or match.get("home_team")
            id_away = match.get("away_tm_id")
            name_away = match.get("away") or match.get("away_team")

            h_data = get_processed_data(id_home, name_home)
            a_data = get_processed_data(id_away, name_away)

            if not h_data or not a_data:
                stats["skipped_matches"] += 1
                continue

            # Inserimento Dati
            if "h2h_data" not in match or match["h2h_data"] is None:
                match["h2h_data"] = {}
            
            if "h2h_dna" not in match["h2h_data"]:
                match["h2h_data"]["h2h_dna"] = {"home_dna": {}, "away_dna": {}}
            
            match["h2h_data"]["h2h_dna"]["home_dna"]["tec"] = h_data["tec_perc"]
            match["h2h_data"]["h2h_dna"]["away_dna"]["tec"] = a_data["tec_perc"]

            match["h2h_data"]["formazioni"] = {
                "home_squad": {"modulo": h_data["formation"], "titolari": h_data["starters"], "panchina": h_data["bench"]},
                "away_squad": {"modulo": a_data["formation"], "titolari": a_data["starters"], "panchina": a_data["bench"]}
            }
            
            modified = True
            stats["processed_matches"] += 1

        if modified:
            h2h_col.update_one(
                {"_id": round_id},
                {"$set": {"matches": matches, "last_tec_formazioni_update": datetime.now()}}
            )

    print("\n\n" + "="*70)
    print("📊 REPORT DIAGNOSTICO FINALE")
    print("="*70)
    print(f"✅ Match Aggiornati:   {stats['processed_matches']}")
    print(f"⏭️  Match Saltati:      {stats['skipped_matches']}")
    print("-" * 70)
    print("🔍 DETTAGLIO SUCCESSI (Metodo di ricerca):")
    print(f"   🆔 ID Match:           {stats['found_by_id']}")
    print(f"   📝 Nome Esatto:        {stats['found_by_name']}")
    print(f"   🎭 Alias/Regex:        {stats['found_by_alias']}")
    print("-" * 70)
    
    if failed_teams_log:
        print(f"❌ ANALISI ERRORI ({len(failed_teams_log)} squadre problematiche):")
        sorted_errors = sorted(failed_teams_log.items(), key=lambda x: x[1])
        current_error_type = ""
        for team, error in sorted_errors:
            if error != current_error_type:
                print(f"\n   🔴 {error}")
                current_error_type = error
            print(f"      - {team}")
    else:
        print("🎉 NESSUN ERRORE RILEVATO!")
    
    print("\n" + "="*70 + "\n")

# --- MODIFICA ANCHE IL BLOCCO FINALE ---
if __name__ == "__main__":
    # Se lancio il file DA SOLO, voglio il menu (interactive=True)
    run_injection(interactive=True)