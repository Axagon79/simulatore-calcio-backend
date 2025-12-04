def calculate_match_prediction(home, away):

    # --- FASE 1: COSTRUZIONE ATTACCO (Somma dei bonus) ---
    hg = 0.2 # Base
    ag = 0.2 # Base

    # 1. Tecnica & Valore
    hg += get_attacco(home)      # calculate_attacco_difesa
    hg += get_rosa_value(home)   # calculate_valore_rosa
    hg += get_rating(home)       # calculate_team_rating / serie_c_rating

    # 2. Momento & Psicologia
    hg += get_lucifero(home)     # calculator_lucifero
    hg += get_motivazioni(home)  # calculate_motivazioni
    hg += get_home_factor(home)  # calculator_fattore_campo (Solo casa)

    # 3. Storia & Mercato
    hg += get_bvs_bonus(home)    # calculator_bvs
    hg += get_h2h_bonus(home)    # calculate_h2h_v2 (Se favorevole)

    # (Idem per Away...)

    # --- FASE 2: RESISTENZA DIFENSIVA (Sottrazione) ---
    
    # Calcolo la "Forza Scudo" dell'avversario
    shield_away = get_difesa(away) + (get_rosa_value(away) * 0.5) # La rosa conta anche in difesa
    shield_home = get_difesa(home) + (get_rosa_value(home) * 0.5)

    # Sottrazione
    hg_final = hg - (shield_away * FATTORE_EROSIONE)
    ag_final = ag - (shield_home * FATTORE_EROSIONE)

    # --- FASE 3: CORREZIONE AFFIDABILITÀ ---
    # Se una squadra è "Inaffidabile" (calculator_affidabilità basso),
    # aumentiamo il CASO (Random) su di lei.
    random_range_home = 0.15 # Standard 15%
    if get_affidabilita(home) < 4: # Se poco affidabile
        random_range_home = 0.30 # Raddoppia l'imprevedibilità!

    hg_final = apply_random(hg_final, random_range_home)
    ag_final = apply_random(ag_final, random_range_away)

    return hg_final, ag_final
