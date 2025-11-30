"""
TEST RATING DIFENSORI - FBRef (Serie B)

Scarica statistiche di UN difensore da FBRef (Serie B, comp 18),
estrae 6 metriche da 3 pagine diverse e calcola il rating puro con i tuoi pesi.

Statistiche usate:
1. Contrasti (Def 3rd)/90   - peso 25%
2. Tkl+Int/90               - peso 29%
3. TklW/90                  - peso 15%
4. Aerials Won/90           - peso 16%
5. onGA/90 (gol subiti)     - peso 10% (MENO è MEGLIO)
6. Clr/90                   - peso 5%

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

DEFENSE_URL     = "https://fbref.com/en/comps/18/defense/Serie-B-Stats"
MISC_URL        = "https://fbref.com/en/comps/18/misc/Serie-B-Stats"
PLAYINGTIME_URL = "https://fbref.com/en/comps/18/playingtime/Serie-B-Stats"


# ============================================================================
# UTILS FBREF
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


def compute_def_rating(
    tkl_def3rd_per90: float | None,
    tkl_int_per90: float | None,
    tklw_per90: float | None,
    aerials_won_per90: float | None,
    on_ga_per90: float | None,
    clr_per90: float | None,
) -> dict:
    """
    Calcola il rating difensore con i 6 fattori e i pesi personalizzati.

    Pesi:
    - Contrasti Def 3rd/90:  25%
    - Tkl+Int/90:            29%
    - TklW/90:               15%
    - Aerials Won/90:        16%
    - onGA/90:               10% (MENO gol subiti = MEGLIO)
    - Clr/90:                 5%

    Scala finale: 4-10
    """

    # Range plausibili per difensori
    t3_norm  = normalize_0_1(tkl_def3rd_per90,  min_val=0.0, max_val=2.0)
    ti_norm  = normalize_0_1(tkl_int_per90,     min_val=0.0, max_val=5.0)
    tw_norm  = normalize_0_1(tklw_per90,        min_val=0.0, max_val=2.0)
    aw_norm  = normalize_0_1(aerials_won_per90, min_val=0.0, max_val=5.0)
    clr_norm = normalize_0_1(clr_per90,         min_val=0.0, max_val=6.0)

    # onGA: MENO gol subiti = MEGLIO → inverti
    # Range: 0.5 gol/90 (ottimo) → 2.5 gol/90 (pessimo)
    if on_ga_per90 is None:
        ga_norm = 0.5
    else:
        # Inverti: più alto onGA → più basso norm
        ga_norm = 1.0 - normalize_0_1(on_ga_per90, min_val=0.5, max_val=2.5)

    q = (
        0.25 * t3_norm +
        0.29 * ti_norm +
        0.15 * tw_norm +
        0.16 * aw_norm +
        0.10 * ga_norm +
        0.05 * clr_norm
    )

    rating_puro = 4.0 + 6.0 * q

    return {
        "t3_norm": t3_norm,
        "ti_norm": ti_norm,
        "tw_norm": tw_norm,
        "aw_norm": aw_norm,
        "ga_norm": ga_norm,
        "clr_norm": clr_norm,
        "q": q,
        "rating_puro": rating_puro,
    }


# ============================================================================
# SCRAPING DELLE 3 TABELLE PER I DIFENSORI
# ============================================================================

def scrape_defense_defs(scraper) -> Dict[tuple, Dict[str, Any]]:
    """
    DEFENSE Serie B:
      key = (player_name, team_name)
      value = { player_name, team_name, pos_raw, role, minutes_90s,
                tkl_def3rd_per90, tkl_int_per90, clr_per90 }
    """
    print(f"➡️  Scarico DEFENSE: {DEFENSE_URL}")
    resp = scraper.get(DEFENSE_URL, timeout=40)
    print(f"   Status DEFENSE: {resp.status_code}")
    if resp.status_code != 200:
        print("   ⚠️ DEFENSE non 200, stop.")
        return {}

    table = extract_table_from_comments_or_dom(resp.text, r"stats_defense")
    if not table:
        print("   ❌ Tabella stats_defense non trovata")
        return {}

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    print(f"   Righe DEFENSE trovate: {len(rows)}")

    defs: Dict[tuple, Dict[str, Any]] = {}

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
        if role != "DIF":
            continue

        cell_min = r.find("td", {"data-stat": "minutes_90s"})
        minutes_90s = parse_float_safe(cell_min.get_text(strip=True)) if cell_min else None

        cell_tkl_def3rd = r.find("td", {"data-stat": "tackles_def_3rd"})
        cell_tkl_int    = r.find("td", {"data-stat": "tackles_interceptions"})
        cell_clr        = r.find("td", {"data-stat": "clearances"})

        tkl_def3rd = parse_float_safe(cell_tkl_def3rd.get_text(strip=True)) if cell_tkl_def3rd else None
        tkl_int    = parse_float_safe(cell_tkl_int.get_text(strip=True)) if cell_tkl_int else None
        clr        = parse_float_safe(cell_clr.get_text(strip=True)) if cell_clr else None

        if not minutes_90s or minutes_90s == 0:
            tkl_def3rd_per90 = None
            tkl_int_per90    = None
            clr_per90        = None
        else:
            tkl_def3rd_per90 = tkl_def3rd / minutes_90s if tkl_def3rd is not None else None
            tkl_int_per90    = tkl_int / minutes_90s if tkl_int is not None else None
            clr_per90        = clr / minutes_90s if clr is not None else None

        key = (player_name, team_name)
        defs[key] = {
            "player_name": player_name,
            "team_name": team_name,
            "pos_raw": pos_raw,
            "role": role,
            "minutes_90s": minutes_90s,
            "tkl_def3rd_per90": tkl_def3rd_per90,
            "tkl_int_per90": tkl_int_per90,
            "clr_per90": clr_per90,
        }

    print(f"   Difensori DEFENSE trovati: {len(defs)}")
    return defs


def scrape_misc(scraper, defs: Dict[tuple, Dict[str, Any]]) -> None:
    """
    Aggiunge TklW/90 e Aerials Won/90 ai difensori in defs.
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
        if key not in defs:
            continue

        minutes_90s = defs[key].get("minutes_90s")

        cell_tklw = r.find("td", {"data-stat": "tackles_won"})
        cell_aer  = r.find("td", {"data-stat": "aerials_won"})

        tklw = parse_float_safe(cell_tklw.get_text(strip=True)) if cell_tklw else None
        aer  = parse_float_safe(cell_aer.get_text(strip=True)) if cell_aer else None

        if not minutes_90s or minutes_90s == 0:
            tklw_per90 = None
            aerials_won_per90 = None
        else:
            tklw_per90 = tklw / minutes_90s if tklw is not None else None
            aerials_won_per90 = aer / minutes_90s if aer is not None else None

        defs[key]["tklw_per90"] = tklw_per90
        defs[key]["aerials_won_per90"] = aerials_won_per90


