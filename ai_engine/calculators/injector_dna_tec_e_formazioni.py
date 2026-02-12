import os
import sys
import re
from datetime import datetime
import dateutil.parser
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
    
    # ✅ Aggiungi Champions ed Europa League al menu
    available_leagues.append("Champions League")
    available_leagues.append("Europa League")
    available_leagues = sorted(available_leagues)
    
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

def get_round_number(doc):
    """Estrae il numero di giornata dall'ID documento."""
    name = doc.get('_id', '') or doc.get('round_name', '')
    match = re.search(r'(\d+)', str(name))
    return int(match.group(1)) if match else 999

def find_target_rounds(league_docs):
    """Trova le 3 giornate da aggiornare: precedente, attuale, successiva."""
    if not league_docs: return []
    sorted_docs = sorted(league_docs, key=get_round_number)
    now = datetime.now()
    closest_index = -1
    min_diff = float('inf')
    for i, doc in enumerate(sorted_docs):
        dates = []
        for m in doc.get('matches', []):
            d_raw = m.get('date_obj') or m.get('date')
            try:
                if d_raw:
                    d = d_raw if isinstance(d_raw, datetime) else dateutil.parser.parse(d_raw)
                    dates.append(d.replace(tzinfo=None))
            except: pass
        if dates:
            avg_date = sum([d.timestamp() for d in dates]) / len(dates)
            diff = abs(now.timestamp() - avg_date)
            if diff < min_diff: min_diff = diff; closest_index = i
    if closest_index == -1: return []
    start_idx = max(0, closest_index - 1)
    end_idx = min(len(sorted_docs), closest_index + 2)
    return sorted_docs[start_idx:end_idx]

def run_injection(interactive=True):
    teams_col = db["teams"]
    h2h_col = db["h2h_by_round"]
    ucl_col = db["matches_champions_league"]
    uel_col = db["matches_europa_league"]

# --- 1. GESTIONE MENU / AUTOMATICO ---
    targeted_rounds = None
    if interactive:
        query_filter = select_leagues_interactive(h2h_col)
    else:
        print("\n🤖 MODALITÀ AUTOMATICA MIRATA: Prec/Attuale/Succ per ogni campionato")
        query_filter = {}
        # Pre-compute targeted rounds: 2 fasi (projection leggera + query mirata)
        print("   📥 Fase 1: selezione round (query leggera)...")
        light_docs = list(h2h_col.find({}, {"_id": 1, "league": 1, "matches.date": 1, "matches.date_obj": 1}))
        by_league = {}
        for doc in light_docs:
            lg = doc.get("league")
            if lg:
                by_league.setdefault(lg, []).append(doc)
        target_ids = []
        for lg_name, lg_docs in by_league.items():
            target = find_target_rounds(lg_docs)
            target_ids.extend([d["_id"] for d in target])
        print(f"   📥 Fase 2: caricamento {len(target_ids)} round completi...")
        targeted_rounds = list(h2h_col.find({"_id": {"$in": target_ids}}))
        print(f"   📋 {len(by_league)} campionati, {len(light_docs)} docs → {len(targeted_rounds)} giornate mirate")

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

    def find_team_document(tm_id, team_name_str, is_cup=False):
        # Se è una coppa, cerca anche nelle collezioni coppe
        collections_to_search = [teams_col]
        
        if is_cup:
            collections_to_search.extend([
                db["teams_champions_league"],
                db["teams_europa_league"]
            ])
        
        # 1. ID
        if tm_id:
            try:
                for col in collections_to_search:
                    doc = col.find_one({"transfermarkt_id": int(tm_id)})
                    if doc: return doc, "ID"
            except: pass
        
        # 2. NOME
        if team_name_str:
            for col in collections_to_search:
                doc = col.find_one({"name": team_name_str})
                if doc: return doc, "NAME"
                
                # 3. ALIAS
                doc = col.find_one({"aliases": team_name_str})
                if doc: return doc, "ALIAS"
                
                # 4. REGEX
                doc = col.find_one({"name": {"$regex": f"^{team_name_str}$", "$options": "i"}})
                if doc: return doc, "REGEX"

        return None, None

    def get_processed_data(tm_id, team_name_str):
        cache_key = str(tm_id) if tm_id else team_name_str
        
        if cache_key in data_cache:
            return data_cache[cache_key]

        # Determina se è una coppa guardando il nome della squadra o contesto
        team_doc, method = find_team_document(tm_id, team_name_str, is_cup=True)
        
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

    # --- 2. RECUPERO DOCUMENTI FILTRATI (Campionati + Coppe) ---
    all_docs = []

    # Determina quali collezioni processare in base al filtro
    if targeted_rounds is not None:
        # Modalità mirata: round pre-calcolati + coppe mirate
        all_docs.extend(targeted_rounds)
        for cup_col in [ucl_col, uel_col]:
            cup_light = list(cup_col.find({}, {"_id": 1, "matches.date": 1, "matches.date_obj": 1}))
            cup_target = find_target_rounds(cup_light)
            cup_ids = [d["_id"] for d in cup_target]
            if cup_ids:
                all_docs.extend(list(cup_col.find({"_id": {"$in": cup_ids}})))
        print(f"   📋 Totale documenti da processare: {len(all_docs)} (h2h: {len(targeted_rounds)} + coppe mirate)")
    elif not query_filter:  # Tutto (fallback)
        all_docs.extend(list(h2h_col.find({})))
        all_docs.extend(list(ucl_col.find({})))
        all_docs.extend(list(uel_col.find({})))
    elif "league" in query_filter and "$in" in query_filter["league"]:
        # Filtra per campionati specifici
        selected = query_filter["league"]["$in"]
        
        # Campionati normali
        if any(s not in ["Champions League", "Europa League"] for s in selected):
            league_filter = [s for s in selected if s not in ["Champions League", "Europa League"]]
            if league_filter:
                all_docs.extend(list(h2h_col.find({"league": {"$in": league_filter}})))
        
        # Champions League
        if "Champions League" in selected:
            all_docs.extend(list(ucl_col.find({})))
        
        # Europa League
        if "Europa League" in selected:
            all_docs.extend(list(uel_col.find({})))
    
    total_docs = len(all_docs)
    
    if total_docs == 0:
        print("❌ Nessun documento trovato con i criteri selezionati.")
        return

    # Ciclo principale
    for i, doc in enumerate(all_docs):
        progress = (i + 1) / total_docs * 100
        current_league = doc.get("league") or doc.get("competition", "Coppa")
        print(f"\r⏳ [{current_league}] Doc {i+1}/{total_docs} ({progress:.1f}%) - Match OK: {stats['processed_matches']}", end="")

        doc_id = doc["_id"]
        matches = doc.get("matches", [])
        modified = False
        
        # Determina quale collezione aggiornare
        if "league" in doc:
            target_col = h2h_col
        elif doc.get("competition") == "UCL":
            target_col = ucl_col
        elif doc.get("competition") == "UEL":
            target_col = uel_col
        else:
            continue
        
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
            target_col.update_one(
                {"_id": doc_id},
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