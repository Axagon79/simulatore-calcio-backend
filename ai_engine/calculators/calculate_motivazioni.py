import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

from league_objectives import LEAGUE_OBJECTIVES


# CONFIGURAZIONE DB

teams = db["teams"]


# Parametri generali
MIN_MATCHES_FOR_MOTIVATION = 6       # prima di questa giornata -> valore neutro
NEUTRAL_MOTIVATION = 10             # 5-15
MAX_MOTIVATION = 15

# Raggio di influenza in punti (obiettivo/pericolo) in funzione dei punti disponibili
D_MAX = 15.0   # quando ci sono ancora tanti punti disponibili
D_MIN = 3.0    # quando restano pochissimi punti da fare

# Pavimenti/limiti sulla motivazione grezza
MIN_RAW_WITH_PRESSURE = 0.40         # se c'è pressione (0-1) almeno ~2/10
MIN_RAW_NO_PRESSURE = 0.33           # se non c'è pressione, almeno ~1/10
# Niente tappo alto: lasciamo salire fino a 1.0

# Zone considerate "obiettivo positivo" e "pericolo"
EURO_ZONES = {
    "title",
    "ucl",
    "uel_uecl",
    "europa_playoffs",
    "promotion_direct",
    "promotion_playoff",
}
RELEGATION_ZONES = {
    "relegation",
    "relegation_playout",
    "relegation_fight",
}


def compute_dynamic_radius(points_available: float, total_matches: int) -> float:
    """
    Raggio d'influenza D che decresce con i punti ancora disponibili:
    all'inizio D ≈ D_MAX, a fine campionato D ≈ D_MIN.
    """
    if total_matches <= 0:
        return D_MIN

    max_points_available = 3.0 * total_matches  # all'inizio del campionato
    pa = max(0.0, min(points_available, max_points_available))
    progress_p = 1.0 - (pa / max_points_available)  # 0 all'inizio, 1 alla fine

    D = D_MAX - (D_MAX - D_MIN) * progress_p
    if D < D_MIN:
        D = D_MIN
    if D > D_MAX:
        D = D_MAX
    return D


def compute_pressure_chasing(
    delta_points: float,
    points_available: float,
    total_matches: int,
) -> float:
    """
    Pressione per chi INSEGUE un confine (obiettivo positivo o salvezza).
    d = punti che mancano per raggiungere la soglia.
    pressure = max(0, 1 - d / D), poi enfatizzata con esponente (per più differenze).
    """
    if delta_points is None:
        return 0.0

    D = compute_dynamic_radius(points_available, total_matches)
    d = max(0.0, float(delta_points))
    if D <= 0:
        return 0.0

    base = 1.0 - (d / D)
    if base < 0.0:
        base = 0.0
    if base > 1.0:
        base = 1.0

    # enfatizza le situazioni davvero vicine al confine
    pressure = base ** 1.3
    return pressure


def compute_pressure_ahead(
    advantage_points: float,
    points_available: float,
    total_matches: int,
) -> float:
    """
    Pressione per chi ha GIA' raggiunto l'obiettivo e ha un margine sopra il confine.
    Più il vantaggio cresce, più la pressione cala (rischio calo motivazionale).
    """
    if advantage_points is None:
        return 0.0

    D = compute_dynamic_radius(points_available, total_matches)
    a = max(0.0, float(advantage_points))
    if D <= 0:
        return 0.0

    base = 1.0 - (a / D)
    if base < 0.0:
        base = 0.0
    if base > 1.0:
        base = 1.0

    # qui non enfatizziamo troppo: chi ha grande vantaggio deve calare più in fretta
    pressure = base ** 1.1
    return pressure


def _match_team_to_classifica(team_doc, cls_by_name, cls_by_tm_id):
    """Matching squadra con classifica: transfermarkt_id > nome > aliases."""
    tm_id = team_doc.get("transfermarkt_id")
    if tm_id and tm_id in cls_by_tm_id:
        return cls_by_tm_id[tm_id]
    name = team_doc.get("name", "")
    if name in cls_by_name:
        return cls_by_name[name]
    for alias in team_doc.get("aliases", []):
        if isinstance(alias, str) and alias in cls_by_name:
            return cls_by_name[alias]
        elif isinstance(alias, dict):
            for v in alias.values():
                if isinstance(v, str) and v in cls_by_name:
                    return cls_by_name[v]
    return None