def scrape_playingtime(scraper, defs: Dict[tuple, Dict[str, Any]]) -> None:
    """
    Aggiunge onGA/90 (gol subiti mentre in campo) ai difensori in defs.
    """
    print(f"\n➡️  Scarico PLAYINGTIME: {PLAYINGTIME_URL}")
    resp = scraper.get(PLAYINGTIME_URL, timeout=40)
    print(f"   Status PLAYINGTIME: {resp.status_code}")
    if resp.status_code != 200:
        print("   ⚠️ PLAYINGTIME non 200, salto.")
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_playing_time")
    if not table:
        print("   ❌ Tabella stats_playing_time non trovata")
        return

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    print(f"   Righe PLAYINGTIME trovate: {len(rows)}")

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
        if key not in defs:
            continue

        minutes_90s = defs[key].get("minutes_90s")

        cell_on_ga = r.find("td", {"data-stat": "on_goals_against"})
        on_ga = parse_float_safe(cell_on_ga.get_text(strip=True)) if cell_on_ga else None

        if not minutes_90s or minutes_90s == 0 or on_ga is None:
            on_ga_per90 = None
        else:
            on_ga_per90 = on_ga / minutes_90s

        defs[key]["on_ga_per90"] = on_ga_per90


# ============================================================================
# MAIN DI TEST
# ============================================================================

