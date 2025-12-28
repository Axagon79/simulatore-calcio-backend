# league_objectives.py

LEAGUE_OBJECTIVES = {
    # =======================
    # ITALIA
    # =======================

    "Serie A": {
        "total_matches": 38,
        "zones": {
            "title":              {"min_pos": 1,  "max_pos": 1},   # Campione
            "ucl":                {"min_pos": 1,  "max_pos": 4},   # Champions League
            "uel_uecl":           {"min_pos": 5,  "max_pos": 7},   # Europa + Conference (approssimato)
            "mid_table":          {"min_pos": 8,  "max_pos": 14},
            "relegation_fight":   {"min_pos": 15, "max_pos": 17},
            "relegation":         {"min_pos": 18, "max_pos": 20},
        },
    },

    "Serie B": {
        "total_matches": 38,
        "zones": {
            "promotion_direct":   {"min_pos": 1,  "max_pos": 2},   # Promozione diretta A
            "promotion_playoff":  {"min_pos": 3,  "max_pos": 8},   # Playoff promozione
            "mid_table":          {"min_pos": 9,  "max_pos": 15},
            "relegation_playout": {"min_pos": 16, "max_pos": 17},  # Playout salvezza
            "relegation":         {"min_pos": 18, "max_pos": 20},
        },
    },

    "Serie C - Girone A": {
        "total_matches": 38,
        "zones": {
            "promotion_direct":   {"min_pos": 1,  "max_pos": 1},   # Promozione diretta B
            "promotion_playoff":  {"min_pos": 2,  "max_pos": 10},  # Playoff promozione
            "mid_table":          {"min_pos": 11, "max_pos": 15},
            "relegation_playout": {"min_pos": 16, "max_pos": 18},
            "relegation":         {"min_pos": 19, "max_pos": 20},
        },
    },

    "Serie C - Girone B": {
        "total_matches": 38,
        "zones": {
            "promotion_direct":   {"min_pos": 1,  "max_pos": 1},
            "promotion_playoff":  {"min_pos": 2,  "max_pos": 10},
            "mid_table":          {"min_pos": 11, "max_pos": 15},
            "relegation_playout": {"min_pos": 16, "max_pos": 18},
            "relegation":         {"min_pos": 19, "max_pos": 20},
        },
    },

    "Serie C - Girone C": {
        "total_matches": 38,
        "zones": {
            "promotion_direct":   {"min_pos": 1,  "max_pos": 1},
            "promotion_playoff":  {"min_pos": 2,  "max_pos": 10},
            "mid_table":          {"min_pos": 11, "max_pos": 15},
            "relegation_playout": {"min_pos": 16, "max_pos": 18},
            "relegation":         {"min_pos": 19, "max_pos": 20},
        },
    },

    # =======================
    # INGHILTERRA
    # =======================

    "Premier League": {
        "total_matches": 38,
        "zones": {
            "title":              {"min_pos": 1,  "max_pos": 1},
            "ucl":                {"min_pos": 1,  "max_pos": 4},
            "uel_uecl":           {"min_pos": 5,  "max_pos": 7},
            "mid_table":          {"min_pos": 8,  "max_pos": 14},
            "relegation_fight":   {"min_pos": 15, "max_pos": 17},
            "relegation":         {"min_pos": 18, "max_pos": 20},
        },
    },

    # =======================
    # SPAGNA
    # =======================

    "La Liga": {
        "total_matches": 38,
        "zones": {
            "title":              {"min_pos": 1,  "max_pos": 1},
            "ucl":                {"min_pos": 1,  "max_pos": 4},
            "uel_uecl":           {"min_pos": 5,  "max_pos": 7},
            "mid_table":          {"min_pos": 8,  "max_pos": 14},
            "relegation_fight":   {"min_pos": 15, "max_pos": 17},
            "relegation":         {"min_pos": 18, "max_pos": 20},
        },
    },

    # =======================
    # GERMANIA
    # =======================

    "Bundesliga": {
        "total_matches": 34,   # 18 squadre, 34 giornate
        "zones": {
            "title":              {"min_pos": 1,  "max_pos": 1},
            "ucl":                {"min_pos": 1,  "max_pos": 4},
            "uel_uecl":           {"min_pos": 5,  "max_pos": 6},
            "mid_table":          {"min_pos": 7,  "max_pos": 13},
            "relegation_playout": {"min_pos": 16, "max_pos": 16},  # Spareggio salvezza
            "relegation":         {"min_pos": 17, "max_pos": 18},
        },
    },

    # =======================
    # FRANCIA
    # =======================

    "Ligue 1": {
        "total_matches": 34,   # formato 18 squadre recente
        "zones": {
            "title":              {"min_pos": 1,  "max_pos": 1},
            "ucl":                {"min_pos": 1,  "max_pos": 3},
            "uel_uecl":           {"min_pos": 4,  "max_pos": 5},
            "mid_table":          {"min_pos": 6,  "max_pos": 14},
            "relegation_fight":   {"min_pos": 15, "max_pos": 16},
            "relegation":         {"min_pos": 17, "max_pos": 18},
        },
    },

    # =======================
    # OLANDA
    # =======================

    "Eredivisie": {
        "total_matches": 34,   # 18 squadre
        "zones": {
            "title":              {"min_pos": 1,  "max_pos": 1},
            "ucl":                {"min_pos": 1,  "max_pos": 2},   # Champions / qualificazioni
            "europa_playoffs":    {"min_pos": 3,  "max_pos": 8},   # playoff posti europei
            "mid_table":          {"min_pos": 9,  "max_pos": 14},
            "relegation_playout": {"min_pos": 16, "max_pos": 16},  # playoff retrocessione
            "relegation":         {"min_pos": 17, "max_pos": 18},
        },
    },

    # =======================
    # PORTOGALLO
    # =======================

    "Liga Portugal": {
        "total_matches": 34,   # 18 squadre
        "zones": {
            "title":              {"min_pos": 1,  "max_pos": 1},
            "ucl":                {"min_pos": 1,  "max_pos": 3},   # Champions/qualificazioni
            "uel_uecl":           {"min_pos": 4,  "max_pos": 6},   # Europa/Conference
            "mid_table":          {"min_pos": 7,  "max_pos": 12},
            "relegation_playout": {"min_pos": 16, "max_pos": 16},  # playout salvezza
            "relegation":         {"min_pos": 17, "max_pos": 18},
        },
    },
}
