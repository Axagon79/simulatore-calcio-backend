import numpy as np
import random

def calculate_goals_from_engine(home_score, away_score, home_data, away_data):
    """
    Versione OLISTICA COMPLETA: Usa TUTTI i fattori del motore per calcolare i gol.
    """
    
    # --- 1. ESTRAZIONE TOTALE DEI DATI ---
    h_luc = home_data.get('lucifero', 0.0)
    a_luc = away_data.get('lucifero', 0.0)
    
    h_att = home_data.get('attack', 5.0)
    h_def = home_data.get('defense', 5.0)
    a_att = away_data.get('attack', 5.0)
    a_def = away_data.get('defense', 5.0)
    
    h_h2h_avg = home_data.get('h2h_avg_goals', 1.2)
    a_h2h_avg = away_data.get('h2h_avg_goals', 1.0)
    
    # Nuovi Fattori Espliciti
    h_motiv = home_data.get('motivation', 5.0)
    a_motiv = away_data.get('motivation', 5.0)
    
    h_field = home_data.get('field_factor', 3.5) # 3.5 è neutro
    a_field = away_data.get('field_factor', 3.5)
    
    h_rel = home_data.get('reliability', 3.5) # Affidabilità (costanza)
    a_rel = away_data.get('reliability', 3.5)
    
    # --- 2. CALCOLO BASE (Gap Punteggio) ---
    # Questo cattura il "Vincitore Generale" (chi è più forte complessivamente)
    gap = home_score - away_score
    base_xg_h = 1.35
    base_xg_a = 1.05
    
    gap_bonus = (gap / 10.0) * 0.40 # Ridotto leggermente per lasciare spazio agli altri fattori
    xg_h = base_xg_h + (gap_bonus if gap > 0 else gap_bonus / 2)
    xg_a = base_xg_a - (gap_bonus if gap > 0 else gap_bonus / 2)
    
    # --- 3. FATTORE TECNICO (Attacco vs Difesa) ---
    tech_h = (h_att / max(a_def, 1.0)) ** 0.5
    tech_a = (a_att / max(h_def, 1.0)) ** 0.5
    xg_h *= tech_h
    xg_a *= tech_a

    # --- 4. FATTORE FORMA (Lucifero) ---
    luc_factor_h = max(0.8, min(1.3, (h_luc + 3) / 9.0)) 
    luc_factor_a = max(0.8, min(1.3, (a_luc + 3) / 9.0))
    xg_h *= luc_factor_h
    xg_a *= luc_factor_a

    # --- 5. FATTORE CAMPO & MOTIVAZIONE (Nuovi!) ---
    # Motivazione: Se > 5, spinge i gol. Se < 5, squadra depressa.
    mot_h = max(0.8, min(1.2, h_motiv / 5.0))
    mot_a = max(0.8, min(1.2, a_motiv / 5.0))
    
    # Campo: Se il fattore campo è alto (es. 5.0), casa vola.
    field_h = max(0.9, min(1.3, h_field / 3.5))
    # Ospite subisce il fattore campo avverso (a_field è il suo rendimento fuori)
    field_a = max(0.8, min(1.2, a_field / 3.5))
    
    xg_h *= (mot_h * field_h)
    xg_a *= (mot_a * field_a)

    # --- 6. MIX CON STORICO H2H (Peso 20%) ---
    final_xg_h = (xg_h * 0.80) + (h_h2h_avg * 0.20)
    final_xg_a = (xg_a * 0.80) + (a_h2h_avg * 0.20)
    
    final_xg_h = max(0.05, final_xg_h)
    final_xg_a = max(0.05, final_xg_a)

    # --- 7. FATTORE AFFIDABILITÀ (Varianza) ---
    # Squadre poco affidabili (reliability bassa) rendono la partita più pazza.
    # reliability = 1 (pazza) -> varianza alta
    # reliability = 5 (solida) -> varianza bassa
    
    avg_reliability = (h_rel + a_rel) / 2
    chaos_probability = 0.15 + ( (5.0 - avg_reliability) * 0.05 ) 
    # Es: Se affidabilità è 2.0 (bassa), prob chaos sale da 15% a 30%
    
    chaos_probability = min(0.40, max(0.05, chaos_probability)) # Cap tra 5% e 40%

    # --- 8. CHAOS FACTOR DINAMICO 🎲 ---
    chaos_msg = ""
    roll = random.random()
    
    if roll < chaos_probability:
        event = random.choice(['boost_h', 'boost_a', 'nerf_h', 'nerf_a', 'pazza'])
        
        if event == 'boost_h': 
            final_xg_h += 0.8; chaos_msg = "🔥 (Caos: Casa Fortunata!)"
        elif event == 'boost_a': 
            final_xg_a += 0.8; chaos_msg = "🔥 (Caos: Ospite Fortunata!)"
        elif event == 'nerf_h': 
            final_xg_h *= 0.5; chaos_msg = "❄️ (Caos: Casa Sfortunata!)"
        elif event == 'nerf_a': 
            final_xg_a *= 0.5; chaos_msg = "❄️ (Caos: Ospite Sfortunata!)"
        elif event == 'pazza': 
            final_xg_h += 1.2; final_xg_a += 1.2; chaos_msg = "🌪️ (Caos: Partita Pazza!)"

    # --- 9. POISSON ---
    goals_h = np.random.poisson(final_xg_h)
    goals_a = np.random.poisson(final_xg_a)
    
    return goals_h, goals_a, round(final_xg_h, 2), round(final_xg_a, 2), chaos_msg