def main():
    print("\n" + "=" * 80)
    print(f"🏆 TEST RATING DIFENSORE - FBRef ({COMP_NAME})")
    print("=" * 80)

    scraper = create_scraper()

    # 1) DEFENSE
    defs = scrape_defense_defs(scraper)
    if not defs:
        print("❌ Nessun difensore trovato, stop.")
        return

    time.sleep(10)

    # 2) MISC
    scrape_misc(scraper, defs)

    time.sleep(10)

    # 3) PLAYINGTIME
    scrape_playingtime(scraper, defs)

    # Scegliamo il primo difensore che ha tutte e 6 le metriche != None
    chosen = None
    for _, data in defs.items():
        if all(
            k in data and data[k] is not None
            for k in ["tkl_def3rd_per90", "tkl_int_per90", "tklw_per90",
                      "aerials_won_per90", "on_ga_per90", "clr_per90"]
        ):
            chosen = data
            break

    # Se non lo troviamo, prendiamo il primo comunque (per debug)
    if chosen is None:
        print("⚠️ Nessun difensore con tutti i 6 valori != None, scelgo il primo per debug.")
        chosen = next(iter(defs.values()))

    print("\n📋 Difensore scelto:")
    print(f"   Nome: {chosen['player_name']}")
    print(f"   Squadra: {chosen['team_name']}")
    print(f"   Posizione raw: {chosen['pos_raw']}")
    print(f"   Ruolo riconosciuto: {chosen['role']}")
    print(f"   90s giocati: {chosen.get('minutes_90s')}")

    print("\n📊 Statistiche derivate:")
    print(f"   Contrasti Def 3rd/90:  {chosen.get('tkl_def3rd_per90')}")
    print(f"   Tkl+Int/90:            {chosen.get('tkl_int_per90')}")
    print(f"   TklW/90:               {chosen.get('tklw_per90')}")
    print(f"   Aerials Won/90:        {chosen.get('aerials_won_per90')}")
    print(f"   onGA/90 (gol subiti):  {chosen.get('on_ga_per90')}")
    print(f"   Clr/90:                {chosen.get('clr_per90')}")

    # Calcolo rating
    result = compute_def_rating(
        tkl_def3rd_per90=chosen.get("tkl_def3rd_per90"),
        tkl_int_per90=chosen.get("tkl_int_per90"),
        tklw_per90=chosen.get("tklw_per90"),
        aerials_won_per90=chosen.get("aerials_won_per90"),
        on_ga_per90=chosen.get("on_ga_per90"),
        clr_per90=chosen.get("clr_per90"),
    )

    print("\n🔢 Valori normalizzati (0-1):")
    print(f"   Tkl Def 3rd/90 norm:   {result['t3_norm']:.3f}")
    print(f"   Tkl+Int/90 norm:       {result['ti_norm']:.3f}")
    print(f"   TklW/90 norm:          {result['tw_norm']:.3f}")
    print(f"   Aerials Won/90 norm:   {result['aw_norm']:.3f}")
    print(f"   onGA/90 norm (inv):    {result['ga_norm']:.3f}")
    print(f"   Clr/90 norm:           {result['clr_norm']:.3f}")

    print("\n📈 Calcolo indice q:")
    print(
        f"   q = 0.25*{result['t3_norm']:.3f} + "
        f"0.29*{result['ti_norm']:.3f} + "
        f"0.15*{result['tw_norm']:.3f} + "
        f"0.16*{result['aw_norm']:.3f} + "
        f"0.10*{result['ga_norm']:.3f} + "
        f"0.05*{result['clr_norm']:.3f}"
    )
    print(f"   q = {result['q']:.4f}")

    print("\n⭐ RATING DIFENSORE (scala 4-10):")
    print(f"   rating_DEF_puro = {result['rating_puro']:.2f}")

    print("\n🔚 TEST RATING DIFENSORE TERMINATO.\n")


if __name__ == "__main__":
    main()
