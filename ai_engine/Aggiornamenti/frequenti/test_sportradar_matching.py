"""
test_sportradar_matching.py — Diagnostica matching nomi Sportradar/SNAI vs DB

Per ogni lega:
1. Apre la pagina Sportradar standings (classifica) con Selenium
2. Estrae TUTTI i nomi squadra dalla tabella classifica
3. Confronta con DB teams collection (stessa logica di scrape_snai_odds)
4. Report: matchati, non matchati (con suggerimenti alias), squadre DB orfane
"""
import os
import sys
import time
import re
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from config import db
except ImportError:
    sys.path.append(r"C:\Progetti\simulatore-calcio-backend\ai_engine")
    from config import db

from scrape_snai_odds import normalize_name, get_team_aliases, init_driver
from selenium.webdriver.common.by import By

# ============================================================
#  MAPPA LEGHE: nome DB → season ID Sportradar
# ============================================================
LEAGUES = [
    {"db_name": "Serie A",                         "season_id": "130971"},
    {"db_name": "Serie B",                         "season_id": "130973"},
    {"db_name": "Serie C - Girone A",              "season_id": "133200"},
    {"db_name": "Serie C - Girone B",              "season_id": "133202"},
    {"db_name": "Serie C - Girone C",              "season_id": "133204"},
    {"db_name": "Premier League",                  "season_id": "130281"},
    {"db_name": "Championship",                    "season_id": "130921"},
    {"db_name": "La Liga",                         "season_id": "130805"},
    {"db_name": "LaLiga 2",                        "season_id": "132048"},
    {"db_name": "Bundesliga",                      "season_id": "130571"},
    {"db_name": "2. Bundesliga",                   "season_id": "130933"},
    {"db_name": "Ligue 1",                         "season_id": "131609"},
    {"db_name": "Ligue 2",                         "season_id": "131908"},
    {"db_name": "Eredivisie",                      "season_id": "130943"},
    {"db_name": "Liga Portugal",                   "season_id": "131867"},
    {"db_name": "Scottish Premiership",            "season_id": "131007"},
    {"db_name": "Allsvenskan",                     "season_id": "138196"},
    {"db_name": "Eliteserien",                     "season_id": "138092"},
    {"db_name": "Superligaen",                     "season_id": "130951"},
    {"db_name": "Jupiler Pro League",              "season_id": "131299"},
    {"db_name": "Süper Lig",                       "season_id": "131873"},
    {"db_name": "League of Ireland Premier Division", "season_id": "137994"},
    {"db_name": "Brasileirão Serie A",             "season_id": "137706"},
    {"db_name": "Primera División",                "season_id": "137974"},
    {"db_name": "Major League Soccer",             "season_id": "137218"},
    {"db_name": "J1 League",                       "season_id": "138182"},
]

BASE_URL = "https://s5.sir.sportradar.com/snai/it/1/season"


def preload_teams():
    """Carica tutti i team dal DB con alias pre-computati."""
    raw = list(db.teams.find({}, {"name": 1, "aliases": 1}))
    teams = []
    for t in raw:
        name = t.get("name", "")
        aliases = get_team_aliases(name, t)
        teams.append({"name": name, "aliases": aliases, "raw_aliases": t.get("aliases", [])})
    return teams


def try_match(sr_name, all_teams, league_teams=None):
    """
    Matching di un nome Sportradar contro i team DB.
    Se league_teams è fornito, cerca prima solo tra quelli (più preciso).
    Logica più stringente: evita falsi positivi con parole troppo corte.
    """
    sr_norm = normalize_name(sr_name)
    sr_low = sr_name.lower().strip()

    # Cerca preferibilmente tra i team della lega specifica
    search_pools = [league_teams, all_teams] if league_teams else [all_teams]

    for pool in search_pools:
        if not pool:
            continue
        for team in pool:
            for a in team["aliases"]:
                # Ignora alias troppo corti (< 4 char) per evitare falsi positivi
                # come "bra" in "brann", "az" in "gaziantep", "pau" in "sao paulo"
                min_len = 4
                if len(a) < min_len and len(sr_norm) < min_len:
                    # Entrambi corti → richiedi match esatto
                    if a == sr_norm or a == sr_low:
                        return team["name"]
                elif len(a) < min_len:
                    # Alias corto, nome SR lungo → alias deve essere parola intera in SR
                    if a in sr_norm.split() or a in sr_low.split():
                        return team["name"]
                elif len(sr_norm) < min_len:
                    # Nome SR corto, alias lungo → SR deve essere parola intera in alias
                    if sr_norm in a.split() or sr_low in a.split():
                        return team["name"]
                else:
                    # Entrambi >= 4 char → logica substring originale
                    if a in sr_norm or a in sr_low or sr_norm in a or sr_low in a:
                        return team["name"]
    return None