def main():
    print("🔥 Calcolo MOTIVAZIONE squadre (0-10) per tutti i campionati...")

    classifiche = db["classifiche"]

    all_teams = list(teams.find(
        {"league": {"$exists": True}},
        {"name": 1, "league": 1, "aliases": 1, "transfermarkt_id": 1, "stats": 1}
    ))

    leagues = {}
    for team in all_teams:
        league = team.get("league")
        if not league:
            continue
        leagues.setdefault(league, []).append(team)

    total_updated = 0

    for league, league_teams in leagues.items():
        if league not in LEAGUE_OBJECTIVES:
            continue

        conf = LEAGUE_OBJECTIVES[league]
        total_matches = conf.get("total_matches")
        zones = conf.get("zones", {})

        if not total_matches or total_matches <= 0:
            continue

        print(f"\n🏆 {league}")
        print(f"   Giornate totali previste: {total_matches}")

        cls_doc = classifiche.find_one({"league": league})
        if not cls_doc or not cls_doc.get("table"):
            print("   ⚠️ Nessuna classifica trovata, salto.")
            continue

        cls_by_name = {}
        cls_by_tm_id = {}
        for row in cls_doc["table"]:
            cls_by_name[row.get("team", "")] = row
            tm_id = row.get("transfermarkt_id")
            if tm_id:
                cls_by_tm_id[tm_id] = row

        # mappa posizione -> (punti, played, team)
        pos_map = {}
        for t in league_teams:
            cls_row = _match_team_to_classifica(t, cls_by_name, cls_by_tm_id)
            if not cls_row:
                continue
            pos = cls_row.get("rank")
            pts = cls_row.get("points")
            played = cls_row.get("played")
            if isinstance(pos, int) and isinstance(pts, (int, float)) and isinstance(
                played, int
            ):
                t["_cls"] = {"position": pos, "points": pts, "played": played}
                pos_map[pos] = (pts, played, t)

        if not pos_map:
            print("   ⚠️ Nessun dato classifica valido per questa lega, salto.")
            continue

        # ---------------- soglie Europa/promozione ----------------
        euro_positions = []
        for z_name, z_conf in zones.items():
            if z_name in EURO_ZONES:
                euro_positions.extend(
                    range(z_conf["min_pos"], z_conf["max_pos"] + 1)
                )
        euro_positions = sorted(set(euro_positions))

        euro_min_pos = None
        euro_max_pos = None
        if euro_positions:
            euro_min_pos = min(euro_positions)
            euro_max_pos = max(euro_positions)

        euro_threshold_points = None
        if euro_max_pos is not None and euro_max_pos in pos_map:
            euro_threshold_points = pos_map[euro_max_pos][0]

        # ---------------- soglie retrocessione / playout ----------------
        releg_positions = []
        for z_name, z_conf in zones.items():
            if z_name in RELEGATION_ZONES:
                releg_positions.extend(
                    range(z_conf["min_pos"], z_conf["max_pos"] + 1)
                )
        releg_positions = sorted(set(releg_positions))

        releg_playout_positions = []
        releg_direct_positions = []
        for pos in releg_positions:
            for z_name, z_conf in zones.items():
                if z_name == "relegation_playout":
                    if z_conf["min_pos"] <= pos <= z_conf["max_pos"]:
                        releg_playout_positions.append(pos)
                if z_name == "relegation":
                    if z_conf["min_pos"] <= pos <= z_conf["max_pos"]:
                        releg_direct_positions.append(pos)

        releg_playout_positions = sorted(set(releg_playout_positions))
        releg_direct_positions = sorted(set(releg_direct_positions))

        releg_playout_points = None
        if releg_playout_positions:
            rp_pos = min(releg_playout_positions)
            if rp_pos in pos_map:
                releg_playout_points = pos_map[rp_pos][0]

        releg_direct_points = None
        if releg_direct_positions:
            rd_pos = min(releg_direct_positions)
            if rd_pos in pos_map:
                releg_direct_points = pos_map[rd_pos][0]

        # ---------------- soglia titolo ----------------
        title_points = None
        if "title" in zones:
            title_pos = zones["title"]["min_pos"]
            if title_pos in pos_map:
                title_points = pos_map[title_pos][0]
        else:
            if 1 in pos_map:
                title_points = pos_map[1][0]

        # ---------------- calcolo per squadra ----------------
        for t in league_teams:
            cls = t.get("_cls")
            if not cls:
                continue
            pos = cls["position"]
            pts = cls["points"]
            played = cls["played"]

            name = t.get("name", "???")

            if not isinstance(pos, int) or not isinstance(
                pts, (int, float)
            ) or not isinstance(played, int):
                print(
                    f"   ⚠️ {name}: dati classifica incompleti, salto motivazione."
                )
                continue

            matches_left = max(0, total_matches - played)
            points_available = matches_left * 3.0

            if played < MIN_MATCHES_FOR_MOTIVATION:
                motivation = NEUTRAL_MOTIVATION
                pressure_euro = 0.0
                pressure_releg = 0.0
                pressure_title = 0.0
                progress = 0.0

            else:
                # progress non lineare (fase del campionato)
                progress_linear = min(
                    max(played / float(total_matches), 0.0), 1.0
                )
                progress = progress_linear ** 0.5

                # ---------- pressione obiettivo positivo (Europa / promozione) ----------
                pressure_euro = 0.0
                if (
                    euro_threshold_points is not None
                    and euro_min_pos is not None
                    and euro_max_pos is not None
                ):
                    if pos <= euro_max_pos:
                        # già dentro la zona Europa/playoff
                        advantage = pts - euro_threshold_points
                        pressure_euro = compute_pressure_ahead(
                            advantage, points_available, total_matches
                        )
                    else:
                        # fuori dalla zona Europa/playoff
                        delta_euro = abs(pts - euro_threshold_points)
                        pressure_euro = compute_pressure_chasing(
                            delta_euro, points_available, total_matches
                        )

                # --- boost specifico Serie C dentro i playoff (2–4, 5–8, 9–10) ---
                is_serie_c = "serie c" in league.lower()
                if (
                    is_serie_c
                    and euro_min_pos is not None
                    and euro_max_pos is not None
                    and euro_min_pos <= 2 <= euro_max_pos
                ):
                    # Applichiamo solo se siamo già in zona playoff
                    if 2 <= pos <= 4:
                        # Posizioni con ingresso tardivo e forti vantaggi nel tabellone
                        pressure_euro *= 1.20
                    elif 5 <= pos <= 8:
                        # Posizioni medio-alte playoff
                        pressure_euro *= 1.10
                    elif 9 <= pos <= 10:
                        # Ultimi posti playoff, pressione per non uscire
                        pressure_euro *= 1.05

                    # Clamp per sicurezza
                    if pressure_euro > 1.0:
                        pressure_euro = 1.0
                    if pressure_euro < 0.0:
                        pressure_euro = 0.0

                # ---------- pressione zona pericolo (playout + retrocessione) ----------
                pressure_releg_pl = 0.0
                if releg_playout_points is not None and releg_playout_positions:
                    first_pl_pos = min(releg_playout_positions)
                    if pos < first_pl_pos:
                        # sopra la zona playout
                        delta_pl = abs(pts - releg_playout_points)
                        pressure_releg_pl = compute_pressure_chasing(
                            delta_pl, points_available, total_matches
                        )
                    else:
                        # dentro la zona playout
                        delta_pl = abs(pts - releg_playout_points)
                        pressure_releg_pl = compute_pressure_chasing(
                            delta_pl, points_available, total_matches
                        )

                pressure_releg_dir = 0.0
                if releg_direct_points is not None and releg_direct_positions:
                    first_dir_pos = min(releg_direct_positions)
                    if pos < first_dir_pos:
                        # sopra la zona retrocessione diretta
                        delta_dir = abs(pts - releg_direct_points)
                        pressure_releg_dir = compute_pressure_chasing(
                            delta_dir, points_available, total_matches
                        )
                    else:
                        # dentro la zona retrocessione diretta
                        delta_dir = abs(pts - releg_direct_points)
                        pressure_releg_dir = compute_pressure_chasing(
                            delta_dir, points_available, total_matches
                        )

                pressure_releg = max(pressure_releg_pl, pressure_releg_dir)

                # ---------- pressione titolo ----------
                pressure_title = 0.0
                if title_points is not None:
                    if pos == 1:
                        # capolista: pressione dipende dal vantaggio sulla seconda
                        second_points = None
                        if 2 in pos_map:
                            second_points = pos_map[2][0]
                        if second_points is not None:
                            advantage = pts - second_points
                            pressure_title = compute_pressure_ahead(
                                advantage, points_available, total_matches
                            )
                    elif pos <= 4:
                        # inseguitrici: distanza dal primo
                        delta_title = abs(pts - title_points)
                        pressure_title = compute_pressure_chasing(
                            delta_title, points_available, total_matches
                        )

                # pressione finale
                pressure = max(pressure_euro, pressure_releg, pressure_title)

                # motivazione grezza
                if pressure > 0:
                    motivation_raw = pressure * progress
                    if motivation_raw < MIN_RAW_WITH_PRESSURE:
                        motivation_raw = MIN_RAW_WITH_PRESSURE
                else:
                    base = progress * 0.2
                    motivation_raw = max(MIN_RAW_NO_PRESSURE, base)

                # scala a 0-10
                motivation = motivation_raw * MAX_MOTIVATION
                if motivation < 5.0:
                    motivation = 5.0
                if motivation > MAX_MOTIVATION:
                    motivation = MAX_MOTIVATION
                motivation = round(motivation, 2)

            teams.update_one(
                {"_id": t["_id"]},
                {
                    "$set": {
                        "stats.motivation": motivation,
                        "stats.motivation_progress": round(progress, 3),
                        "stats.motivation_pressure_euro": round(
                            pressure_euro, 3
                        ),
                        "stats.motivation_pressure_releg": round(
                            pressure_releg, 3
                        ),
                        "stats.motivation_pressure_title": round(
                            pressure_title, 3
                        ),
                    }
                },
            )
            total_updated += 1

            print(
                f"   ✅ {name[:20]:<20} | pos={pos:2d} pts={int(pts):3d} "
                f"| Mot={motivation:4.2f} (prog={progress:.2f}, "
                f"PE={pressure_euro:.2f}, PR={pressure_releg:.2f}, PT={pressure_title:.2f})"
            )

    print(
        f"\n✅ Completato calcolo motivazione. Aggiornate {total_updated} squadre."
    )

