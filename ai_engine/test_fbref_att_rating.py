"""
TEST RATING ATTACCANTI - FBRef (Serie B)

Scarica statistiche di UN attaccante da FBRef (Serie B, comp 18),
estrae 8 metriche da 4 pagine diverse e calcola il rating puro con i tuoi pesi.

Statistiche usate:
1. Gls/90 (gol per 90)          - peso 23%
2. G+A/90 (gol + assist per 90) - peso 22%
3. SoT/90 (tiri in porta per 90)- peso 12%
4. G/Sh (gol per tiro)          - peso 12%
5. Succ/90 (affronti riusciti)  - peso 8%
6. Fld/90 (falli subiti)        - peso 8%
7. KP/90 (passaggi chiave)      - peso 8%
8. npxG+xAG/90                  - peso 7%

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

STANDARD_URL   = "https://fbref.com/en/comps/18/stats/Serie-B-Stats"
SHOOTING_URL   = "https://fbref.com/en/comps/18/shooting/Serie-B-Stats"
POSSESSION_URL = "https://fbref.com/en/comps/18/possession/Serie-B-Stats"
PASSING_URL    = "https://fbref.com/en/comps/18/passing/Serie-B-Stats"
MISC_URL       = "https://fbref.com/en/comps/18/misc/Serie-B-Stats"


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


def compute_att_rating(
    gls_per90: float | None,
    ga_per90: float | None,
    sot_per90: float | None,
    g_per_shot: float | None,
    succ_per90: float | None,
    fld_per90: float | None,
    kp_per90: float | None,
    npxg_xag_per90: float | None,
) -> dict:
    """
    Calcola il rating attaccante con gli 8 fattori e i pesi personalizzati.

    Pesi:
    - Gls/90:        23%
    - G+A/90:        22%
    - SoT/90:        12%
    - G/Sh:          12%
    - Succ/90:        8%
    - Fld/90:         8%
    - KP/90:          8%
    - npxG+xAG/90:    7%

    Scala finale: 4-10
    """

    # Range plausibili per attaccanti
    gls_norm   = normalize_0_1(gls_per90,       min_val=0.0,  max_val=1.0)
    ga_norm    = normalize_0_1(ga_per90,        min_val=0.0,  max_val=1.2)
    sot_norm   = normalize_0_1(sot_per90,       min_val=0.0,  max_val=2.5)
    gsh_norm   = normalize_0_1(g_per_shot,      min_val=0.0,  max_val=0.30)
    succ_norm  = normalize_0_1(succ_per90,      min_val=0.0,  max_val=2.0)
    fld_norm   = normalize_0_1(fld_per90,       min_val=0.0,  max_val=3.0)
    kp_norm    = normalize_0_1(kp_per90,        min_val=0.0,  max_val=2.0)
    npxg_norm  = normalize_0_1(npxg_xag_per90,  min_val=0.0,  max_val=1.0)

    q = (
        0.23 * gls_norm +
        0.22 * ga_norm +
        0.12 * sot_norm +
        0.12 * gsh_norm +
        0.08 * succ_norm +
        0.08 * fld_norm +
        0.08 * kp_norm +
        0.07 * npxg_norm
    )

    rating_puro = 4.0 + 6.0 * q

    return {
        "gls_norm": gls_norm,
        "ga_norm": ga_norm,
        "sot_norm": sot_norm,
        "gsh_norm": gsh_norm,
        "succ_norm": succ_norm,
        "fld_norm": fld_norm,
        "kp_norm": kp_norm,
        "npxg_norm": npxg_norm,
        "q": q,
        "rating_puro": rating_puro,
    }


# ============================================================================
# SCRAPING DELLE 4 TABELLE PER GLI ATTACCANTI
# ============================================================================

def scrape_standard_atts(scraper) -> Dict[tuple, Dict[str, Any]]:
    """
    STANDARD Serie B:
      key = (player_name, team_name)
      value = { player_name, team_name, pos_raw, role, minutes_90s,
                gls_per90, ga_per90, npxg_xag_per90 }
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

    atts: Dict[tuple, Dict[str, Any]] = {}

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
        if role != "ATT":
            continue

        cell_min = r.find("td", {"data-stat": "minutes_90s"})
        minutes_90s = parse_float_safe(cell_min.get_text(strip=True)) if cell_min else None

        cell_gls  = r.find("td", {"data-stat": "goals_per90"})
        cell_ga   = r.find("td", {"data-stat": "goals_assists_per90"})
        cell_npxg = r.find("td", {"data-stat": "npxg_xg_assist_per90"})

        gls_per90       = parse_float_safe(cell_gls.get_text(strip=True)) if cell_gls else None
        ga_per90        = parse_float_safe(cell_ga.get_text(strip=True)) if cell_ga else None
        npxg_xag_per90  = parse_float_safe(cell_npxg.get_text(strip=True)) if cell_npxg else None

        key = (player_name, team_name)
        atts[key] = {
            "player_name": player_name,
            "team_name": team_name,
            "pos_raw": pos_raw,
            "role": role,
            "minutes_90s": minutes_90s,
            "gls_per90": gls_per90,
            "ga_per90": ga_per90,
            "npxg_xag_per90": npxg_xag_per90,
        }

    print(f"   Attaccanti STANDARD trovati: {len(atts)}")
    return atts


