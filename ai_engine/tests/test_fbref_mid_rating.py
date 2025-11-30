"""
TEST RATING CENTROCAMPISTI - FBRef (Serie B)

Scarica statistiche di UN centrocampista da FBRef (Serie B, comp 18),
estrae 6 metriche da 4 pagine diverse e calcola il rating puro con i tuoi pesi.

Statistiche usate:
1. G-PK/90 (gol non su rigore per 90)   - peso 13%
2. Ast/90 (assist per 90)              - peso 18%
3. Cmp% (percentuale passaggi)         - peso 29%
4. TklW/90 (tackle vinti per 90)       - peso 12%
5. Rec/90 (recuperi palla per 90)      - peso 18%
6. Aerials Won% (duelli aerei vinti %) - peso 10%

Scala finale: 4-10
"""

import re
import time
from typing import Dict, Any

import cloudscraper
from bs4 import BeautifulSoup, Comment


# ============================================================================
# CONFIGURAZIONE
# ============================================================================

COMP_ID = 18
COMP_NAME = "Serie B"

STANDARD_URL = "https://fbref.com/en/comps/18/stats/Serie-B-Stats"
PASSING_URL  = "https://fbref.com/en/comps/18/passing/Serie-B-Stats"
DEFENSE_URL  = "https://fbref.com/en/comps/18/defense/Serie-B-Stats"
MISC_URL     = "https://fbref.com/en/comps/18/misc/Serie-B-Stats"


# ============================================================================
# UTILS FBREF (STESSA LOGICA PORTIERI)
# ============================================================================

