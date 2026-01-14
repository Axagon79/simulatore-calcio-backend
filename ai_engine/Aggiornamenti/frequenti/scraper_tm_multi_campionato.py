import os
import sys
import os
import sys

# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db


"""
SCRAPER TRANSFERMARKT - PRESENZE & ASSENZE MULTI-CAMPIONATO (CLUSTER pup_pals_db)

Campionati gestiti (11):
- Serie A, Serie B, Serie C (Girone A/B/C)
- Premier League, La Liga, Eredivisie, Bundesliga, Ligue 1, Primeira Liga

Logica:
1) FASE 1 - CHECK SQUADRE MANCANTI
   - Confronta squadre Transfermarkt vs Mongo (cluster)
   - Identifica squadre mancanti per ogni league_code

2) FASE 2 - RECUPERO SQUADRE MANCANTI
   - Per le squadre mancanti fa scraping di "ausfallzeiten" e salva i dati

3) FASE 3 - AGGIORNAMENTO INTELLIGENTE
   - Legge da "Table" (classifica) Transfermarkt le PARTITE GIOCATE per squadra
   - Per ogni squadra confronta:
       matches_played (classifica) vs max_matches_recorded (Mongo)
   - Se max_matches_recorded < matches_played → aggiorna quella squadra
   - Se max_matches_recorded >= matches_played → salta l'aggiornamento

MongoDB (CLUSTER):
- URI: MONGO_URI (pup_pals-cluster)
- DB: pup_pals_db
- Collection: players_availability_tm
"""

import re
import sys
import time
import random
from datetime import datetime

import cloudscraper
from bs4 import BeautifulSoup

# ============================================================================
# CONFIGURAZIONE MONGO CLUSTER
# ============================================================================

MONGO_COLLECTION_NAME = "players_availability_tm"

# ============================================================================
# CONFIGURAZIONE CAMPIONATI
# ============================================================================

BASE_DOMAIN_IT = "https://www.transfermarkt.it"
BASE_DOMAIN_COM = "https://www.transfermarkt.com"
SEASON = "2025-2026"