def scrape_shooting(scraper, atts: Dict[tuple, Dict[str, Any]]) -> None:
    """
    Aggiunge SoT/90 e G/Sh agli attaccanti in atts.
    """
    print(f"\n➡️  Scarico SHOOTING: {SHOOTING_URL}")
    resp = scraper.get(SHOOTING_URL, timeout=40)
    print(f"   Status SHOOTING: {resp.status_code}")
    if resp.status_code != 200:
        print("   ⚠️ SHOOTING non 200, salto.")
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_shooting")
    if not table:
        print("   ❌ Tabella stats_shooting non trovata")
        return

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    print(f"   Righe SHOOTING trovate: {len(rows)}")

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
        if key not in atts:
            continue

        cell_sot = r.find("td", {"data-stat": "shots_on_target_per90"})
        cell_gsh = r.find("td", {"data-stat": "goals_per_shot"})

        sot_per90  = parse_float_safe(cell_sot.get_text(strip=True)) if cell_sot else None
        g_per_shot = parse_float_safe(cell_gsh.get_text(strip=True)) if cell_gsh else None

        atts[key]["sot_per90"] = sot_per90
        atts[key]["g_per_shot"] = g_per_shot


def scrape_possession(scraper, atts: Dict[tuple, Dict[str, Any]]) -> None:
    """
    Aggiunge Succ/90 (affronti riusciti) agli attaccanti in atts.
    """
    print(f"\n➡️  Scarico POSSESSION: {POSSESSION_URL}")
    resp = scraper.get(POSSESSION_URL, timeout=40)
    print(f"   Status POSSESSION: {resp.status_code}")
    if resp.status_code != 200:
        print("   ⚠️ POSSESSION non 200, salto.")
        return

    table = extract_table_from_comments_or_dom(resp.text, r"stats_possession")
    if not table:
        print("   ❌ Tabella stats_possession non trovata")
        return

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    print(f"   Righe POSSESSION trovate: {len(rows)}")

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
        if key not in atts:
            continue

        minutes_90s = atts[key].get("minutes_90s")

        cell_succ = r.find("td", {"data-stat": "take_ons_won"})
        succ = parse_float_safe(cell_succ.get_text(strip=True)) if cell_succ else None

        if not minutes_90s or minutes_90s == 0 or succ is None:
            succ_per90 = None
        else:
            succ_per90 = succ / minutes_90s

        atts[key]["succ_per90"] = succ_per90


def scrape_passing(scraper, atts: Dict[tuple, Dict[str, Any]]) -> None:
    """
    Aggiunge KP/90 (passaggi chiave) agli attaccanti in atts.
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
        if key not in atts:
            continue

        minutes_90s = atts[key].get("minutes_90s")

        cell_kp = r.find("td", {"data-stat": "assisted_shots"})
        kp = parse_float_safe(cell_kp.get_text(strip=True)) if cell_kp else None

        if not minutes_90s or minutes_90s == 0 or kp is None:
            kp_per90 = None
        else:
            kp_per90 = kp / minutes_90s

        atts[key]["kp_per90"] = kp_per90


def scrape_misc(scraper, atts: Dict[tuple, Dict[str, Any]]) -> None:
    """
    Aggiunge Fld/90 (falli subiti) agli attaccanti in atts.
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
        if key not in atts:
            continue

        minutes_90s = atts[key].get("minutes_90s")

        cell_fld = r.find("td", {"data-stat": "fouled"})
        fld = parse_float_safe(cell_fld.get_text(strip=True)) if cell_fld else None

        if not minutes_90s or minutes_90s == 0 or fld is None:
            fld_per90 = None
        else:
            fld_per90 = fld / minutes_90s

        atts[key]["fld_per90"] = fld_per90


# ============================================================================
# MAIN DI TEST
# ============================================================================

