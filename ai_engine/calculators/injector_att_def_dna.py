import os
import sys
from datetime import datetime
import contextlib

# 1. CONFIGURAZIONE PERCORSI
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR)) 
sys.path.append(PROJECT_ROOT)
sys.path.append(CURRENT_DIR)

# --- FIX EMOJI WINDOWS ---
@contextlib.contextmanager
def suppress_stdout():
    with open(os.devnull, "w", encoding='utf-8') as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout

try:
    from config import db
    print("✅ [INJECTOR-ATT-DEF] Connessione stabilita.")
except ImportError as e:
    print(f"❌ [INJECTOR-ATT-DEF] Errore: {e}")
    sys.exit(1)

# --- FUNZIONE MENU INTERATTIVO ---
def select_leagues_interactive(h2h_col):
    """Gestisce la scelta manuale dei campionati."""
    print(f"\n{'='*60}")
    print(f"⚔️  MENU INIEZIONE ATTACCO/DIFESA (DNA)")
    print(f"{'='*60}")
    
    available_leagues = sorted(h2h_col.distinct("league"))
    
    if not available_leagues:
        return {}

    print(f"   [0] 🌍 AGGIORNA TUTTO (Tutti i campionati)")
    print(f"{'-'*60}")
    
    for i, league in enumerate(available_leagues, 1):
        print(f"   [{i}] {league}")
    
    while True:
        choice = input(f"\n👉 La tua scelta: ").strip()
        
        # SCELTA: TUTTO (O premi invio)
        if choice == "0":
            print("✅ Hai scelto: TUTTO.")
            return {} 
            
        try:
            indexes = [int(x.strip()) - 1 for x in choice.split(",") if x.strip().isdigit()]
            if indexes:
                selected_names = [available_leagues[idx] for idx in indexes if 0 <= idx < len(available_leagues)]
                print(f"✅ Hai scelto: {selected_names}")
                return {"league": {"$in": selected_names}}
        except: pass
        print("❌ Scelta non valida.")

def run_injection_att_def(interactive=True):
    teams_col = db["teams"]
    h2h_col = db["h2h_by_round"]

    # 1. GESTIONE AUTOMAZIONE (ORCHESTRA vs MANUALE)
    if interactive:
        query_filter = select_leagues_interactive(h2h_col)
    else:
        # Se chiamato dal Direttore d'Orchestra, NON chiedere nulla -> Fai tutto.
        print("\n🤖 MODALITÀ ORCHESTRA ATTIVA: Aggiorno tutti i campionati in silenzio.")
        query_filter = {}

    print("\n🚀 AVVIO CALCOLO ATTACCO/DIFESA...")
    
    # Statistiche per capire cosa succede
    stats_log = {
        "processed": 0, 
        "skipped_no_team": 0, 
        "data_missing": 0  # Conta quante volte troviamo la squadra ma mancano i valori numerici
    }
    
    # Cache per velocizzare ed evitare di ri-cercare le stesse squadre 1000 volte
    team_cache = {}

    def get_team_stats(tm_id):
        """Cerca i dati 'stats' della squadra usando l'ID."""
        if not tm_id: return None
        
        # Se l'abbiamo già cercata, restituiamo subito il risultato
        if tm_id in team_cache: return team_cache[tm_id]

        doc = teams_col.find_one({"transfermarkt_id": int(tm_id)})
        
        if not doc:
            return None # Squadra non trovata nel DB Teams

        # Recuperiamo l'oggetto stats
        s = doc.get("stats", {})
        
        # --- QUI AVVIENE LA MAGIA ANTI-CRASH E IL RISPETTO DEL CALCOLO ---
        
        # 1. Recupero Valori Grezzi (Raw)
        # Cerchiamo in vari campi perché a volte i nomi cambiano
        raw_att = s.get("attack_home") or s.get("attack") or s.get("strength_attack")
        raw_def = s.get("defense_home") or s.get("defense") or s.get("strength_defense")
        
        # 2. Controllo se i dati esistono (NON SONO NULL)
        final_att = 0
        final_def = 0
        missing_data = False

        # LOGICA ATTACCO
        if raw_att is not None:
            # Applichiamo la TUA formula: (valore / 15) * 100
            try:
                final_att = round((float(raw_att) / 15) * 100, 1)
            except:
                final_att = 0 # Sicurezza estrema
        else:
            missing_data = True # Segnaliamo che manca il dato

        # LOGICA DIFESA
        if raw_def is not None:
            try:
                final_def = round((float(raw_def) / 15) * 100, 1)
            except:
                final_def = 0
        else:
            missing_data = True

        if missing_data:
            stats_log["data_missing"] += 1
            # Se vuoi vedere QUALI squadre hanno dati mancanti, scommenta la riga sotto:
            # print(f"⚠️ Dati mancanti per ID {tm_id} -> {doc.get('name')}")

        result = {"att": final_att, "def": final_def}
        team_cache[tm_id] = result
        return result

    # --- CICLO PRINCIPALE ---
    all_rounds = list(h2h_col.find(query_filter))
    total = len(all_rounds)

    for i, round_doc in enumerate(all_rounds):
        # Stampa progresso solo se non siamo in modalità silenziosa totale
        if i % 10 == 0:
            print(f"\r⏳ Elaborazione Round {i+1}/{total}...", end="")
        
        matches = round_doc.get("matches", [])
        modified = False
        
        for match in matches:
            id_home = match.get("home_tm_id")
            id_away = match.get("away_tm_id")

            # Recupera dati statistici
            h_stats = get_team_stats(id_home)
            a_stats = get_team_stats(id_away)

            if not h_stats or not a_stats:
                stats_log["skipped_no_team"] += 1
                continue

            # Iniezione DNA
            if "h2h_data" not in match or match["h2h_data"] is None:
                match["h2h_data"] = {}
            
            if "h2h_dna" not in match["h2h_data"]:
                match["h2h_data"]["h2h_dna"] = {"home_dna": {}, "away_dna": {}}

            # SCRITTURA DEI VALORI CALCOLATI
            match["h2h_data"]["h2h_dna"]["home_dna"]["att"] = h_stats["att"]
            match["h2h_data"]["h2h_dna"]["home_dna"]["def"] = h_stats["def"]
            
            match["h2h_data"]["h2h_dna"]["away_dna"]["att"] = a_stats["att"]
            match["h2h_data"]["h2h_dna"]["away_dna"]["def"] = a_stats["def"]

            modified = True
            stats_log["processed"] += 1

        if modified:
            h2h_col.update_one(
                {"_id": round_doc["_id"]},
                {"$set": {"matches": matches, "last_att_def_update": datetime.now()}}
            )

    print(f"\n\n✅ OPERAZIONE COMPLETATA!")
    print(f"📊 Match Aggiornati correttamente:     {stats_log['processed']}")
    print(f"⚠️  Squadre con dati NULL (messi a 0): {stats_log['data_missing']}")
    print(f"⏭️  Match Saltati (ID non trovato):     {stats_log['skipped_no_team']}")
    print("="*60)

if __name__ == "__main__":
    # Se lo lanci a mano -> interactive=True (Vedi il menu)
    run_injection_att_def(interactive=True)