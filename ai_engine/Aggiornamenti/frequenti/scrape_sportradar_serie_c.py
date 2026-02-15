"""
SCRAPER FORMAZIONI SERIE C — Sportradar + Injector h2h_by_round
================================================================
1. Scarica rose di tutte le 59 squadre Serie C da Sportradar
2. Genera titolari/panchinari con algoritmo basato su minuti
3. Inietta formazioni in h2h_by_round (stesso formato FBRef)

Uso: python scrape_sportradar_serie_c.py [--scrape] [--inject] [--test]
  --scrape  = scarica rose da Sportradar (salva in JSON cache)
  --inject  = inietta formazioni in h2h_by_round dal JSON cache
  --test    = scrape solo 2 squadre di test
  (senza flag = scrape + inject)
"""
import os
import sys
import json
import time
import re
from datetime import datetime

# Setup paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(CURRENT_DIR)))
sys.path.insert(0, PROJECT_ROOT)

from config import db

# ============================================================
# CONFIGURAZIONE
# ============================================================

CACHE_FILE = os.path.join(PROJECT_ROOT, "cache", "sportradar_serie_c_rosters.json")
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

# Mapping ruoli Sportradar → interni
ROLE_MAP = {"POR": "GK", "DIF": "DIF", "CENT": "MID", "ATT": "ATT"}

# Moduli: come parse_formation in calculate_team_rating.py
FORMATION_MAPPING = {
    "3-4-2-1": "3-4-3",
    "4-2-2-2": "4-4-2",
    "4-2-3-1": "4-5-1",
    "4-3-1-2": "4-3-3",
}

# ============================================================
# TEAM IDS — Tutti i 3 gironi Serie C
# ============================================================

GIRONI = {
    "A": {
        "season_id": 133200,
        "teams": {
            "ALBINOLEFFE": 2732, "Alcione Milano": 834514, "Arzignano V.": 170634,
            "CITTADELLA": 2717, "Dolomiti Bellunesi": 834506, "FERALPISALO": 37173,
            "Giana Erminio": 117232, "Inter U23": 1275976, "L.R. Vicenza": 2722,
            "Lecco": 7933, "Lumezzane": 2738, "NOVARA": 2767,
            "Ospitaletto": 1158829, "PRO VERCELLI": 2769, "Pergolettese": 113757,
            "Pro Patria": 2746, "Renate": 36586, "Trento": 347514,
            "Triestina": 2724, "Union Brescia": 1276628, "Virtus Verona": 113761,
        }
    },
    "B": {
        "season_id": 133202,
        "teams": {
            "AREZZO": 2731, "ASCOLI": 2707, "Bra": 111883,
            "Campobasso": 43858, "Carpi": 834548, "Forlì FC": 2783,
            "Gubbio": 2782, "Guidonia Montecelio": 281373, "Juventus Next Gen": 474236,
            "Livorno": 2726, "PERUGIA": 2698, "PONTEDERA": 24745,
            "Pianese": 117356, "Pineto": 275501, "Ravenna": 5318,
            "SAMBENEDETTESE": 2750, "TERNANA": 2708, "Torres": 2753,
            "Vis Pesaro": 2754,
        }
    },
    "C": {
        "season_id": 133204,
        "teams": {
            "AZ Picerno": 223518, "Atalanta U23": 1037333, "Audace Cerignola": 368732,
            "BENEVENTO": 2759, "CASERTANA": 53857, "COSENZA": 2716,
            "CROTONE": 2718, "Casarano": 43684, "Catania": 2725,
            "Cavese": 6361, "Foggia": 2803, "Giugliano": 5307,
            "Latina": 44069, "MONOPOLI": 25137, "Potenza": 7936,
            "SALERNITANA": 2710, "SIRACUSA": 37177, "Sorrento": 7937,
            "TRAPANI": 43686, "Team Altamura": 368724,
        }
    }
}