# // aggiunto per: logica bulk - Funzioni di supporto per Engine Core

def calculate_single_motivation(team_data, pos_map, league_conf, league_name):
    """
    Riproduce la logica di calcolo per una singola squadra (usata dal Bulk).
    """
    total_matches = league_conf.get("total_matches")
    zones = league_conf.get("zones", {})

    cls = team_data.get("_cls", {})
    pos, pts, played = cls.get("position"), cls.get("points"), cls.get("played")
    
    if not all(isinstance(x, (int, float)) for x in [pos, pts, played]):
        return NEUTRAL_MOTIVATION

    if played < MIN_MATCHES_FOR_MOTIVATION:
        return NEUTRAL_MOTIVATION

    matches_left = max(0, total_matches - played)
    points_available = matches_left * 3.0
    progress = (min(max(played / float(total_matches), 0.0), 1.0)) ** 0.5

    # --- Ricostruzione soglie Europa ---
    euro_positions = sorted(set([p for z, c in zones.items() if z in EURO_ZONES for p in range(c["min_pos"], c["max_pos"] + 1)]))
    euro_max_pos = max(euro_positions) if euro_positions else None
    euro_threshold_points = pos_map[euro_max_pos][0] if euro_max_pos in pos_map else None

    pressure_euro = 0.0
    if euro_threshold_points is not None:
        if pos <= euro_max_pos:
            pressure_euro = compute_pressure_ahead(pts - euro_threshold_points, points_available, total_matches)
        else:
            pressure_euro = compute_pressure_chasing(abs(pts - euro_threshold_points), points_available, total_matches)

    # --- Ricostruzione soglie Retrocessione ---
    releg_pos = sorted(set([p for z, c in zones.items() if z in RELEGATION_ZONES for p in range(c["min_pos"], c["max_pos"] + 1)]))
    releg_pl_pts = pos_map[min(releg_pos)][0] if releg_pos and min(releg_pos) in pos_map else None
    pressure_releg = compute_pressure_chasing(abs(pts - releg_pl_pts), points_available, total_matches) if releg_pl_pts else 0.0

    # --- Titolo ---
    title_pts = pos_map[1][0] if 1 in pos_map else None
    pressure_title = 0.0
    if title_pts:
        if pos == 1:
            second_pts = pos_map[2][0] if 2 in pos_map else None
            pressure_title = compute_pressure_ahead(pts - second_pts, points_available, total_matches) if second_pts else 0.0
        elif pos <= 4:
            pressure_title = compute_pressure_chasing(abs(pts - title_pts), points_available, total_matches)

    pressure = max(pressure_euro, pressure_releg, pressure_title)
    motivation_raw = max(MIN_RAW_WITH_PRESSURE, pressure * progress) if pressure > 0 else max(MIN_RAW_NO_PRESSURE, progress * 0.2)
    
    return round(max(5.0, min(MAX_MOTIVATION, motivation_raw * MAX_MOTIVATION)), 2)