COMPETITIONS = [
    # ITALIA
    {
        "name": "Serie A", "league_code": "ITA1",
        "startseite_url": "https://www.transfermarkt.it/serie-a/startseite/wettbewerb/IT1",
        "table_url": "https://www.transfermarkt.it/serie-a/tabelle/wettbewerb/IT1/saison_id/2025",
        "base_domain": BASE_DOMAIN_IT,
    },
    {
        "name": "Serie B", "league_code": "ITA2",
        "startseite_url": "https://www.transfermarkt.it/serie-b/startseite/wettbewerb/IT2",
        "table_url": "https://www.transfermarkt.it/serie-b/tabelle/wettbewerb/IT2/saison_id/2025",
        "base_domain": BASE_DOMAIN_IT,
    },
    {
        "name": "Serie C - Girone A", "league_code": "ITA3A",
        "startseite_url": "https://www.transfermarkt.it/serie-c-girone-a/startseite/wettbewerb/IT3A",
        "table_url": "https://www.transfermarkt.it/serie-c-girone-a/tabelle/wettbewerb/IT3A/saison_id/2025",
        "base_domain": BASE_DOMAIN_IT,
    },
    {
        "name": "Serie C - Girone B", "league_code": "ITA3B",
        "startseite_url": "https://www.transfermarkt.it/serie-c-girone-b/startseite/wettbewerb/IT3B",
        "table_url": "https://www.transfermarkt.it/serie-c-girone-b/tabelle/wettbewerb/IT3B/saison_id/2025",
        "base_domain": BASE_DOMAIN_IT,
    },
    {
        "name": "Serie C - Girone C", "league_code": "ITA3C",
        "startseite_url": "https://www.transfermarkt.it/serie-c-girone-c/startseite/wettbewerb/IT3C",
        "table_url": "https://www.transfermarkt.it/serie-c-girone-c/tabelle/wettbewerb/IT3C/saison_id/2025",
        "base_domain": BASE_DOMAIN_IT,
    },
    
    # EUROPA TOP
    {
        "name": "Premier League", "league_code": "GB1",
        "startseite_url": "https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1",
        "table_url": "https://www.transfermarkt.com/premier-league/tabelle/wettbewerb/GB1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "La Liga", "league_code": "ES1",
        "startseite_url": "https://www.transfermarkt.com/la-liga/startseite/wettbewerb/ES1",
        "table_url": "https://www.transfermarkt.com/la-liga/tabelle/wettbewerb/ES1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Bundesliga", "league_code": "DE1",
        "startseite_url": "https://www.transfermarkt.com/bundesliga/startseite/wettbewerb/L1",
        "table_url": "https://www.transfermarkt.com/bundesliga/tabelle/wettbewerb/L1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Ligue 1", "league_code": "FR1",
        "startseite_url": "https://www.transfermarkt.com/ligue-1/startseite/wettbewerb/FR1",
        "table_url": "https://www.transfermarkt.com/ligue-1/tabelle/wettbewerb/FR1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Eredivisie", "league_code": "NL1",
        "startseite_url": "https://www.transfermarkt.com/eredivisie/startseite/wettbewerb/NL1",
        "table_url": "https://www.transfermarkt.com/eredivisie/tabelle/wettbewerb/NL1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Primeira Liga", "league_code": "PT1",
        "startseite_url": "https://www.transfermarkt.com/liga-nos/startseite/wettbewerb/PO1",
        "table_url": "https://www.transfermarkt.com/liga-nos/tabelle/wettbewerb/PO1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    
    # 🆕 EUROPA SERIE B
    {
        "name": "Championship", "league_code": "GB2",
        "startseite_url": "https://www.transfermarkt.com/championship/startseite/wettbewerb/GB2",
        "table_url": "https://www.transfermarkt.com/championship/tabelle/wettbewerb/GB2/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "LaLiga 2", "league_code": "ES2",
        "startseite_url": "https://www.transfermarkt.com/laliga2/startseite/wettbewerb/ES2",
        "table_url": "https://www.transfermarkt.com/laliga2/tabelle/wettbewerb/ES2/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "2. Bundesliga", "league_code": "DE2",
        "startseite_url": "https://www.transfermarkt.com/2-bundesliga/startseite/wettbewerb/L2",
        "table_url": "https://www.transfermarkt.com/2-bundesliga/tabelle/wettbewerb/L2/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Ligue 2", "league_code": "FR2",
        "startseite_url": "https://www.transfermarkt.com/ligue-2/startseite/wettbewerb/FR2",
        "table_url": "https://www.transfermarkt.com/ligue-2/tabelle/wettbewerb/FR2/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    
    # 🆕 EUROPA NORDICI + EXTRA
    {
        "name": "Scottish Premiership", "league_code": "SC1",
        "startseite_url": "https://www.transfermarkt.com/premiership/startseite/wettbewerb/SC1",
        "table_url": "https://www.transfermarkt.com/premiership/tabelle/wettbewerb/SC1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Allsvenskan", "league_code": "SE1",
        "startseite_url": "https://www.transfermarkt.com/allsvenskan/startseite/wettbewerb/SE1",
        "table_url": "https://www.transfermarkt.com/allsvenskan/tabelle/wettbewerb/SE1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Eliteserien", "league_code": "NO1",
        "startseite_url": "https://www.transfermarkt.com/eliteserien/startseite/wettbewerb/NO1",
        "table_url": "https://www.transfermarkt.com/eliteserien/tabelle/wettbewerb/NO1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Superligaen", "league_code": "DK1",
        "startseite_url": "https://www.transfermarkt.com/superligaen/startseite/wettbewerb/DK1",
        "table_url": "https://www.transfermarkt.com/superligaen/tabelle/wettbewerb/DK1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Jupiler Pro League", "league_code": "BE1",
        "startseite_url": "https://www.transfermarkt.com/jupiler-pro-league/startseite/wettbewerb/BE1",
        "table_url": "https://www.transfermarkt.com/jupiler-pro-league/tabelle/wettbewerb/BE1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Süper Lig", "league_code": "TR1",
        "startseite_url": "https://www.transfermarkt.com/super-lig/startseite/wettbewerb/TR1",
        "table_url": "https://www.transfermarkt.com/super-lig/tabelle/wettbewerb/TR1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "League of Ireland Premier Division", "league_code": "IRL1",
        "startseite_url": "https://www.transfermarkt.com/premier-division/startseite/wettbewerb/IRL1",
        "table_url": "https://www.transfermarkt.com/premier-division/tabelle/wettbewerb/IRL1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    
    # 🆕 AMERICHE
    {
        "name": "Brasileirão Serie A", "league_code": "BRA1",
        "startseite_url": "https://www.transfermarkt.com/campeonato-brasileiro-serie-a/startseite/wettbewerb/BRA1",
        "table_url": "https://www.transfermarkt.com/campeonato-brasileiro-serie-a/tabelle/wettbewerb/BRA1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Primera División", "league_code": "ARG1",
        "startseite_url": "https://www.transfermarkt.com/primera-division/startseite/wettbewerb/AR1N",
        "table_url": "https://www.transfermarkt.com/primera-division/tabelle/wettbewerb/AR1N/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    {
        "name": "Major League Soccer", "league_code": "USA1",
        "startseite_url": "https://www.transfermarkt.com/major-league-soccer/startseite/wettbewerb/MLS1",
        "table_url": "https://www.transfermarkt.com/major-league-soccer/tabelle/wettbewerb/MLS1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
    
    # 🆕 ASIA
    {
        "name": "J1 League", "league_code": "JAP1",
        "startseite_url": "https://www.transfermarkt.com/j1-league/startseite/wettbewerb/JAP1",
        "table_url": "https://www.transfermarkt.com/j1-league/tabelle/wettbewerb/JAP1/saison_id/2025",
        "base_domain": BASE_DOMAIN_COM,
    },
]

# ============================================================================
# FUNZIONI DI SUPPORTO
# ============================================================================

def create_scraper():
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True}
    )
    scraper.headers.update({
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    })
    return scraper


def get_mongo_collection():
    return db[MONGO_COLLECTION_NAME]


def get_teams_from_startseite(scraper, comp):
    """
    Ritorna dict team_id -> {name, slug, ausfall_url} per il campionato.
    """
    url = comp["startseite_url"]
    print(f"   🔎 Leggo startseite: {url}")
    try:
        resp = scraper.get(url, timeout=40)
    except Exception as e:
        print(f"   ❌ Errore richiesta: {e}")
        return {}

    if resp.status_code != 200:
        print(f"   ⚠️ Status {resp.status_code}")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="items")
    if not table:
        print("   ⚠️ Tabella 'items' non trovata")
        return {}

    teams = {}
    for row in table.find_all("tr"):
        cell = row.find("td", class_="hauptlink")
        if not cell:
            continue
        a = cell.find("a")
        if not a or not a.get("href"):
            continue

        name = a.get_text(strip=True)
        href = a["href"]
        m = re.match(r"^/([^/]+)/startseite/verein/(\d+)", href)
        if not m:
            continue
        slug = m.group(1)
        team_id = int(m.group(2))
        ausfall_url = f"{comp['base_domain']}/{slug}/ausfallzeiten/verein/{team_id}"
        teams[team_id] = {
            "team_name": name,
            "slug": slug,
            "team_id": team_id,
            "ausfall_url": ausfall_url,
        }

    print(f"   ✅ Squadre trovate su TM: {len(teams)}")
    return teams


def get_teams_from_mongo(coll, league_code):
    """
    Ritorna dict team_id -> {team_name, max_matches_recorded} per la lega.
    """
    pipeline = [
        {"$match": {"league_code": league_code}},
        {
            "$group": {
                "_id": "$team_id",
                "team_name": {"$first": "$team_name"},
                "max_matches_recorded": {"$max": "$max_matches_recorded"},
            }
        },
    ]
    res = coll.aggregate(pipeline)
    teams = {}
    for doc in res:
        tid = doc["_id"]
        teams[tid] = {
            "team_name": doc.get("team_name", ""),
            "max_matches_recorded": doc.get("max_matches_recorded", 0),
        }
    print(f"   ✅ Squadre presenti in Mongo: {len(teams)}")
    return teams


def get_matches_played_from_table(scraper, comp):
    """
    Legge la CLASSIFICA per il campionato e ritorna:
    dict team_id -> matches_played (partite giocate reali)
    """
    url = comp["table_url"]
    print(f"   📊 Leggo classifica (table): {url}")
    try:
        resp = scraper.get(url, timeout=40)
    except Exception as e:
        print(f"   ❌ Errore richiesta classifica: {e}")
        return {}

    if resp.status_code != 200:
        print(f"   ⚠️ Status classifica {resp.status_code}")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="items")
    if not table:
        print("   ⚠️ Tabella classifica non trovata")
        return {}

    matches_played = {}

    for row in table.find_all("tr"):
        # link squadra: contiene sempre /verein/ID
        club_link = row.find("a", href=re.compile(r"/verein/\d+"))
        if not club_link or not club_link.get("href"):
            continue

        href = club_link["href"]
        m = re.search(r"/verein/(\d+)", href)
        if not m:
            continue
        team_id = int(m.group(1))

        # primo td.zentriert della riga = partite giocate
        number_cells = row.find_all("td", class_="zentriert")
        if not number_cells:
            continue

        txt = number_cells[1].get_text(strip=True)
        if not txt.isdigit():
            continue

        matches = int(txt)
        matches_played[team_id] = matches

    print(f"   ✅ Partite giocate lette per {len(matches_played)} squadre")
    return matches_played