def suggest_closest(sr_name, all_teams, top_n=3):
    """Suggerisce i nomi DB più vicini (overlap parole normalizzate)."""
    sr_words = set(normalize_name(sr_name).split())
    if not sr_words:
        return []

    scores = []
    seen = set()
    for team in all_teams:
        db_words = set(normalize_name(team["name"]).split())
        overlap = len(sr_words & db_words)
        if overlap > 0 and team["name"] not in seen:
            scores.append((team["name"], overlap))
            seen.add(team["name"])
        for alias in team.get("raw_aliases", []):
            alias_words = set(normalize_name(alias).split())
            ov = len(sr_words & alias_words)
            if ov > overlap:
                key = f"{team['name']} (alias: {alias})"
                if key not in seen:
                    scores.append((key, ov))
                    seen.add(key)

    scores.sort(key=lambda x: -x[1])
    return [s[0] for s in scores[:top_n]]


def extract_standings_teams(driver, season_id):
    """
    Apre la pagina standings di Sportradar e estrae i nomi squadra.
    Tenta /standings/tables, poi /standings, poi la pagina base del season.
    """
    urls_to_try = [
        f"{BASE_URL}/{season_id}/standings/tables",
        f"{BASE_URL}/{season_id}/standings",
        f"{BASE_URL}/{season_id}",
    ]

    for url in urls_to_try:
        driver.get(url)
        time.sleep(3)

        # Cerca righe della classifica: tipicamente <tr> con link a /team/
        # Usa innerText del primo nodo testuale diretto per evitare duplicati
        teams = driver.execute_script("""
            var rows = document.querySelectorAll('table tbody tr, [class*="standings"] tr, [class*="table"] tr');
            var names = [];
            rows.forEach(function(row) {
                var teamLink = row.querySelector('a[href*="/team/"]');
                if (teamLink) {
                    // Prendi solo il testo diretto del link (non dei figli <span>)
                    var directText = '';
                    for (var i = 0; i < teamLink.childNodes.length; i++) {
                        var node = teamLink.childNodes[i];
                        if (node.nodeType === 3) { // TEXT_NODE
                            directText += node.textContent;
                        }
                    }
                    directText = directText.trim();
                    // Se il testo diretto è vuoto, prendi il primo figlio con testo
                    if (!directText) {
                        var spans = teamLink.querySelectorAll('span, div, p');
                        for (var j = 0; j < spans.length; j++) {
                            var st = spans[j].textContent.trim();
                            if (st && st.length > 1) { directText = st; break; }
                        }
                    }
                    // Ultimo fallback: textContent completo, poi taglia se raddoppiato
                    if (!directText) directText = teamLink.textContent.trim();
                    if (directText && directText.length > 1) names.push(directText);
                    return;
                }
                var cells = row.querySelectorAll('td');
                for (var i = 0; i < Math.min(cells.length, 3); i++) {
                    var t = cells[i].textContent.trim();
                    if (t && t.length > 2 && isNaN(t) && !/^\\d+$/.test(t)) {
                        names.push(t);
                        break;
                    }
                }
            });
            var unique = [];
            var seen = new Set();
            names.forEach(function(n) {
                if (!seen.has(n)) { seen.add(n); unique.push(n); }
            });
            return unique;
        """)

        # Post-processing: rimuovi nomi raddoppiati (es. "ATALANTAATALANTA" → skip se "ATALANTA" esiste)
        if teams:
            clean = []
            team_set = set(teams)
            for t in teams:
                # Se è la concatenazione di un nome con se stesso, salta
                half = len(t) // 2
                if len(t) > 2 and len(t) % 2 == 0 and t[:half] == t[half:]:
                    if t[:half] in team_set:
                        continue
                    else:
                        # Il nome "pulito" non era nella lista → usa la metà
                        clean.append(t[:half])
                        continue
                # Salta anche se è un nome lungo che contiene spazio + duplicato parziale
                # es. "Dallas \nDallas" (newline-separated)
                parts = t.split('\n')
                if len(parts) == 2 and parts[0].strip() == parts[1].strip():
                    clean.append(parts[0].strip())
                    continue
                clean.append(t)
            teams = clean

        if teams and len(teams) >= 4:
            return teams, url

    return [], urls_to_try[0]