def get_motivation_live_bulk(team_name, league_name, bulk_cache):
    """
    Interfaccia per l'Engine Core per ottenere la motivazione dal bulk_cache.
    """
    if league_name not in LEAGUE_OBJECTIVES or not bulk_cache or "TEAMS" not in bulk_cache:
        return NEUTRAL_MOTIVATION

    league_teams = [t for t in bulk_cache["TEAMS"] if t.get("league") == league_name]
    # Carica classifica dalla collection classifiche
    cls_doc = db["classifiche"].find_one({"league": league_name})
    cls_by_name = {}
    cls_by_tm_id = {}
    if cls_doc and cls_doc.get("table"):
        for row in cls_doc["table"]:
            cls_by_name[row.get("team", "")] = row
            tm_id = row.get("transfermarkt_id")
            if tm_id:
                cls_by_tm_id[tm_id] = row

    # Arricchisci le squadre con dati classifica
    for t in league_teams:
        cls_row = _match_team_to_classifica(t, cls_by_name, cls_by_tm_id)
        if cls_row:
            t["_cls"] = {"position": cls_row.get("rank"), "points": cls_row.get("points"), "played": cls_row.get("played")}

    pos_map = {t["_cls"]["position"]: (t["_cls"]["points"], t["_cls"]["played"], t) for t in league_teams if t.get("_cls", {}).get("position")}
    
    # RICERCA TARGET TEAM (FIX ALIAS BLINDATO)
    target_team = None
    for t in league_teams:
        # 1. Nome Esatto
        if t.get("name") == team_name:
            target_team = t
            break
        
        # 2. Check Alias (Lista o Dizionario)
        aliases = t.get("aliases", [])
        found = False
        if isinstance(aliases, list):
            if team_name in aliases: found = True
        elif isinstance(aliases, dict):
            if team_name in aliases.values(): found = True
            
        if found:
            target_team = t
            break
            
    if not target_team: return NEUTRAL_MOTIVATION
    
    return calculate_single_motivation(target_team, pos_map, LEAGUE_OBJECTIVES[league_name], league_name)

if __name__ == "__main__":
    main()