# Mapping nomi Sportradar → nomi nel DB teams
# (costruito al volo cercando nel DB, con fallback manuale)
NOME_OVERRIDE = {
    "ALBINOLEFFE": "AlbinoLeffe",
    "L.R. Vicenza": "Vicenza",
    "NOVARA": "Novara",
    "PRO VERCELLI": "Pro Vercelli",
    "FERALPISALO": "FeralpiSalo",
    "CITTADELLA": "Cittadella",
    "Inter U23": "Inter U23",
    "Dolomiti Bellunesi": "D. Bellunesi",
    "Alcione Milano": "Alcione",
    "Arzignano V.": "Arzignano",
    "Union Brescia": "Union Brescia",
    "AREZZO": "Arezzo",
    "ASCOLI": "Ascoli",
    "Forlì FC": "Forli",
    "Juventus Next Gen": "Juventus U23",
    "PERUGIA": "Perugia",
    "PONTEDERA": "Pontedera",
    "SAMBENEDETTESE": "Sambenedettese",
    "TERNANA": "Ternana",
    "Guidonia Montecelio": "Guidonia",
    "Carpi": "Athletic Carpi",
    "AZ Picerno": "Picerno",
    "Atalanta U23": "Atalanta B",
    "Audace Cerignola": "A. Cerignola",
    "BENEVENTO": "Benevento",
    "CASERTANA": "Casertana",
    "COSENZA": "Cosenza",
    "CROTONE": "Crotone",
    "MONOPOLI": "Monopoli",
    "SALERNITANA": "Salernitana",
    "SIRACUSA": "Siracusa",
    "TRAPANI": "Trapani",
    "Team Altamura": "Altamura",
}


# ============================================================
# PARTE 1: SCRAPING
# ============================================================

def scrape_all_teams(test_mode=False):
    """Scarica rose da Sportradar per tutte le 59 squadre Serie C"""
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--start-maximized")

    print("=" * 70)
    print("SCRAPER SPORTRADAR — ROSE SERIE C")
    print("=" * 70)

    print("\nAvvio Chrome...")
    driver = uc.Chrome(options=options, headless=False, user_multi_procs=True)
    time.sleep(2)

    all_rosters = {}
    total_teams = sum(len(g["teams"]) for g in GIRONI.values())
    current = 0
    errors = []

    try:
        for girone_name, girone_data in GIRONI.items():
            season_id = girone_data["season_id"]
            teams = girone_data["teams"]

            print(f"\n{'='*50}")
            print(f"GIRONE {girone_name} (season {season_id}) — {len(teams)} squadre")
            print(f"{'='*50}")

            for team_name, team_id in teams.items():
                current += 1

                if test_mode and current > 2:
                    print(f"\n[TEST MODE] Stop dopo 2 squadre")
                    break

                db_name = NOME_OVERRIDE.get(team_name, team_name)
                print(f"\n[{current}/{total_teams}] {team_name} (ID: {team_id}) → DB: '{db_name}'")

                url = f"https://s5.sir.sportradar.com/snai/it/1/season/{season_id}/team/{team_id}"

                try:
                    driver.get(url)
                    time.sleep(6)

                    # Scroll per triggerare lazy loading
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2)
                    driver.execute_script("window.scrollTo(0, 0)")
                    time.sleep(1)

                    # Cerca le tabelle
                    tables = driver.find_elements(By.TAG_NAME, "table")

                    # Trova la tabella rosa (quella con più righe e nomi "Cognome, Nome")
                    roster_table = None
                    for table in tables:
                        rows = table.find_elements(By.TAG_NAME, "tr")
                        if len(rows) > 15:  # La rosa ha almeno 15+ righe
                            # Verifica che abbia nomi nel formato "Cognome, Nome"
                            sample_cells = table.find_elements(By.TAG_NAME, "td")
                            sample_text = " ".join([c.text for c in sample_cells[:20]])
                            if "," in sample_text and any(r in sample_text for r in ["POR", "DIF", "CENT", "ATT"]):
                                roster_table = table
                                break

                    if not roster_table:
                        print(f"  ⚠️ Tabella rosa non trovata!")
                        errors.append(team_name)
                        continue

                    # Parsa giocatori
                    rows = roster_table.find_elements(By.TAG_NAME, "tr")
                    players = []

                    for row in rows:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if len(cells) < 5:
                            continue

                        cell_texts = [c.text.strip() for c in cells]

                        # Trova la cella con il nome (formato "Cognome, Nome")
                        name_cell = None
                        name_idx = -1
                        for ci, ct in enumerate(cell_texts):
                            if "," in ct and len(ct) > 3 and not ct.replace(",", "").replace(" ", "").isdigit():
                                name_cell = ct
                                name_idx = ci
                                break

                        if not name_cell:
                            continue

                        # Estrai dati
                        ruolo_sr = cell_texts[0] if cell_texts[0] in ["POR", "DIF", "CENT", "ATT"] else ""
                        numero = cell_texts[1] if len(cell_texts) > 1 else ""

                        # Minuti e presenze sono dopo il nome e DOB
                        # Struttura: [Ruolo, #, (flag), Nome, DOB, Presenze, Minuti, Gol, Gialli, Rossi]
                        presenze_raw = cell_texts[name_idx + 2] if len(cell_texts) > name_idx + 2 else ""
                        minuti_raw = cell_texts[name_idx + 3] if len(cell_texts) > name_idx + 3 else ""
                        gol_raw = cell_texts[name_idx + 4] if len(cell_texts) > name_idx + 4 else ""

                        # Parse presenze (es. "25 (1)" → 25 titolare + 1 sub)
                        presenze = 0
                        sub = 0
                        if presenze_raw:
                            m = re.match(r'(\d+)?\s*\(?(\d+)?\)?', presenze_raw)
                            if m:
                                presenze = int(m.group(1)) if m.group(1) else 0
                                sub = int(m.group(2)) if m.group(2) else 0

                        # Parse minuti
                        try:
                            minuti = int(minuti_raw.replace("'", "").replace(",", "").strip()) if minuti_raw else 0
                        except:
                            minuti = 0

                        # Parse gol
                        try:
                            gol = int(gol_raw) if gol_raw else 0
                        except:
                            gol = 0

                        # Cognome, Nome → parse
                        parts = name_cell.split(",")
                        cognome = parts[0].strip()
                        nome = parts[1].strip() if len(parts) > 1 else ""

                        players.append({
                            "ruolo": ROLE_MAP.get(ruolo_sr, ""),
                            "ruolo_sr": ruolo_sr,
                            "numero": numero,
                            "cognome": cognome,
                            "nome": nome,
                            "nome_completo": f"{nome} {cognome}".strip(),
                            "presenze": presenze,
                            "sub": sub,
                            "minuti": minuti,
                            "gol": gol
                        })

                    print(f"  ✅ {len(players)} giocatori (POR:{sum(1 for p in players if p['ruolo']=='GK')}, "
                          f"DIF:{sum(1 for p in players if p['ruolo']=='DIF')}, "
                          f"MID:{sum(1 for p in players if p['ruolo']=='MID')}, "
                          f"ATT:{sum(1 for p in players if p['ruolo']=='ATT')})")

                    all_rosters[db_name] = {
                        "sportradar_name": team_name,
                        "sportradar_id": team_id,
                        "girone": girone_name,
                        "season_id": season_id,
                        "players": players,
                        "scraped_at": datetime.now().isoformat()
                    }

                    # Salva incrementale ogni 5 squadre
                    if current % 5 == 0:
                        _save_cache(all_rosters)
                        print(f"  💾 Cache salvata ({len(all_rosters)} squadre)")

                except Exception as e:
                    print(f"  ❌ Errore: {e}")
                    errors.append(team_name)
                    continue

            if test_mode:
                break

    finally:
        driver.quit()
        _save_cache(all_rosters)

    print(f"\n{'='*70}")
    print(f"SCRAPING COMPLETATO")
    print(f"  Squadre scaricate: {len(all_rosters)}/{total_teams}")
    if errors:
        print(f"  Errori: {errors}")
    print(f"  Cache: {CACHE_FILE}")
    print(f"{'='*70}\n")

    return all_rosters