def classify_cell_status(td):
    """
    Classifica lo stato della cella (BENCH, SUB_IN, SQUAD, OUT_INJ, OUT_SUSP, NONE).
    Estrae anche match_id dal campo id="playerId/matchId/..."
    """
    cls = " ".join(td.get("class", []))
    span = td.find("span")
    title = span.get("title", "") if span else ""
    inner_cls = " ".join(span.get("class", [])) if span else ""
    cell_id = span.get("id", "") if span else ""

    status = "NONE"
    detail = title or ""

    if "ausfallzeiten_a" in cls or "ausfallzeiten_a" in inner_cls:
        if "qualifica" in title.lower() or "squalifica" in title.lower():
            status = "OUT_SUSP"
        else:
            status = "OUT_INJ"
    elif "ausfallzeiten_e" in cls:
        status = "SUB_IN"
    elif "ausfallzeiten_s" in cls:
        status = "BENCH"
    elif "ausfallzeiten_k" in cls:
        status = "SQUAD"
    elif "ausfallzeiten_" in cls:
        status = "NONE"
    else:
        status = "UNK"

    match_id = None
    if cell_id:
        parts = cell_id.split("/")
        if len(parts) >= 2 and parts[1].isdigit():
            match_id = int(parts[1])

    return match_id, status, detail