def main():
    print("\n" + "=" * 80)
    print(f"🏆 TEST RATING ATTACCANTE - FBRef ({COMP_NAME})")
    print("=" * 80)

    scraper = create_scraper()

    # 1) STANDARD
    atts = scrape_standard_atts(scraper)
    if not atts:
        print("❌ Nessun attaccante trovato, stop.")
        return

    time.sleep(10)

    # 2) SHOOTING
    scrape_shooting(scraper, atts)

    time.sleep(10)

    # 3) POSSESSION
    scrape_possession(scraper, atts)

    time.sleep(10)

    # 4) PASSING
    scrape_passing(scraper, atts)

    time.sleep(10)

    # 5) MISC
    scrape_misc(scraper, atts)

    # Scegliamo il primo attaccante che ha tutte e 8 le metriche != None
    chosen = None
    for _, data in atts.items():
        if all(
            k in data and data[k] is not None
            for k in ["gls_per90", "ga_per90", "sot_per90", "g_per_shot",
                      "succ_per90", "fld_per90", "kp_per90", "npxg_xag_per90"]
        ):
            chosen = data
            break

    # Se non lo troviamo, prendiamo il primo comunque (per debug)
    if chosen is None:
        print("⚠️ Nessun attaccante con tutti gli 8 valori != None, scelgo il primo per debug.")
        chosen = next(iter(atts.values()))

    print("\n📋 Attaccante scelto:")
    print(f"   Nome: {chosen['player_name']}")
    print(f"   Squadra: {chosen['team_name']}")
    print(f"   Posizione raw: {chosen['pos_raw']}")
    print(f"   Ruolo riconosciuto: {chosen['role']}")
    print(f"   90s giocati: {chosen.get('minutes_90s')}")

    print("\n📊 Statistiche derivate:")
    print(f"   Gls/90:         {chosen.get('gls_per90')}")
    print(f"   G+A/90:         {chosen.get('ga_per90')}")
    print(f"   SoT/90:         {chosen.get('sot_per90')}")
    print(f"   G/Sh:           {chosen.get('g_per_shot')}")
    print(f"   Succ/90:        {chosen.get('succ_per90')}")
    print(f"   Fld/90:         {chosen.get('fld_per90')}")
    print(f"   KP/90:          {chosen.get('kp_per90')}")
    print(f"   npxG+xAG/90:    {chosen.get('npxg_xag_per90')}")

    # Calcolo rating
    result = compute_att_rating(
        gls_per90=chosen.get("gls_per90"),
        ga_per90=chosen.get("ga_per90"),
        sot_per90=chosen.get("sot_per90"),
        g_per_shot=chosen.get("g_per_shot"),
        succ_per90=chosen.get("succ_per90"),
        fld_per90=chosen.get("fld_per90"),
        kp_per90=chosen.get("kp_per90"),
        npxg_xag_per90=chosen.get("npxg_xag_per90"),
    )

    print("\n🔢 Valori normalizzati (0-1):")
    print(f"   Gls/90 norm:      {result['gls_norm']:.3f}")
    print(f"   G+A/90 norm:      {result['ga_norm']:.3f}")
    print(f"   SoT/90 norm:      {result['sot_norm']:.3f}")
    print(f"   G/Sh norm:        {result['gsh_norm']:.3f}")
    print(f"   Succ/90 norm:     {result['succ_norm']:.3f}")
    print(f"   Fld/90 norm:      {result['fld_norm']:.3f}")
    print(f"   KP/90 norm:       {result['kp_norm']:.3f}")
    print(f"   npxG+xAG/90 norm: {result['npxg_norm']:.3f}")

    print("\n📈 Calcolo indice q:")
    print(
        f"   q = 0.23*{result['gls_norm']:.3f} + "
        f"0.22*{result['ga_norm']:.3f} + "
        f"0.12*{result['sot_norm']:.3f} + "
        f"0.12*{result['gsh_norm']:.3f} + "
        f"0.08*{result['succ_norm']:.3f} + "
        f"0.08*{result['fld_norm']:.3f} + "
        f"0.08*{result['kp_norm']:.3f} + "
        f"0.07*{result['npxg_norm']:.3f}"
    )
    print(f"   q = {result['q']:.4f}")

    print("\n⭐ RATING ATTACCANTE (scala 4-10):")
    print(f"   rating_ATT_puro = {result['rating_puro']:.2f}")

    print("\n🔚 TEST RATING ATTACCANTE TERMINATO.\n")


if __name__ == "__main__":
    main()