def create_scraper():
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "desktop": True,
        },
        delay=10,
    )
    # Headers più completi per evitare blocchi 403
    scraper.headers.update({
        "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.com/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return scraper


def extract_table_from_comments_or_dom(html: str, id_regex: str):
    """
    Cerca una tabella il cui id matcha id_regex, prima nei commenti HTML,
    poi nel DOM normale (stessa logica dello scraper portieri).
    """
    soup = BeautifulSoup(html, "html.parser")
    table = None

    # 1) Cerca nei commenti
    comments = soup.find_all(string=lambda t: isinstance(t, Comment))
    for c in comments:
        if "<table" not in c:
            continue
        if re.search(id_regex, c):
            inner = BeautifulSoup(c, "html.parser")
            cand = inner.find("table", id=re.compile(id_regex))
            if cand:
                table = cand
                break

    # 2) Fallback: DOM normale
    if not table:
        table = soup.find("table", id=re.compile(id_regex))

    return table


def parse_float_safe(val: str | None):
    if val is None:
        return None
    txt = val.strip().replace(",", "").replace("+", "").replace("%", "")
    if txt == "" or txt == "-":
        return None
    try:
        return float(txt)
    except Exception:
        return None


def classify_role(pos_raw: str) -> str:
    """
    Classifica il ruolo del giocatore secondo la tua mappa personalizzata.
    Rimuove gli spazi: 'MF, DF' -> 'MF,DF'.
    """
    if pos_raw is None:
        return "UNKNOWN"

    pos = pos_raw.replace(" ", "").strip()

    if "GK" in pos:
        return "GK"

    mapping = {
        "FW": "ATT",
        "FW,MF": "ATT",
        "MF,FW": "ATT",
        "FW,DF": "ATT",
        "DF,FW": "DIF",
        "MF": "MID",
        "MF,DF": "MID",
        "DF,MF": "DIF",
        "DF": "DIF",
    }

    return mapping.get(pos, "UNKNOWN")


def normalize_0_1(value: float | None, min_val: float, max_val: float) -> float:
    """
    Normalizza un valore su [0,1] con clamp.
    """
    if value is None:
        return 0.5
    if max_val == min_val:
        return 0.5
    x = (value - min_val) / (max_val - min_val)
    if x < 0:
        x = 0.0
    if x > 1:
        x = 1.0
    return x


def compute_mid_rating(
    g_pk_per90: float | None,
    ast_per90: float | None,
    cmp_pct: float | None,
    tklw_per90: float | None,
    rec_per90: float | None,
    aerials_won_pct: float | None,
) -> dict:
    """
    Calcola il rating centrocampista con i 6 fattori e i pesi personalizzati.

    Pesi:
    - G-PK/90:      13%
    - Ast/90:       18%
    - Cmp%:         29%
    - TklW/90:      12%
    - Rec/90:       18%
    - AerialsWon%:  10%

    Scala finale: 4-10
    """

    g_norm = normalize_0_1(g_pk_per90,       min_val=0.0,  max_val=0.50)
    a_norm = normalize_0_1(ast_per90,       min_val=0.0,  max_val=0.30)
    p_norm = normalize_0_1(cmp_pct,         min_val=70.0, max_val=95.0)
    t_norm = normalize_0_1(tklw_per90,      min_val=0.0,  max_val=2.50)
    r_norm = normalize_0_1(rec_per90,       min_val=0.0,  max_val=5.00)
    d_norm = normalize_0_1(aerials_won_pct, min_val=30.0, max_val=70.0)

    q = (
        0.13 * g_norm +
        0.18 * a_norm +
        0.29 * p_norm +
        0.12 * t_norm +
        0.18 * r_norm +
        0.10 * d_norm
    )

    rating_puro = 4.0 + 6.0 * q

    return {
        "g_norm": g_norm,
        "a_norm": a_norm,
        "p_norm": p_norm,
        "t_norm": t_norm,
        "r_norm": r_norm,
        "d_norm": d_norm,
        "q": q,
        "rating_puro": rating_puro,
    }


# ============================================================================
# SCRAPING DELLE 4 TABELLE PER I CENTROCAMPISTI
# ============================================================================

def scrape_standard_mids(scraper) -> Dict[tuple, Dict[str, Any]]:
    """
    STANDARD Serie B:
      key = (player_name, team_name)
      value = { player_name, team_name, pos_raw, role,
                minutes_90s, g_pk_per90, ast_per90 }
    """
    print(f"➡️  Scarico STANDARD: {STANDARD_URL}")
    resp = scraper.get(STANDARD_URL, timeout=40)
    print(f"   Status STANDARD: {resp.status_code}")
    if resp.status_code != 200:
        print("   ⚠️ STANDARD non 200, stop.")
        return {}

    table = extract_table_from_comments_or_dom(resp.text, r"stats_standard")
    if not table:
        print("   ❌ Tabella stats_standard non trovata")
        return {}

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    print(f"   Righe STANDARD trovate: {len(rows)}")

    mids: Dict[tuple, Dict[str, Any]] = {}

    for r in rows:
        if "class" in r.attrs and ("thead" in " ".join(r["class"]) or "spacer" in " ".join(r["class"])):
            continue

        player_cell = r.find(["th", "td"], {"data-stat": "player"})
        team_cell   = r.find("td", {"data-stat": "team"}) or r.find("td", {"data-stat": "squad"})
        pos_cell    = r.find("td", {"data-stat": "position"})

        if not player_cell or not team_cell or not pos_cell:
            continue

        player_name = player_cell.get_text(strip=True)
        team_name   = team_cell.get_text(strip=True)
        pos_raw     = pos_cell.get_text(strip=True)

        role = classify_role(pos_raw)
        if role != "MID":
            continue

        cell_min = r.find("td", {"data-stat": "minutes_90s"})
        minutes_90s = parse_float_safe(cell_min.get_text(strip=True)) if cell_min else None

        cell_goals     = r.find("td", {"data-stat": "goals"})
        cell_pens_made = r.find("td", {"data-stat": "pens_made"})
        cell_assists   = r.find("td", {"data-stat": "assists"})

        goals     = parse_float_safe(cell_goals.get_text(strip=True)) if cell_goals else None
        pens_made = parse_float_safe(cell_pens_made.get_text(strip=True)) if cell_pens_made else None
        assists   = parse_float_safe(cell_assists.get_text(strip=True)) if cell_assists else None

        if not minutes_90s or minutes_90s == 0:
            g_pk_per90 = None
            ast_per90  = None
        else:
            goals     = goals or 0.0
            pens_made = pens_made or 0.0
            assists   = assists or 0.0

            g_pk_total = goals - pens_made
            if g_pk_total < 0:
                g_pk_total = 0.0

            g_pk_per90 = g_pk_total / minutes_90s
            ast_per90  = assists / minutes_90s

        key = (player_name, team_name)
        mids[key] = {
            "player_name": player_name,
            "team_name": team_name,
            "pos_raw": pos_raw,
            "role": role,
            "minutes_90s": minutes_90s,
            "g_pk_per90": g_pk_per90,
            "ast_per90": ast_per90,
        }

    print(f"   Centrocampisti STANDARD trovati: {len(mids)}")
    return mids


def scrape_passing(scraper, mids: Dict[tuple, Dict[str, Any]]) -> None:
    """
    Aggiunge Cmp% (passes_pct) ai centrocampisti in mids.
    """
    print(f"\n➡️  Scarico PASSING: {PASSING_URL}")
    resp = scraper.get(PASSING_URL, timeout=40)
    print(f"   Status PASSING: {resp.status_code}")
    if resp.status_code != 200:
        print("   ⚠️ PASSING non 200, salto.")
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_passing")
    if not table:
        print("   ❌ Tabella stats_passing non trovata")
        return

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    print(f"   Righe PASSING trovate: {len(rows)}")

    for r in rows:
        if "class" in r.attrs and ("thead" in " ".join(r["class"]) or "spacer" in " ".join(r["class"])):
            continue

        player_cell = r.find(["th", "td"], {"data-stat": "player"})
        team_cell   = r.find("td", {"data-stat": "team"}) or r.find("td", {"data-stat": "squad"})
        if not player_cell or not team_cell:
            continue

        player_name = player_cell.get_text(strip=True)
        team_name   = team_cell.get_text(strip=True)
        key = (player_name, team_name)
        if key not in mids:
            continue

        cell_cmp = r.find("td", {"data-stat": "passes_pct"})
        cmp_pct = parse_float_safe(cell_cmp.get_text(strip=True)) if cell_cmp else None
        mids[key]["cmp_pct"] = cmp_pct


def scrape_defense(scraper, mids: Dict[tuple, Dict[str, Any]]) -> None:
    """
    Aggiunge TklW/90 ai centrocampisti in mids usando DEFENSE.
    """
    print(f"\n➡️  Scarico DEFENSE: {DEFENSE_URL}")
    resp = scraper.get(DEFENSE_URL, timeout=40)
    print(f"   Status DEFENSE: {resp.status_code}")
    if resp.status_code != 200:
        print("   ⚠️ DEFENSE non 200, salto.")
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_defense")
    if not table:
        print("   ❌ Tabella stats_defense non trovata")
        return

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    print(f"   Righe DEFENSE trovate: {len(rows)}")

    for r in rows:
        if "class" in r.attrs and ("thead" in " ".join(r["class"]) or "spacer" in " ".join(r["class"])):
            continue

        player_cell = r.find(["th", "td"], {"data-stat": "player"})
        team_cell   = r.find("td", {"data-stat": "team"}) or r.find("td", {"data-stat": "squad"})
        if not player_cell or not team_cell:
            continue

        player_name = player_cell.get_text(strip=True)
        team_name   = team_cell.get_text(strip=True)
        key = (player_name, team_name)
        if key not in mids:
            continue

        minutes_90s = mids[key].get("minutes_90s")

        cell_tkl = r.find("td", {"data-stat": "tackles_won"})
        tackles_won = parse_float_safe(cell_tkl.get_text(strip=True)) if cell_tkl else None

        if not minutes_90s or minutes_90s == 0 or tackles_won is None:
            tklw_per90 = None
        else:
            tklw_per90 = tackles_won / minutes_90s

        mids[key]["tklw_per90"] = tklw_per90


def scrape_misc(scraper, mids: Dict[tuple, Dict[str, Any]]) -> None:
    """
    Aggiunge Rec/90 (ball_recoveries) e Aerials Won% (aerials_won_pct)
    ai centrocampisti in mids usando MISC.
    """
    print(f"\n➡️  Scarico MISC: {MISC_URL}")
    resp = scraper.get(MISC_URL, timeout=40)
    print(f"   Status MISC: {resp.status_code}")
    if resp.status_code != 200:
        print("   ⚠️ MISC non 200, salto.")
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_misc")
    if not table:
        print("   ❌ Tabella stats_misc non trovata")
        return

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    print(f"   Righe MISC trovate: {len(rows)}")

    for r in rows:
        if "class" in r.attrs and ("thead" in " ".join(r["class"]) or "spacer" in " ".join(r["class"])):
            continue

        player_cell = r.find(["th", "td"], {"data-stat": "player"})
        team_cell   = r.find("td", {"data-stat": "team"}) or r.find("td", {"data-stat": "squad"})
        if not player_cell or not team_cell:
            continue

        player_name = player_cell.get_text(strip=True)
        team_name   = team_cell.get_text(strip=True)
        key = (player_name, team_name)
        if key not in mids:
            continue

        minutes_90s = mids[key].get("minutes_90s")

        cell_rec = r.find("td", {"data-stat": "ball_recoveries"})
        recov = parse_float_safe(cell_rec.get_text(strip=True)) if cell_rec else None

        cell_aer = r.find("td", {"data-stat": "aerials_won_pct"})
        aerials_pct = parse_float_safe(cell_aer.get_text(strip=True)) if cell_aer else None

        if not minutes_90s or minutes_90s == 0 or recov is None:
            rec_per90 = None
        else:
            rec_per90 = recov / minutes_90s

        mids[key]["rec_per90"] = rec_per90
        mids[key]["aerials_won_pct"] = aerials_pct


# ============================================================================
# MAIN DI TEST
# ============================================================================

def main():
    print("\n" + "=" * 80)
    print(f"🏆 TEST RATING CENTROCAMPISTA - FBRef ({COMP_NAME})")
    print("=" * 80)

    scraper = create_scraper()

    # 1) STANDARD
    mids = scrape_standard_mids(scraper)
    if not mids:
        print("❌ Nessun centrocampista trovato, stop.")
        return

    time.sleep(10)

    # 2) PASSING
    scrape_passing(scraper, mids)

    time.sleep(10)

    # 3) DEFENSE
    scrape_defense(scraper, mids)

    time.sleep(10)

    # 4) MISC
    scrape_misc(scraper, mids)

    # Proviamo prima a scegliere un centrocampista che ha TUTTE e 6 le metriche non None
    chosen = None
    for _, data in mids.items():
        if all(
            k in data and data[k] is not None
            for k in ["g_pk_per90", "ast_per90", "cmp_pct",
                      "tklw_per90", "rec_per90", "aerials_won_pct"]
        ):
            chosen = data
            break

    # Se non lo troviamo, prendiamo comunque il primo (per debug)
    if chosen is None:
        print("⚠️ Nessun centrocampista con tutti i 6 valori != None, scelgo il primo per debug.")
        chosen = next(iter(mids.values()))

    print("\n📋 Centrocampista scelto:")
    print(f"   Nome: {chosen['player_name']}")
    print(f"   Squadra: {chosen['team_name']}")
    print(f"   Posizione raw: {chosen['pos_raw']}")
    print(f"   Ruolo riconosciuto: {chosen['role']}")
    print(f"   90s giocati: {chosen.get('minutes_90s')}")

    print("\n📊 Statistiche derivate:")
    print(f"   G-PK/90:       {chosen.get('g_pk_per90')}")
    print(f"   Ast/90:        {chosen.get('ast_per90')}")
    print(f"   Cmp%:          {chosen.get('cmp_pct')}")
    print(f"   TklW/90:       {chosen.get('tklw_per90')}")
    print(f"   Rec/90:        {chosen.get('rec_per90')}")
    print(f"   Aerials Won%:  {chosen.get('aerials_won_pct')}")

    # Calcolo rating
    result = compute_mid_rating(
        g_pk_per90=chosen.get("g_pk_per90"),
        ast_per90=chosen.get("ast_per90"),
        cmp_pct=chosen.get("cmp_pct"),
        tklw_per90=chosen.get("tklw_per90"),
        rec_per90=chosen.get("rec_per90"),
        aerials_won_pct=chosen.get("aerials_won_pct"),
    )

    print("\n🔢 Valori normalizzati (0-1):")
    print(f"   G-PK/90 norm:      {result['g_norm']:.3f}")
    print(f"   Ast/90 norm:       {result['a_norm']:.3f}")
    print(f"   Cmp% norm:         {result['p_norm']:.3f}")
    print(f"   TklW/90 norm:      {result['t_norm']:.3f}")
    print(f"   Rec/90 norm:       {result['r_norm']:.3f}")
    print(f"   Aerials Won% norm: {result['d_norm']:.3f}")

    print("\n📈 Calcolo indice q:")
    print(
        f"   q = 0.13*{result['g_norm']:.3f} + "
        f"0.18*{result['a_norm']:.3f} + "
        f"0.29*{result['p_norm']:.3f} + "
        f"0.12*{result['t_norm']:.3f} + "
        f"0.18*{result['r_norm']:.3f} + "
        f"0.10*{result['d_norm']:.3f}"
    )
    print(f"   q = {result['q']:.4f}")

    print("\n⭐ RATING CENTROCAMPISTA (scala 4-10):")
    print(f"   rating_MID_puro = {result['rating_puro']:.2f}")

    print("\n🔚 TEST RATING CENTROCAMPISTA TERMINATO.\n")


if __name__ == "__main__":
    main()
