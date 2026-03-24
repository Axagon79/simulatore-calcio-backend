"""
Bootstrap rapido per un singolo campionato nuovo.
Popola tutti i campi mancanti in h2h_by_round senza rielaborare gli altri campionati.

Uso: python bootstrap_single_league.py "League One"
"""
import os
import sys
import time
import re

# --- FIX PERCORSI ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
CALCULATORS = os.path.join(PROJECT_ROOT, "ai_engine", "calculators")
FREQUENTI = os.path.join(PROJECT_ROOT, "ai_engine", "Aggiornamenti", "frequenti")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, CALCULATORS)
sys.path.insert(0, FREQUENTI)

from config import db

TARGET_LEAGUE = sys.argv[1] if len(sys.argv) > 1 else "League One"
h2h_col = db["h2h_by_round"]
teams_col = db["teams"]

def step_timer(name):
    class Timer:
        def __init__(self, n): self.name = n
        def __enter__(self): self.t = time.time(); print(f"\n{'='*60}\n>> {self.name}\n{'='*60}"); return self
        def __exit__(self, *a): print(f"   Completato in {time.time()-self.t:.1f}s")
    return Timer(name)

# ============================================================
# STEP 1: Enrich con TM IDs (home_tm_id, away_tm_id, mongo_id)
# ============================================================
def find_team_in_db(team_name, league=None):
    """Cerca squadra per nome, alias, aliases_transfermarkt."""
    base_filter = {}
    if league:
        base_filter["league"] = league
    # Nome esatto
    team = teams_col.find_one({**base_filter, "name": team_name})
    if team and "transfermarkt_id" in team:
        return team
    # Alias
    team = teams_col.find_one({**base_filter, "aliases": team_name})
    if team and "transfermarkt_id" in team:
        return team
    # Aliases transfermarkt
    team = teams_col.find_one({**base_filter, "aliases_transfermarkt": team_name})
    if team and "transfermarkt_id" in team:
        return team
    # Senza filtro lega (fallback)
    if league:
        return find_team_in_db(team_name, league=None)
    return None

def step1_enrich_tm_ids():
    with step_timer(f"STEP 1: Enrich TM IDs per {TARGET_LEAGUE}"):
        rounds = list(h2h_col.find({"league": TARGET_LEAGUE}))
        print(f"   Round da processare: {len(rounds)}")
        not_found = set()
        enriched_total = 0

        for round_doc in rounds:
            modified = False
            for match in round_doc.get("matches", []):
                home = match.get("home", "")
                away = match.get("away", "")

                if not match.get("home_tm_id"):
                    result = find_team_in_db(home, league=TARGET_LEAGUE)
                    if result:
                        match["home_tm_id"] = result.get("transfermarkt_id")
                        match["home_mongo_id"] = str(result.get("_id", ""))
                        modified = True
                        enriched_total += 1
                    else:
                        not_found.add(home)

                if not match.get("away_tm_id"):
                    result = find_team_in_db(away, league=TARGET_LEAGUE)
                    if result:
                        match["away_tm_id"] = result.get("transfermarkt_id")
                        match["away_mongo_id"] = str(result.get("_id", ""))
                        modified = True
                        enriched_total += 1
                    else:
                        not_found.add(away)

            if modified:
                h2h_col.update_one({"_id": round_doc["_id"]}, {"$set": {"matches": round_doc["matches"]}})

        print(f"   Enriched: {enriched_total} team IDs")
        if not_found:
            print(f"   Non trovate ({len(not_found)}): {sorted(not_found)}")

# ============================================================
# STEP 2: Calculate H2H scores (via calculate_h2h_v2)
# ============================================================
def step2_calculate_h2h():
    with step_timer(f"STEP 2: Calculate H2H per {TARGET_LEAGUE}"):
        from calculate_h2h_v2 import run_calculator
        run_calculator(target_league=TARGET_LEAGUE)

# ============================================================
# STEP 3: Inject ATT/DEF DNA
# ============================================================
def step3_inject_att_def():
    with step_timer(f"STEP 3: Inject ATT/DEF DNA per {TARGET_LEAGUE}"):
        try:
            import importlib
            mod = importlib.import_module("injector_att_def_dna")
            mod.run_injection_att_def(interactive=False)
        except Exception as e:
            print(f"   WARN step 3: {e} — continuiamo")

# ============================================================
# STEP 4: Inject TEC + Formazioni
# ============================================================
def step4_inject_tec_formazioni():
    with step_timer(f"STEP 4: Inject TEC + Formazioni per {TARGET_LEAGUE}"):
        try:
            import importlib
            mod = importlib.import_module("injector_dna_tec_e_formazioni")
            mod.run_injection(interactive=False)
        except Exception as e:
            print(f"   WARN step 4: {e} — continuiamo")

# ============================================================
# STEP 5: Inject DNA VAL (valore rosa)
# ============================================================
def step5_inject_val():
    with step_timer(f"STEP 5: Inject DNA VAL per {TARGET_LEAGUE}"):
        try:
            import importlib
            mod = importlib.import_module("injector_dna_val")
            mod.run_injection_val(interactive=False)
        except Exception as e:
            print(f"   WARN step 5: {e} — continuiamo")

