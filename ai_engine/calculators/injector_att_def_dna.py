import os
import sys
import re
from datetime import datetime
import dateutil.parser
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
    print(f"⚔️  MENU INIEZIONE ATTACCO/DIFESA (DNA) - LOGICA FISSA")
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
        if choice == "0":
            return {} 
        try:
            indexes = [int(x.strip()) - 1 for x in choice.split(",") if x.strip().isdigit()]
            if indexes:
                selected_names = [available_leagues[idx] for idx in indexes if 0 <= idx < len(available_leagues)]
                print(f"✅ Hai scelto: {selected_names}")
                return {"league": {"$in": selected_names}}
        except: pass
        print("❌ Scelta non valida.")

def get_round_number_from_text(text):
    match = re.search(r'(\d+)', str(text))
    return int(match.group(1)) if match else 0

def find_target_rounds(league_docs, league_name=None):
    """Trova i 3 round target (prec/attuale/succ) usando league_current_rounds come ancora."""
    if not league_docs: return []
    sorted_docs = sorted(league_docs, key=lambda d: get_round_number_from_text(d.get('round_name', '0')))
    anchor_index = -1
    if league_name:
        cr_doc = db['league_current_rounds'].find_one({"league": league_name})
        if cr_doc and cr_doc.get("current_round") is not None:
            current_round = cr_doc["current_round"]
            for i, doc in enumerate(sorted_docs):
                if get_round_number_from_text(doc.get('round_name', '0')) == current_round:
                    anchor_index = i
                    break
    if anchor_index == -1:
        now = datetime.now()
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
                if diff < min_diff: min_diff = diff; anchor_index = i
    if anchor_index == -1: return []
    start_idx = max(0, anchor_index - 1)
    end_idx = min(len(sorted_docs), anchor_index + 2)
    return sorted_docs[start_idx:end_idx]

def run_injection_att_def(interactive=True):
    teams_col = db["teams"]
    h2h_col = db["h2h_by_round"]

    if interactive:
        query_filter = select_leagues_interactive(h2h_col)
        rounds = list(h2h_col.find(query_filter))
    else:
        # Modalità mirata: 2 fasi (projection leggera + query mirata)
        print("\n🤖 MODALITÀ AUTOMATICA MIRATA: Prec/Attuale/Succ per ogni campionato")
        print("   📥 Fase 1: selezione round (query leggera)...")
        light_docs = list(h2h_col.find({}, {"_id": 1, "league": 1, "matches.date": 1, "matches.date_obj": 1}))
        by_league = {}
        for doc in light_docs:
            lg = doc.get("league")
            if lg:
                by_league.setdefault(lg, []).append(doc)
        target_ids = []
        for lg_name, lg_docs in by_league.items():
            target = find_target_rounds(lg_docs, league_name=lg_name)
            target_ids.extend([d["_id"] for d in target])
        print(f"   📥 Fase 2: caricamento {len(target_ids)} round completi...")
        rounds = list(h2h_col.find({"_id": {"$in": target_ids}}))
        print(f"   📋 {len(by_league)} campionati, {len(light_docs)} docs → {len(rounds)} giornate mirate")

    print("\n🚀 AVVIO INIEZIONE ATT/DEF...")
    total_rounds = len(rounds)
    updated_rounds_count = 0
    matches_processed = 0
    team_cache = {}

    for i, round_doc in enumerate(rounds):
        round_id = round_doc["_id"]
        matches_list = round_doc.get("matches", [])
        has_changes = False
        
        for match in matches_list:
            home_id = match.get("home_tm_id")
            away_id = match.get("away_tm_id")

            if not home_id or not away_id:
                continue

            # --- LOOKUP SQUADRE ---
            if home_id in team_cache: home_team = team_cache[home_id]
            else:
                home_team = teams_col.find_one({"transfermarkt_id": home_id})
                team_cache[home_id] = home_team

            if away_id in team_cache: away_team = team_cache[away_id]
            else:
                away_team = teams_col.find_one({"transfermarkt_id": away_id})
                team_cache[away_id] = away_team

            # --- INIZIALIZZAZIONE STRUTTURA DNA ---
            if "h2h_data" not in match or match["h2h_data"] is None:
                match["h2h_data"] = {}
            if "h2h_dna" not in match["h2h_data"]:
                match["h2h_data"]["h2h_dna"] = {}
            
            dna = match["h2h_data"]["h2h_dna"]
            if "home_dna" not in dna: dna["home_dna"] = {}
            if "away_dna" not in dna: dna["away_dna"] = {}

            # --- LOGICA ESATTA RICHIESTA ---
            # SQUADRA CASA
            if home_team and "scores" in home_team:
                s = home_team["scores"]
                dna["home_dna"]["att"] = round(((s.get("attack_home") or 0) / 15) * 100, 1)
                dna["home_dna"]["def"] = round(((s.get("defense_home") or 0) / 10) * 100, 1)
                has_changes = True

            # SQUADRA TRASFERTA
            if away_team and "scores" in away_team:
                s = away_team["scores"]
                dna["away_dna"]["att"] = round(((s.get("attack_away") or 0) / 15) * 100, 1)
                dna["away_dna"]["def"] = round(((s.get("defense_away") or 0) / 10) * 100, 1)
                has_changes = True
            
            if has_changes:
                matches_processed += 1

        if has_changes:
            h2h_col.update_one(
                {"_id": round_id}, 
                {"$set": {"matches": matches_list, "last_att_def_update": datetime.now()}}
            )
            updated_rounds_count += 1
        
        print(f"\r⏳ Elaborazione: {i+1}/{total_rounds} giornate...", end="")

    print(f"\n\n✅ FINE. Giornate: {updated_rounds_count}, Match: {matches_processed}")

if __name__ == "__main__":
    run_injection_att_def(interactive=True)