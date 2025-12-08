import numpy as np
import random
import os
import sys
import json

# --- 1. CONFIGURAZIONE PERCORSI E DB ---
current_path = os.path.dirname(os.path.abspath(__file__))
parent_path = os.path.dirname(current_path)
sys.path.append(current_path)

try:
    from config import db
    stats_collection = db['team_seasonal_stats']
    DB_AVAILABLE = True
except:
    DB_AVAILABLE = False


# --- 2. CARICAMENTO MEDIE LEGHE (JSON) ---
LEAGUE_STATS_FILE = os.path.join(current_path, "league_stats.json")
LEAGUE_AVERAGES = {}

try:
    if os.path.exists(LEAGUE_STATS_FILE):
        with open(LEAGUE_STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for league, stats in data.items():
                # Carichiamo la media gol della lega (es. 2.50) e la dividiamo per 2 (squadra)
                val = stats.get("avg_goals", 2.5) if isinstance(stats, dict) else stats
                LEAGUE_AVERAGES[league] = val / 2.0
except Exception as e:
    print(f"⚠️ Warning: Impossibile caricare league_stats.json ({e})")

def get_league_avg(league_name):
    # Default 1.25 gol a squadra se lega sconosciuta
    return LEAGUE_AVERAGES.get(league_name, 1.25)


# --- 3. CACHE FBREF (Volume Totale Squadra) ---
FBREF_CACHE = {}

def get_team_fbref_data(team_name):
    """
    Recupera il Volume Totale (xG medio) da FBRef. 
    Usa una cache locale per non interrogare il DB durante il Monte Carlo.
    """
    # 1. Se l'abbiamo già letto, ritorna subito il valore salvato
    if team_name in FBREF_CACHE:
        return FBREF_CACHE[team_name]

    # 2. Se non c'è il DB disponibile, ritorna un default conservativo
    if not DB_AVAILABLE:
        return 2.5

    # 3. Leggi dal DB (Operazione lenta su migliaia di simulazioni)
    doc = stats_collection.find_one({"team": team_name})
    if doc:
        val = float(doc.get("total_volume_avg", 2.5))
    else:
        val = 2.5

    # 4. Salva in Cache per la prossima volta
    FBREF_CACHE[team_name] = val
    return val


# --- 4. MOTORE DI CALCOLO DEFINITIVO (DOPPIO MOTORE: WIN + GOL) ---

def calculate_goals_from_engine(home_score, away_score, home_data, away_data, algo_mode=5, league_name="Unknown", home_name="Home", away_name="Away"):
    """
    MOTORE V11: PESI CONDIVISI MA RUOLI DIVERSI
    I pesi lavorano su entrambi i motori (Win & Gol) dove ha senso.
    
    Parametri:
    - home_score/away_score: Punteggi grezzi dal motore principale (H2H points)
    - home_data/away_data: Dizionari completi con tutti i pesi (Rating, Lucifero, Motivation...)
    """

    # --- A. ESTRAZIONE DATI COMPLETI ---
    
    # Rating (Forza Rosa 5-25)
    h_rat = home_data.get('rating', 12.5)
    a_rat = away_data.get('rating', 12.5)
    
    # BVS (Valore Quote vs Picchetto)
    h_bvs = home_data.get('bvs', 0.0)
    a_bvs = away_data.get('bvs', 0.0)
    
    # Motivazione (0-15) & Fattore Campo (0-7)
    h_mot = home_data.get('motivation', 10.0)
    a_mot = away_data.get('motivation', 10.0)
    h_fld = home_data.get('field_factor', 3.5)
    a_fld = away_data.get('field_factor', 3.5)
    
    # Lucifero (Forma Recente 0-25) & Affidabilità (0-10)
    h_luc = home_data.get('lucifero', 12.5) 
    a_luc = away_data.get('lucifero', 12.5)
    h_rel = home_data.get('reliability', 5.0)
    a_rel = away_data.get('reliability', 5.0)

    # H2H (Punteggio Vittoria & Media Gol Storica)
    h_h2h_win = home_score  # Punteggio calcolato dall'H2H Calculator
    a_h2h_win = away_score
    h_h2h_g = home_data.get('h2h_avg_goals', 1.2) # Media gol storica scontri diretti
    a_h2h_g = away_data.get('h2h_avg_goals', 1.0)
    
    # Dati Tecnici (Attacco 0-15 / Difesa 0-10 / Volume FBRef)
    vol_h = get_team_fbref_data(home_name)
    vol_a = get_team_fbref_data(away_name)
    h_att = home_data.get('attack', 7.5)
    a_att = away_data.get('attack', 7.5)
    h_def = home_data.get('defense', 5.0)
    a_def = away_data.get('defense', 5.0)


    # --- B. MOTORE WIN: CHI COMANDA? (Probabilità 1X2) ---
    # Calcoliamo uno "Score Dominio" indipendente dai gol previsti.
    # Usiamo TUTTI i pesi che contribuiscono a vincere una partita.
    
    score_h = (
        (h_rat * 0.25) +     # Forza Rating (25%): La rosa conta molto
        (h_bvs * 0.20) +     # Valore Quote (20%): Dove il bookmaker sbaglia
        (h_luc * 0.15) +     # Forma (15%): Lucifero "Win" (Stato di grazia)
        (h_h2h_win * 0.15) + # Storia (15%): Tradizione vittorie
        (h_mot * 0.10) +     # Motivazione (10%): Fame di punti
        (h_fld * 0.10) +     # Fattore Campo (10%): Spinta pubblico
        (h_rel * 0.05)       # Affidabilità (5%): Costanza risultati
    )
    
    score_a = (
        (a_rat * 0.25) + 
        (a_bvs * 0.20) + 
        (a_luc * 0.15) + 
        (a_h2h_win * 0.15) +
        (a_mot * 0.10) + 
        (a_fld * 0.10) + 
        (a_rel * 0.05)
    )
    
    # Differenza di dominio (Delta)
    diff_dominio = score_h - score_a
    
    # Win Shift: Sposta l'inerzia probabilistica
    # Se la differenza è 0 (equilibrio), shift è 0.
    # Se la differenza è alta, shift tende verso ±0.55 (55% di vantaggio).
    # Usiamo tanh per una curva morbida che non "esplode".
    win_shift = np.tanh(diff_dominio / 25.0) * 0.40
    

    # --- C. MOTORE GOL: CHE ARIA TIRA? (Aspettativa Gol) ---
    # Calcoliamo quanti gol ci aspettiamo indipendentemente da chi vince.
    # Qui usiamo pesi che indicano "Spettacolo" e "Ritmo".
    
    # 1. Base statistica (Volume FBRef diviso 2 per squadra)
    base_lambda_h = vol_h / 2.0
    base_lambda_a = vol_a / 2.0
    
    # 2. Lucifero (SHARED - Lato Gol)
    # Una squadra in forma (Lucifero alto) è più cinica e precisa.
    # Una squadra fuori forma (Lucifero basso) spreca occasioni.
    form_factor_h = 1 + ((h_luc - 12.5) / 60.0) 
    form_factor_a = 1 + ((a_luc - 12.5) / 60.0)
    
    # 3. H2H Storico (SHARED - Lato Gol)
    # Se storicamente si segnano 4 gol a partita, alziamo l'aspettativa.
    hist_factor_h = max(0.85, min(1.15, h_h2h_g / 1.3)) 
    hist_factor_a = max(0.85, min(1.15, a_h2h_g / 1.1))
    
    # 4. Fattore Tattico (Puro tecnico: Attacco vs Difesa)
    # Se la difesa avversaria è forte (10), il fattore scende < 1.
    # Se la difesa è un colabrodo (0), il fattore sale > 1.
    tactical_h = (h_att / 7.5) * (1 + (5.0 - a_def)/15.0) 
    tactical_a = (a_att / 7.5) * (1 + (5.0 - h_def)/15.0)
    
    # 5. Calcolo RAW (Aspettativa Gol Pura)
    raw_lambda_h = base_lambda_h * tactical_h * form_factor_h * hist_factor_h
    raw_lambda_a = base_lambda_a * tactical_a * form_factor_a * hist_factor_a


    # --- D. FUSIONE MOTORI (SINTESI) ---
    # Il "Chi vince" (Win Shift) piega il "Quanti gol" (Raw Lambda).
    # Chi domina vede salire la sua probabilità di concretizzare i gol previsti.
    # Chi subisce vede scendere la sua probabilità, anche se ha un buon attacco.
    
    final_lambda_h = raw_lambda_h * (1 + win_shift)
    final_lambda_a = raw_lambda_a * (1 - win_shift)
    
    # Safety Cap (Limiti fisici del calcio)
    # Minimo 0.15 gol attesi (mai zero assoluto), Massimo 3.8 (goleada rara)
    final_lambda_h = max(0.15, min(3.8, final_lambda_h))
    final_lambda_a = max(0.15, min(3.8, final_lambda_a))
    
    
    # --- E. GENERAZIONE RISULTATO (POISSON) ---
    # Simulazione Monte Carlo basata sulle aspettative finali
    gh = np.random.poisson(final_lambda_h)
    ga = np.random.poisson(final_lambda_a)
    
    # Stringa di debug per vedere i valori calcolati (xG previsti)
    xg_info = f"{final_lambda_h:.2f}-{final_lambda_a:.2f}"
    
    return gh, ga, final_lambda_h, final_lambda_a, xg_info