# ============================================================
# STEP 6: Update Fattore Campo
# ============================================================
def step6_fattore_campo():
    with step_timer(f"STEP 6: Fattore Campo per {TARGET_LEAGUE}"):
        from update_fattore_campo import calculate_field_factor, _teams_by_id, _teams_by_name, _teams_by_league
        import update_fattore_campo as ufc

        # Init cache teams
        all_teams_list = list(teams_col.find({}))
        ufc._teams_by_id = {}
        ufc._teams_by_name = {}
        ufc._teams_by_league = {}
        ufc._league_avg_cache = {}
        for t in all_teams_list:
            ufc._teams_by_id[str(t["_id"])] = t
            name = t.get("name")
            if name: ufc._teams_by_name[name.lower()] = t
            official = t.get("official_name")
            if official: ufc._teams_by_name[official.lower()] = t
            aliases = t.get("aliases")
            if isinstance(aliases, list):
                for a in aliases:
                    if isinstance(a, str): ufc._teams_by_name[a.lower()] = t
            elif isinstance(aliases, dict):
                for val in aliases.values():
                    if isinstance(val, str): ufc._teams_by_name[val.lower()] = t
            league = t.get("ranking", {}).get("league")
            if league: ufc._teams_by_league.setdefault(league, []).append(t)

        rounds = list(h2h_col.find({"league": TARGET_LEAGUE}))
        updated = 0
        for r in rounds:
            modified = False
            for m in r.get("matches", []):
                h_name = m.get("home")
                a_name = m.get("away")
                h_id = m.get("home_tm_id")
                a_id = m.get("away_tm_id")
                raw_h, raw_a = calculate_field_factor(h_id, h_name, a_id, a_name)
                pct_h = max(10, min(99, int((raw_h / 7.0) * 100)))
                pct_a = max(10, min(99, int((raw_a / 7.0) * 100)))
                h2h = m.get("h2h_data") or {}
                if h2h.get("fattore_campo", {}).get("field_home") != pct_h:
                    h2h["fattore_campo"] = {"field_home": pct_h, "field_away": pct_a}
                    m["h2h_data"] = h2h
                    modified = True
            if modified:
                h2h_col.update_one({"_id": r["_id"]}, {"$set": {"matches": r["matches"]}})
                updated += 1
        print(f"   Round aggiornati: {updated}/{len(rounds)}")

# ============================================================
# STEP 7: Lucifero + Trend
# ============================================================
def step7_lucifero():
    with step_timer(f"STEP 7: Lucifero per {TARGET_LEAGUE}"):
        try:
            import cron_update_lucifero as cul
            cul.ALL_DOCS = list(h2h_col.find({}))
            cul.esegui_aggiornamento()
        except Exception as e:
            print(f"   WARN step 7: {e} — continuiamo")

# ============================================================
# STEP 8: Inject Standings (rank, points)
# ============================================================
def step8_standings():
    with step_timer(f"STEP 8: Standings per {TARGET_LEAGUE}"):
        try:
            from injector_standings_to_matches import run_injection
            run_injection()
        except Exception as e:
            print(f"   Nota: {e}")

# ============================================================
# Helper: run injector filtrato su singola lega
# ============================================================
def _run_injector_filtered(module_name, func_name):
    """Esegue un injector standard ma solo sui round della lega target."""
    import importlib
    mod = importlib.import_module(module_name)
    func = getattr(mod, func_name)

    # Gli injector in modalità interactive permettono di scegliere
    # Proviamo con query filtrata direttamente
    rounds = list(h2h_col.find({"league": TARGET_LEAGUE}))
    print(f"   Round {TARGET_LEAGUE}: {len(rounds)} (injector generico)")

    # Monkey-patch temporaneo per filtrare
    original_find = h2h_col.find
    def filtered_find(query=None, *args, **kwargs):
        if query is None or query == {}:
            return original_find({"league": TARGET_LEAGUE}, *args, **kwargs)
        if "league" not in (query or {}):
            query = dict(query or {})
            query["league"] = TARGET_LEAGUE
        return original_find(query, *args, **kwargs)

    h2h_col.find = filtered_find
    try:
        func(interactive=False)
    finally:
        h2h_col.find = original_find


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    start = time.time()
    print(f"\n{'#'*60}")
    print(f"  BOOTSTRAP CAMPIONATO: {TARGET_LEAGUE}")
    print(f"{'#'*60}")

    # Verifica che la lega esista
    count = h2h_col.count_documents({"league": TARGET_LEAGUE})
    if count == 0:
        print(f"\n  ERRORE: Nessun documento trovato per '{TARGET_LEAGUE}' in h2h_by_round!")
        sys.exit(1)
    print(f"\n  Trovati {count} round per {TARGET_LEAGUE}")

    step1_enrich_tm_ids()
    step2_calculate_h2h()
    step3_inject_att_def()
    step4_inject_tec_formazioni()
    step5_inject_val()
    step6_fattore_campo()
    step7_lucifero()
    step8_standings()

    elapsed = time.time() - start
    print(f"\n{'#'*60}")
    print(f"  BOOTSTRAP COMPLETATO in {elapsed:.0f}s")
    print(f"{'#'*60}")