def get_db_teams_for_league(league_name):
    """Estrae i nomi squadra dal DB h2h_by_round per una lega."""
    db_team_names = set()
    rounds = list(db.h2h_by_round.find({"league": league_name}))
    for rd in rounds:
        for m in rd.get("matches", []):
            home = m.get("home", "")
            away = m.get("away", "")
            if home:
                db_team_names.add(home)
            if away:
                db_team_names.add(away)
    return db_team_names


def main():
    print("=" * 100)
    print("DIAGNOSTICA MATCHING — SPORTRADAR (SNAI) vs DATABASE")
    print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 100)

    all_teams = preload_teams()
    print(f"\nTeam nel DB (teams collection): {len(all_teams)}")

    driver = init_driver()

    total_sr = 0
    total_matched = 0
    total_unmatched = 0
    all_unmatched = []
    all_db_orphans = []
    leagues_no_standings = []

    try:
        for league in LEAGUES:
            db_name = league["db_name"]
            season_id = league["season_id"]

            print(f"\n{'─' * 80}")
            print(f"  {db_name}  (season/{season_id})")
            print(f"{'─' * 80}")

            try:
                sr_teams, used_url = extract_standings_teams(driver, season_id)

                if not sr_teams:
                    print(f"  ⚠️  Classifica non trovata o vuota")
                    leagues_no_standings.append(db_name)
                    continue

                print(f"  Squadre Sportradar: {len(sr_teams)}")
                total_sr += len(sr_teams)

                # Pre-filtra team DB che appartengono a questa lega
                db_league_names = get_db_teams_for_league(db_name)
                league_pool = [t for t in all_teams if t["name"] in db_league_names]

                matched = []
                unmatched = []

                for sr_name in sorted(sr_teams):
                    db_match = try_match(sr_name, all_teams, league_pool)
                    if db_match:
                        matched.append((sr_name, db_match))
                    else:
                        suggestions = suggest_closest(sr_name, all_teams)
                        unmatched.append((sr_name, suggestions))

                total_matched += len(matched)
                total_unmatched += len(unmatched)

                # Matchati
                if matched:
                    print(f"\n  ✅ MATCHATI ({len(matched)}):")
                    for sr, db_n in matched:
                        if sr.lower().strip() == db_n.lower().strip():
                            print(f"     {sr}")
                        else:
                            print(f"     {sr:35s} → DB: {db_n}")

                # Non matchati
                if unmatched:
                    print(f"\n  ❌ NON MATCHATI ({len(unmatched)}):")
                    for sr, sugg in unmatched:
                        sugg_str = " | ".join(sugg) if sugg else "nessun suggerimento"
                        print(f"     SR: \"{sr}\"")
                        print(f"         Suggerimenti: {sugg_str}")
                        all_unmatched.append((db_name, sr, sugg))

                # Squadre DB senza corrispondenza Sportradar
                sr_matched_db = {db_n for _, db_n in matched}
                db_league_teams = db_league_names
                db_orphans = db_league_teams - sr_matched_db
                if db_orphans:
                    print(f"\n  ⚠️  SQUADRE DB SENZA CORRISPONDENZA SR ({len(db_orphans)}):")
                    for dn in sorted(db_orphans):
                        print(f"     DB: \"{dn}\"")
                        all_db_orphans.append((db_name, dn))

            except Exception as e:
                print(f"  ⚠️  Errore: {e}")
                continue

    finally:
        driver.quit()

    # ================================================================
    #  RIEPILOGO FINALE
    # ================================================================
    print("\n\n" + "=" * 100)
    print("RIEPILOGO GLOBALE")
    print("=" * 100)
    print(f"  Squadre Sportradar totali:  {total_sr}")
    print(f"  Matchate con DB:           {total_matched}")
    print(f"  NON matchate:              {total_unmatched}")

    if leagues_no_standings:
        print(f"\n  ⚠️  Leghe senza classifica: {', '.join(leagues_no_standings)}")

    if all_unmatched:
        print(f"\n{'─' * 80}")
        print(f"ALIAS DA AGGIUNGERE ({len(all_unmatched)}):")
        print(f"{'─' * 80}")
        for league, sr, sugg in all_unmatched:
            best = sugg[0] if sugg else "???"
            print(f"  [{league:30s}]  SR \"{sr}\"  →  probabile DB: \"{best}\"")
    else:
        print("\n✅ Tutti i nomi Sportradar hanno un match nel DB!")

    if all_db_orphans:
        print(f"\n{'─' * 80}")
        print(f"SQUADRE DB SENZA CORRISPONDENZA SPORTRADAR ({len(all_db_orphans)}):")
        print(f"{'─' * 80}")
        for league, dn in all_db_orphans:
            print(f"  [{league:30s}]  DB: \"{dn}\"")

    print()


if __name__ == "__main__":
    main()
