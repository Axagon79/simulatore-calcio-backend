"""
Tre varianti di tolleranze per validation comparativa:
- BASE: tolleranze originali (T1 strettissima, T5 larga)
- WIDE_A: T1 invariato, T2/T3 allargati ~+15-20%
- WIDE_B: T1 leggermente allargato, T2/T3 allargati ~+30-40%

T4 e T5 restano invariati in tutte le varianti (sono gia larghe).
"""

# Variante BASE = match_engine.TOLERANCES originale
TOLERANCES_BASE = {
    "giornata":                                    [0, 1, 2, 4, 6],
    "posizione_classifica_casa":                   [0, 1, 2, 4, 6],
    "posizione_classifica_ospite":                 [0, 1, 2, 4, 6],
    "punti_casa":                                  [0, 2, 4, 7, 12],
    "punti_ospite":                                [0, 2, 4, 7, 12],
    "differenza_punti":                            [0, 2, 5, 10, 15],
    "partite_giocate_casa":                        [0, 1, 2, 4, 6],
    "partite_giocate_ospite":                      [0, 1, 2, 4, 6],
    "gol_fatti_casa":                              [0, 3, 6, 10, 15],
    "gol_subiti_casa":                             [0, 3, 6, 10, 15],
    "gol_fatti_ospite":                            [0, 3, 6, 10, 15],
    "gol_subiti_ospite":                           [0, 3, 6, 10, 15],
    "posizione_classifica_casa_solo_casalinga":    [0, 1, 2, 4, 6],
    "punti_casa_solo_casalinga":                   [0, 1, 3, 6, 10],
    "posizione_classifica_ospite_solo_trasferta":  [0, 1, 2, 4, 6],
    "punti_ospite_solo_trasferta":                 [0, 1, 3, 6, 10],
    "prob_implicita_1":                            [0.0, 0.015, 0.04, 0.08, 0.15],
    "prob_implicita_X":                            [0.0, 0.015, 0.04, 0.08, 0.15],
    "prob_implicita_2":                            [0.0, 0.015, 0.04, 0.08, 0.15],
    "elo_casa":                                    [0, 15, 35, 75, 150],
    "elo_ospite":                                  [0, 15, 35, 75, 150],
    "elo_diff":                                    [0, 20, 50, 100, 200],
}

# Variante WIDE_A: T1 invariato, T2 e T3 allargate ~+15-20%
TOLERANCES_WIDE_A = {
    "giornata":                                    [0, 2, 3, 4, 6],
    "posizione_classifica_casa":                   [0, 2, 3, 4, 6],
    "posizione_classifica_ospite":                 [0, 2, 3, 4, 6],
    "punti_casa":                                  [0, 3, 6, 7, 12],
    "punti_ospite":                                [0, 3, 6, 7, 12],
    "differenza_punti":                            [0, 3, 7, 10, 15],
    "partite_giocate_casa":                        [0, 2, 3, 4, 6],
    "partite_giocate_ospite":                      [0, 2, 3, 4, 6],
    "gol_fatti_casa":                              [0, 4, 8, 10, 15],
    "gol_subiti_casa":                             [0, 4, 8, 10, 15],
    "gol_fatti_ospite":                            [0, 4, 8, 10, 15],
    "gol_subiti_ospite":                           [0, 4, 8, 10, 15],
    "posizione_classifica_casa_solo_casalinga":    [0, 2, 3, 4, 6],
    "punti_casa_solo_casalinga":                   [0, 2, 4, 6, 10],
    "posizione_classifica_ospite_solo_trasferta":  [0, 2, 3, 4, 6],
    "punti_ospite_solo_trasferta":                 [0, 2, 4, 6, 10],
    "prob_implicita_1":                            [0.0, 0.02, 0.05, 0.08, 0.15],
    "prob_implicita_X":                            [0.0, 0.02, 0.05, 0.08, 0.15],
    "prob_implicita_2":                            [0.0, 0.02, 0.05, 0.08, 0.15],
    "elo_casa":                                    [0, 25, 50, 75, 150],
    "elo_ospite":                                  [0, 25, 50, 75, 150],
    "elo_diff":                                    [0, 30, 70, 100, 200],
}

# Variante WIDE_B: T1 leggermente allargato, T2/T3 ~+30-40%
TOLERANCES_WIDE_B = {
    "giornata":                                    [1, 2, 4, 5, 7],
    "posizione_classifica_casa":                   [1, 2, 4, 5, 7],
    "posizione_classifica_ospite":                 [1, 2, 4, 5, 7],
    "punti_casa":                                  [1, 4, 7, 9, 14],
    "punti_ospite":                                [1, 4, 7, 9, 14],
    "differenza_punti":                            [1, 4, 7, 12, 17],
    "partite_giocate_casa":                        [1, 2, 4, 5, 7],
    "partite_giocate_ospite":                      [1, 2, 4, 5, 7],
    "gol_fatti_casa":                              [2, 5, 9, 12, 17],
    "gol_subiti_casa":                             [2, 5, 9, 12, 17],
    "gol_fatti_ospite":                            [2, 5, 9, 12, 17],
    "gol_subiti_ospite":                           [2, 5, 9, 12, 17],
    "posizione_classifica_casa_solo_casalinga":    [1, 2, 4, 5, 7],
    "punti_casa_solo_casalinga":                   [1, 3, 5, 8, 12],
    "posizione_classifica_ospite_solo_trasferta":  [1, 2, 4, 5, 7],
    "punti_ospite_solo_trasferta":                 [1, 3, 5, 8, 12],
    "prob_implicita_1":                            [0.005, 0.025, 0.06, 0.10, 0.17],
    "prob_implicita_X":                            [0.005, 0.025, 0.06, 0.10, 0.17],
    "prob_implicita_2":                            [0.005, 0.025, 0.06, 0.10, 0.17],
    "elo_casa":                                    [10, 25, 55, 90, 170],
    "elo_ospite":                                  [10, 25, 55, 90, 170],
    "elo_diff":                                    [15, 35, 80, 120, 220],
}


VARIANTS = {
    "BASE":   TOLERANCES_BASE,
    "WIDE_A": TOLERANCES_WIDE_A,
    "WIDE_B": TOLERANCES_WIDE_B,
}
