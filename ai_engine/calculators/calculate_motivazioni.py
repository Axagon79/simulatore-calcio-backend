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


def main():
    print("🔥 Calcolo MOTIVAZIONE squadre (0-10) per tutti i campionati...")

    cursor = teams.find(
        {
            "stats.ranking_c.position": {"$exists": True},
            "stats.ranking_c.points": {"$exists": True},
            "stats.ranking_c.played": {"$exists": True},
            "league": {"$exists": True},
        }
    )

    leagues = {}
    for team in cursor:
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

        # mappa posizione -> (punti, played, team)
        pos_map = {}
        for t in league_teams:
            rc = t.get("stats", {}).get("ranking_c", {})
            pos = rc.get("position")
            pts = rc.get("points")
            played = rc.get("played")
            if isinstance(pos, int) and isinstance(pts, (int, float)) and isinstance(
                played, int
            ):
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
            stats = t.get("stats", {})
            rc = stats.get("ranking_c", {})
            pos = rc.get("position")
            pts = rc.get("points")
            played = rc.get("played")

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


if __name__ == "__main__":
    main()