def parse_ausfallzeiten_for_team(scraper, comp, team, mongo_coll=None):
    """
    Estrae presenze/assenze da tabella ausfallzeiten di UNA squadra e salva in Mongo.
    Calcola anche max_matches_recorded come numero di match distinti trovati.
    """
    url = team["ausfall_url"]
    time.sleep(random.uniform(2, 4))

    try:
        resp = scraper.get(url, timeout=120)
    except Exception as e:
        print(f"      ❌ Timeout/errore ausfallzeiten: {e}")
        return 0, 0

    if resp.status_code != 200:
        print(f"      ⚠️ Status {resp.status_code} per ausfallzeiten")
        return 0, 0

    soup = BeautifulSoup(resp.text, "html.parser")

    table = None
    for tb in soup.find_all("table"):
        cls = " ".join(tb.get("class", []))
        if "ausfallzeiten" in cls:
            table = tb
            break

    if not table:
        print(f"      ⚠️ Tabella ausfallzeiten non trovata per {team['team_name']}")
        return 0, 0

    rows = table.find_all("tr")
    if not rows:
        print(f"      ⚠️ Nessuna riga giocatore per {team['team_name']}")
        return 0, 0

    now_ts = int(datetime.now().timestamp())
    num_saved_docs = 0
    all_match_ids = set()

    for tr in rows:
        name_cell = tr.find("td", class_="hauptlink")
        if not name_cell:
            continue

        a = name_cell.find("a")
        if not a:
            continue

        player_name = a.get_text(strip=True)
        prof_href = a.get("href", "")
        m = re.search(r"/spieler/(\d+)", prof_href)
        player_id = int(m.group(1)) if m else None

        pos_cell = tr.find("td", class_="ausfallzeiten_pos")
        position_short = pos_cell.get_text(strip=True) if pos_cell else None

        tds = tr.find_all("td")
        if len(tds) < 3:
            continue

        match_cells = tds[3:]

        events = []
        for td in match_cells:
            match_id, status, detail = classify_cell_status(td)
            if not match_id or status == "NONE":
                continue
            all_match_ids.add(match_id)
            events.append(
                {"match_id": match_id, "status": status, "detail": detail}
            )

        if not events:
            continue

        doc = {
            "season": SEASON,
            "league_code": comp["league_code"],
            "team_name": team["team_name"],
            "team_slug": team["slug"],
            "team_id": team["team_id"],
            "player_id": player_id,
            "player_name": player_name,
            "position_short": position_short,
            "events": events,
            "max_matches_recorded": len(all_match_ids),
            "source": "transfermarkt_ausfallzeiten",
            "updated_at": now_ts,
        }

        if mongo_coll is not None:
            mongo_coll.update_one(
                {
                    "season": SEASON,
                    "league_code": comp["league_code"],
                    "team_id": team["team_id"],
                    "player_id": player_id,
                },
                {"$set": doc},
                upsert=True,
            )
            num_saved_docs += 1

    return num_saved_docs, len(all_match_ids)