def _save_cache(data):
    """Salva cache JSON"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_cache():
    """Carica cache JSON"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ============================================================
# PARTE 2: GENERAZIONE FORMAZIONI
# ============================================================

def parse_formation(formation_str):
    """Converte modulo in {DIF, MID, ATT}"""
    if not formation_str:
        formation_str = "4-3-3"

    formation_clean = formation_str.strip()
    if formation_clean in FORMATION_MAPPING:
        formation_clean = FORMATION_MAPPING[formation_clean]

    parts = formation_clean.split("-")
    try:
        numbers = [int(p.strip()) for p in parts]
    except:
        numbers = [4, 3, 3]

    if len(numbers) == 3:
        return {"DIF": numbers[0], "MID": numbers[1], "ATT": numbers[2]}
    else:
        return {"DIF": 4, "MID": 3, "ATT": 3}


def generate_formation_for_team(players, formation_str):
    """Genera titolari e panchinari da lista giocatori Sportradar"""

    formation = parse_formation(formation_str)

    # Separa per ruolo e ordina per minuti
    gk_all = sorted([p for p in players if p["ruolo"] == "GK"], key=lambda x: x["minuti"], reverse=True)
    dif_all = sorted([p for p in players if p["ruolo"] == "DIF"], key=lambda x: x["minuti"], reverse=True)
    mid_all = sorted([p for p in players if p["ruolo"] == "MID"], key=lambda x: x["minuti"], reverse=True)
    att_all = sorted([p for p in players if p["ruolo"] == "ATT"], key=lambda x: x["minuti"], reverse=True)

    # Giocatori senza ruolo → assegna al ruolo con meno giocatori
    no_role = [p for p in players if not p["ruolo"]]
    for p in no_role:
        counts = {"DIF": len(dif_all), "MID": len(mid_all), "ATT": len(att_all)}
        min_role = min(counts, key=counts.get)
        p["ruolo"] = min_role
        if min_role == "DIF":
            dif_all.append(p)
        elif min_role == "MID":
            mid_all.append(p)
        else:
            att_all.append(p)

    # Ricalcola ordinamento
    dif_all.sort(key=lambda x: x["minuti"], reverse=True)
    mid_all.sort(key=lambda x: x["minuti"], reverse=True)
    att_all.sort(key=lambda x: x["minuti"], reverse=True)

    # Rating base: 6.0 per tutti (non abbiamo rating FBRef per Serie C)
    BASE_RATING = 6.0

    # --- TITOLARI ---
    starters = []

    # GK
    if gk_all:
        gk = gk_all[0]
        starters.append({
            "role": "GK",
            "player": gk["nome_completo"],
            "rating": BASE_RATING,
            "minutes_90s": round(gk["minuti"] / 90, 1)
        })

    # DEF
    for i in range(min(formation["DIF"], len(dif_all))):
        p = dif_all[i]
        starters.append({
            "role": "DIF",
            "player": p["nome_completo"],
            "rating": BASE_RATING,
            "minutes_90s": round(p["minuti"] / 90, 1)
        })

    # MID
    for i in range(min(formation["MID"], len(mid_all))):
        p = mid_all[i]
        starters.append({
            "role": "MID",
            "player": p["nome_completo"],
            "rating": BASE_RATING,
            "minutes_90s": round(p["minuti"] / 90, 1)
        })

    # ATT
    for i in range(min(formation["ATT"], len(att_all))):
        p = att_all[i]
        starters.append({
            "role": "ATT",
            "player": p["nome_completo"],
            "rating": BASE_RATING,
            "minutes_90s": round(p["minuti"] / 90, 1)
        })

    # --- PANCHINARI ---
    bench = []
    used_names = set(s["player"] for s in starters)

    # GK riserva
    if len(gk_all) > 1:
        gk2 = gk_all[1]
        bench.append({
            "role": "GK",
            "player": gk2["nome_completo"],
            "rating": BASE_RATING,
            "minutes_90s": round(gk2["minuti"] / 90, 1),
            "effective_rating": BASE_RATING * 0.85
        })
        used_names.add(gk2["nome_completo"])

    # 2 DIF panchina
    bench_count = 0
    for i in range(formation["DIF"], len(dif_all)):
        if bench_count >= 2:
            break
        p = dif_all[i]
        if p["nome_completo"] not in used_names:
            bench.append({
                "role": "DIF",
                "player": p["nome_completo"],
                "rating": BASE_RATING,
                "minutes_90s": round(p["minuti"] / 90, 1),
                "effective_rating": BASE_RATING * 0.85
            })
            used_names.add(p["nome_completo"])
            bench_count += 1

    # 2 MID panchina
    bench_count = 0
    for i in range(formation["MID"], len(mid_all)):
        if bench_count >= 2:
            break
        p = mid_all[i]
        if p["nome_completo"] not in used_names:
            bench.append({
                "role": "MID",
                "player": p["nome_completo"],
                "rating": BASE_RATING,
                "minutes_90s": round(p["minuti"] / 90, 1),
                "effective_rating": BASE_RATING * 0.85
            })
            used_names.add(p["nome_completo"])
            bench_count += 1

    # 2 ATT panchina
    bench_count = 0
    for i in range(formation["ATT"], len(att_all)):
        if bench_count >= 2:
            break
        p = att_all[i]
        if p["nome_completo"] not in used_names:
            bench.append({
                "role": "ATT",
                "player": p["nome_completo"],
                "rating": BASE_RATING,
                "minutes_90s": round(p["minuti"] / 90, 1),
                "effective_rating": BASE_RATING * 0.85
            })
            used_names.add(p["nome_completo"])
            bench_count += 1

    return {
        "formation": formation_str,
        "starters": starters,
        "bench": bench
    }


