import os
import sys
import re
from datetime import datetime
import dateutil.parser

# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

try:
    from config import db
    print("✅ [INJECTOR-VAL] Connessione al database stabilita.")
except ImportError:
    print("❌ [INJECTOR-VAL] Errore: config.py non trovato.")
    sys.exit(1)

# --- FUNZIONE MENU INTERATTIVO ---
def select_leagues_interactive(h2h_col):
    """
    Mostra i campionati disponibili e chiede all'utente quali processare.
    Restituisce un filtro MongoDB query.
    """
    print(f"\n{'='*60}")
    print(f"💎 MENU INIEZIONE VALORE (VAL)")
    print(f"{'='*60}")
    
    # Recupera i campionati distinti presenti nel DB
    available_leagues = sorted(h2h_col.distinct("league"))
    
    if not available_leagues:
        print("⚠️  Nessun campo 'league' trovato in h2h_by_round.")
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
            if not selected_indexes:
                print("❌ Nessun numero valido inserito.")
                continue

            selected_names = []
            for idx in selected_indexes:
                if 0 <= idx < len(available_leagues):
                    selected_names.append(available_leagues[idx])
            
            if not selected_names:
                print("❌ Scelta non valida. Riprova.")
                continue

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

def run_injection_val(interactive=True):
    """
    Estrae 'strengthScore09' da Teams e lo inietta come percentuale (0-100)
    nella struttura nidificata DNA di h2h_by_round sotto la chiave 'val'.
    VERSIONE TURBO ⚡ + MENU
    """
    teams_col = db["teams"]
    h2h_col = db["h2h_by_round"]

    print("\n🚀 Inizio aggiornamento asse VALORE (VAL) - Modalità TURBO...")

    # 1. CARICAMENTO SQUADRE IN MEMORIA (TURBO ⚡)
    print("   📥 Caricamento dati squadre in memoria (attendere)...")
    all_teams = list(teams_col.find({}, {"transfermarkt_id": 1, "stats.strengthScore09": 1}))

    team_val_map = {}
    for t in all_teams:
        tm_id = t.get("transfermarkt_id")
        if tm_id:
            raw_score = t.get("stats", {}).get("strengthScore09", 0) or 0
            team_val_map[tm_id] = round(raw_score * 10, 1)

    print(f"   ✅ Mappate {len(team_val_map)} squadre.")

    # 2. RECUPERO GIORNATE
    if interactive:
        query_filter = select_leagues_interactive(h2h_col)
        all_rounds = list(h2h_col.find(query_filter))
    else:
        # Modalità mirata: 2 fasi (projection leggera + query mirata)
        print("🤖 MODALITÀ AUTOMATICA MIRATA: Prec/Attuale/Succ per ogni campionato")
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
        all_rounds = list(h2h_col.find({"_id": {"$in": target_ids}}))
        print(f"   📋 {len(by_league)} campionati, {len(light_docs)} docs → {len(all_rounds)} giornate mirate")
    
    if not all_rounds:
        print("⚠️  Nessuna giornata trovata con i filtri selezionati.")
        return

    matches_processed = 0
    rounds_updated = 0

    print(f"   🔄 Elaborazione di {len(all_rounds)} giornate...")

    for round_doc in all_rounds:
        round_id = round_doc["_id"]
        matches = round_doc.get("matches", [])
        modified = False

        for match in matches:
            id_home = match.get("home_tm_id")
            id_away = match.get("away_tm_id")

            if id_home is None or id_away is None:
                continue

            # Lookup istantaneo dal dizionario (senza chiamare il DB)
            val_home = team_val_map.get(int(id_home), 0)
            val_away = team_val_map.get(int(id_away), 0)

            # --- COSTRUZIONE STRUTTURA NIDIFICATA (DNA System) ---
            if "h2h_data" not in match or match["h2h_data"] is None:
                match["h2h_data"] = {}
            
            if "h2h_dna" not in match["h2h_data"]:
                match["h2h_data"]["h2h_dna"] = {
                    "home_dna": {},
                    "away_dna": {}
                }

            # Iniezione del campo VALORE ('val')
            match["h2h_data"]["h2h_dna"]["home_dna"]["val"] = val_home
            match["h2h_data"]["h2h_dna"]["away_dna"]["val"] = val_away
            
            modified = True
            matches_processed += 1

        # Aggiornamento del documento su MongoDB (solo se modificato)
        if modified:
            h2h_col.update_one(
                {"_id": round_id},
                {"$set": {"matches": matches, "last_dna_val_update": datetime.now()}}
            )
            rounds_updated += 1

    print("-" * 50)
    print(f"🏁 FINE INIEZIONE VAL.")
    print(f"   📊 Giornate aggiornate: {rounds_updated}")
    print(f"   ⚽ Partite processate: {matches_processed}")
    print("-" * 50)

if __name__ == "__main__":
    # interactive=True significa che mostrerà il menu
    run_injection_val(interactive=True)