# ============================================================================
# MAIN
# ============================================================================

def main():
    scraper = create_scraper()
    mongo_coll = get_mongo_collection()

    total_docs = 0

    for comp in COMPETITIONS:
        print("\n" + "=" * 80)
        print(f"🏆 CAMPIONATO: {comp['name']} ({comp['league_code']})")
        print("=" * 80)

        # FASE 1: squadre mancanti
        tm_teams = get_teams_from_startseite(scraper, comp)
        time.sleep(random.uniform(1, 3))
        mongo_teams = get_teams_from_mongo(mongo_coll, comp["league_code"])

        tm_ids = set(tm_teams.keys())
        mongo_ids = set(mongo_teams.keys())
        missing_ids = tm_ids - mongo_ids

        if missing_ids:
            print("   ❗ Squadre MANCANTI in Mongo (da recuperare):")
            for tid in sorted(missing_ids):
                print(f"      - {tid}: {tm_teams[tid]['team_name']}")
        else:
            print("   ✅ Nessuna squadra mancante in Mongo.")

        # FASE 2: recupero squadre mancanti
        if missing_ids:
            print("\n   🔄 Recupero squadre mancanti...")
            for tid in sorted(missing_ids):
                team = tm_teams[tid]
                print(f"      ▶ Recupero {team['team_name']} (team_id={tid})")
                docs, matches = parse_ausfallzeiten_for_team(
                    scraper, comp, team, mongo_coll
                )
                print(
                    f"         → Documenti giocatore salvati: {docs}, "
                    f"match distinti: {matches}"
                )
                total_docs += docs
                time.sleep(random.uniform(2, 4))

        # FASE 3: aggiornamento intelligente
        print("\n   📊 Verifico avanzamento (partite giocate) per aggiornare solo chi è indietro...")
        matches_played = get_matches_played_from_table(scraper, comp)
        time.sleep(random.uniform(1, 3))

        for team_id, team_info in tm_teams.items():
            team_name = team_info["team_name"]
            mp = matches_played.get(team_id)

            if mp is None:
                continue

            mongo_team_info = mongo_teams.get(team_id)
            current_max = 0
            if mongo_team_info:
                val = mongo_team_info.get("max_matches_recorded")
                current_max = val if isinstance(val, int) else 0

            if current_max >= mp:
                continue


            print(
                f"   🔁 Aggiorno squadra {team_name} (team_id={team_id}) "
                f"perché max_matches_recorded={current_max} < matches_played={mp}"
            )
            docs, matches = parse_ausfallzeiten_for_team(
                scraper, comp, team_info, mongo_coll
            )
            print(
                f"      → Documenti giocatore salvati: {docs}, "
                f"match distinti: {matches}"
            )
            total_docs += docs
            time.sleep(random.uniform(2, 4))

        print(f"\n   🏁 Fine campionato {comp['name']}\n")

    print("\n" + "=" * 80)
    print("🎉 COMPLETATO!")
    print(f"📊 Totale documenti giocatore salvati/aggiornati: {total_docs}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()