# ============================================================
# PARTE 3: INJECTION IN h2h_by_round
# ============================================================

def inject_formations():
    """Inietta formazioni Serie C in h2h_by_round"""
    print("=" * 70)
    print("INJECTION FORMAZIONI SERIE C → h2h_by_round")
    print("=" * 70)

    # Carica cache
    rosters = _load_cache()
    if not rosters:
        print("❌ Cache vuota! Esegui prima --scrape")
        return

    print(f"📋 Rose caricate: {len(rosters)} squadre")

    # Carica moduli dal DB teams
    teams_col = db["teams"]
    h2h_col = db["h2h_by_round"]

    team_formations = {}
    for team_doc in teams_col.find({"league": {"$regex": "Serie C"}}, {"name": 1, "formation": 1, "aliases": 1}):
        name = team_doc.get("name")
        formation = team_doc.get("formation", "4-3-3")
        team_formations[name] = formation
        # Anche alias
        for alias in team_doc.get("aliases", []):
            if isinstance(alias, str):
                team_formations[alias] = formation

    print(f"📐 Moduli caricati: {len(team_formations)} (con alias)")

    # Pre-genera formazioni per tutte le squadre
    team_lineups = {}
    for db_name, roster_data in rosters.items():
        formation_str = team_formations.get(db_name, "4-3-3")
        lineup = generate_formation_for_team(roster_data["players"], formation_str)
        team_lineups[db_name] = lineup

    print(f"⚽ Formazioni generate: {len(team_lineups)}")

    # Costruisci lookup per nome squadra (nome DB → lineup)
    # Include anche alias dal DB
    name_to_lineup = {}
    for db_name, lineup in team_lineups.items():
        name_to_lineup[db_name] = lineup
        name_to_lineup[db_name.lower()] = lineup

    # Aggiungi alias da teams collection
    for team_doc in teams_col.find({"league": {"$regex": "Serie C"}}, {"name": 1, "aliases": 1}):
        name = team_doc.get("name")
        if name in team_lineups:
            for alias in team_doc.get("aliases", []):
                if isinstance(alias, str):
                    name_to_lineup[alias] = team_lineups[name]
                    name_to_lineup[alias.lower()] = team_lineups[name]

    # Cerca documenti h2h_by_round Serie C
    serie_c_docs = list(h2h_col.find({"league": {"$regex": "Serie C"}}))
    print(f"\n📄 Documenti h2h_by_round Serie C: {len(serie_c_docs)}")

    stats = {"injected": 0, "skipped_home": 0, "skipped_away": 0, "total_matches": 0}

    for doc in serie_c_docs:
        doc_id = doc["_id"]
        matches = doc.get("matches", [])
        modified = False

        for match in matches:
            stats["total_matches"] += 1
            home = match.get("home") or match.get("home_team", "")
            away = match.get("away") or match.get("away_team", "")

            # Lookup formazioni
            h_lineup = name_to_lineup.get(home) or name_to_lineup.get(home.lower())
            a_lineup = name_to_lineup.get(away) or name_to_lineup.get(away.lower())

            if not h_lineup:
                stats["skipped_home"] += 1
                continue
            if not a_lineup:
                stats["skipped_away"] += 1
                continue

            # Inizializza h2h_data se mancante
            if "h2h_data" not in match or match["h2h_data"] is None:
                match["h2h_data"] = {}

            # Inietta formazioni
            match["h2h_data"]["formazioni"] = {
                "home_squad": {
                    "modulo": h_lineup["formation"],
                    "titolari": h_lineup["starters"],
                    "panchina": h_lineup["bench"]
                },
                "away_squad": {
                    "modulo": a_lineup["formation"],
                    "titolari": a_lineup["starters"],
                    "panchina": a_lineup["bench"]
                }
            }

            modified = True
            stats["injected"] += 1

        if modified:
            h2h_col.update_one(
                {"_id": doc_id},
                {"$set": {"matches": matches, "last_formazioni_serie_c_update": datetime.now()}}
            )

    print(f"\n{'='*70}")
    print(f"INJECTION COMPLETATA")
    print(f"  Match totali: {stats['total_matches']}")
    print(f"  ✅ Iniettati: {stats['injected']}")
    print(f"  ⏭️ Skip (home non trovata): {stats['skipped_home']}")
    print(f"  ⏭️ Skip (away non trovata): {stats['skipped_away']}")
    print(f"{'='*70}\n")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--test" in args:
        print("🧪 MODALITÀ TEST — solo 2 squadre")
        scrape_all_teams(test_mode=True)
    elif "--scrape" in args:
        scrape_all_teams()
    elif "--inject" in args:
        inject_formations()
    else:
        # Default: scrape + inject
        scrape_all_teams()
        inject_formations()
