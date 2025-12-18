import numpy as np
import random
import os
import sys
import json

# (** TRADUTTORE FINALE: CONVERTE I PUNTEGGI NUMERICI ASTRATTI (POWER) IN GOL REALI (0-0, 2-1) **)
# ( GESTISCE LA LOGICA DI "ARROTONDAMENTO INTELLIGENTE" PER EVITARE RISULTATI IMPOSSIBILI (ES. 2.5 GOL) )
# ( CONTIENE LE TABELLE DI CONVERSIONE E LE PROBABILITÀ PER I RISULTATI ESATTI )

# --- 0. CONFIGURAZIONE TUNING MIXER ---
TUNING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tuning_settings.json")

def load_tuning(algo_mode="GLOBAL"):
    """
    Carica i settaggi dal file JSON.
    Accetta int (1,2,3...) o stringa ("GLOBAL").
    """
    try:
        if not os.path.exists(TUNING_FILE):
            return {}

        with open(TUNING_FILE, "r", encoding="utf-8") as f:
            full_data = json.load(f)

        # Mappa: Numero -> Nome Chiave JSON
        algo_map = {
            1: "ALGO_1",
            2: "ALGO_2",
            3: "ALGO_3",
            4: "ALGO_4",
            5: "ALGO_5"
        }

        # Determinazione della chiave target
        if isinstance(algo_mode, int):
            # Se è un numero (es. 1), cercalo nella mappa. Fallback: GLOBAL
            target_key = algo_map.get(algo_mode, "GLOBAL")
        else:
            # Se è già una stringa o altro (es. "GLOBAL"), usalo direttamente
            target_key = str(algo_mode)

        merged_settings = {}

        # 1. Carica SEMPRE la base GLOBAL (Master)
        if "GLOBAL" in full_data:
            for k, v_obj in full_data["GLOBAL"].items():
                if isinstance(v_obj, dict) and "valore" in v_obj:
                    merged_settings[k] = v_obj["valore"]

        # 2. Sovrascrivi con lo Specifico (solo se diverso da GLOBAL)
        if target_key != "GLOBAL" and target_key in full_data:
            for k, v_obj in full_data[target_key].items():
                if isinstance(v_obj, dict) and "valore" in v_obj:
                    merged_settings[k] = v_obj["valore"]

        return merged_settings

    except Exception as e:
        print(f"⚠️ Errore caricamento tuning: {e}")
        return {}

 

# --- CARICAMENTO INIZIALE ---
# Carichiamo il MASTER (GLOBAL) come base
S = load_tuning("GLOBAL")



# Se i settaggi mancano, usa questi default di sicurezza
S.setdefault("DIVISORE_MEDIA_GOL", 2.0)
S.setdefault("POTENZA_FAVORITA_WINSHIFT", 0.40)
S.setdefault("IMPATTO_DIFESA_TATTICA", 15.0)
S.setdefault("TETTO_MAX_GOL_ATTESI", 3.8)


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

def calculate_goals_from_engine(home_score, away_score, home_data, away_data, algo_mode=5, league_name="Unknown", home_name="Home", away_name="Away", debug_mode=True):
    """
    MOTORE V11: PESI CONDIVISI MA RUOLI DIVERSI
    I pesi lavorano su entrambi i motori (Win & Gol) dove ha senso.
    
    Parametri:
    - home_score/away_score: Punteggi grezzi dal motore principale (H2H points)
    - home_data/away_data: Dizionari completi con tutti i pesi (Rating, Lucifero, Motivation...)
        """

    # ⚡ CARICAMENTO DINAMICO DEI PESI ⚡
    # Ricarichiamo i pesi specifici per l'algoritmo richiesto (algo_mode)
    # Questa variabile 'S' oscurerà quella globale solo dentro questa funzione.
    S = load_tuning(algo_mode)

        # --- INIZIO SPIA DEBUG COMPLETA (SOLO SE RICHIESTO) ---
    if debug_mode:
        print(f"\n Sto usando ALGO: {algo_mode}")
        print(f"   --- MIXER PESI (WIN) ---")
        print(f"   -> Rating Rosa:     {S.get('PESO_RATING_ROSA', 1.0)}")
        print(f"   -> BVS Quote:       {S.get('PESO_BVS_QUOTE', 1.0)}")
        print(f"   -> Forma Recente:   {S.get('PESO_FORMA_RECENTE', 1.0)}")
        print(f"   -> Storia H2H:      {S.get('PESO_STORIA_H2H', 1.0)}")
        print(f"   -> Motivazione:     {S.get('PESO_MOTIVAZIONE', 1.0)}")
        print(f"   -> Fattore Campo:   {S.get('PESO_FATTORE_CAMPO', 1.0)}")
        print(f"   -> Affidabilità:    {S.get('PESO_AFFIDABILITA', 1.0)}")
        print(f"   --- MIXER PARAMETRI (GOL) ---")
        print(f"   -> Divisore Media:  {S.get('DIVISORE_MEDIA_GOL', 2.0)}")
        print(f"   -> Impatto Difesa:  {S.get('IMPATTO_DIFESA_TATTICA', 15.0)}")
        print(f"   -> WinShift Power:  {S.get('POTENZA_FAVORITA_WINSHIFT', 0.40)}")
        print(f"   -> Tetto Max Gol:   {S.get('TETTO_MAX_GOL_ATTESI', 3.8)}")
        print("------------------------------------------------")
    # --- FINE SPIA DEBUG ---



    # Assicuriamoci che ci siano i valori di default critici se mancano nel file
    S.setdefault("DIVISORE_MEDIA_GOL", 2.0)
    S.setdefault("POTENZA_FAVORITA_WINSHIFT", 0.40)
    S.setdefault("IMPATTO_DIFESA_TATTICA", 15.0)
    S.setdefault("TETTO_MAX_GOL_ATTESI", 3.8)
    S.setdefault("PESO_RATING_ROSA", 1.0) # Default per i pesi motore se mancano

        # --- A. ESTRAZIONE DATI COMPLETI ---

    # Rating (Forza Rosa 5-25) -> Default 12.5
    h_rat = float(home_data.get('rating', 12.5))
    a_rat = float(away_data.get('rating', 12.5))
    
    # BVS (Valore Quote vs Picchetto) -> Default 0.0
    h_bvs = float(home_data.get('bvs', 0.0))
    a_bvs = float(away_data.get('bvs', 0.0))
    
    # Motivazione (5-15) & Fattore Campo (0-7)
    h_mot = float(home_data.get('motivation', 10.0))
    a_mot = float(away_data.get('motivation', 10.0))
    h_fld = float(home_data.get('field_factor', 3.5))
    a_fld = float(away_data.get('field_factor', 3.5))
    
    # Lucifero (Forma Recente 0-25) & Affidabilità (0-10)
    h_luc = float(home_data.get('lucifero', 12.5)) 
    a_luc = float(away_data.get('lucifero', 12.5))
    h_rel = float(home_data.get('reliability', 5.0))
    a_rel = float(away_data.get('reliability', 5.0))
    
    # Valore Rosa (3-10) -> NUOVO, Default 4.5
    h_rosa = float(home_data.get('strength_score', 4.5))
    a_rosa = float(away_data.get('strength_score', 4.5))

    # H2H (Punteggio Vittoria & Media Gol Storica)
    # ✅ Usa il voto H2H puro passato dall'engine dentro home_data/away_data
    h_h2h_win = float(home_data.get('h2h_score', 5.0))
    a_h2h_win = float(away_data.get('h2h_score', 5.0))
    h_h2h_g = float(home_data.get('h2h_avg_goals', 1.2))
    a_h2h_g = float(away_data.get('h2h_avg_goals', 1.0))
    
    # Dati Tecnici (Attacco 0-15 / Difesa 0-10 / Volume FBRef)
    vol_h = get_team_fbref_data(home_name)
    vol_a = get_team_fbref_data(away_name)
    h_att = float(home_data.get('attack', 7.5))
    a_att = float(away_data.get('attack', 7.5))
    h_def = float(home_data.get('defense', 5.0))
    a_def = float(away_data.get('defense', 5.0))
    
    # Tecnica Totale (Att+Dif) -> NUOVO CALCOLO
    # Range: 0-25 (Att 0-15 + Dif 0-10) -> Default Medio: 12.5
    h_tec = h_att + h_def
    a_tec = a_att + a_def



        # --- B. MOTORE WIN: CHI COMANDA? (Probabilità 1X2) ---
    # Calcoliamo uno "Score Dominio" indipendente dai gol previsti.
    
    # Pesi Ribilanciati (Totale ~1.0)
    W_RAT = 0.20 * S.get("PESO_RATING_ROSA", 1.0)       # 20%
    W_TEC = 0.15 * S.get("PESO_TECNICA", 1.0)           # 15% (Nuovo)
    W_BVS = 0.15 * S.get("PESO_BVS_QUOTE", 1.0)         # 15%
    W_LUC = 0.15 * S.get("PESO_FORMA_RECENTE", 1.0)     # 15%
    W_H2H = 0.10 * S.get("PESO_STORIA_H2H", 1.0)        # 10%
    W_MOT = 0.10 * S.get("PESO_MOTIVAZIONE", 1.0)       # 10%
    W_FLD = 0.05 * S.get("PESO_FATTORE_CAMPO", 1.0)     # 5%
    W_ROS = 0.05 * S.get("PESO_ROSA_EXTRA", 1.0)        # 5% (Nuovo)
    W_AFF = 0.05 * S.get("PESO_AFFIDABILITA", 1.0)      # 5%

    score_h = (
        (h_rat * W_RAT) + 
        (h_tec * W_TEC) + 
        (h_bvs * W_BVS) + 
        (h_luc * W_LUC) + 
        (h_h2h_win * W_H2H) + 
        (h_mot * W_MOT) + 
        (h_fld * W_FLD) + 
        (h_rosa * W_ROS) + 
        (h_rel * W_AFF)
    )
    
    score_a = (
        (a_rat * W_RAT) + 
        (a_tec * W_TEC) + 
        (a_bvs * W_BVS) + 
        (a_luc * W_LUC) + 
        (a_h2h_win * W_H2H) + 
        (a_mot * W_MOT) + 
        (a_fld * W_FLD) + 
        (a_rosa * W_ROS) + 
        (a_rel * W_AFF)
    )

    
        # --- INIZIO SCONTRINO FISCALE (Solo se Debug Attivo) ---
    if debug_mode:
        print(f"\n   📊 SCONTRINO FISCALE PUNTI ({home_name} vs {away_name})")
        print(f"   {'VOCE':<15} | {home_name + ' (Val x Peso = Pt)':<28} | {away_name + ' (Val x Peso = Pt)':<28}")
        print("-" * 80)
        
        # Funzione helper per formattare la riga
        def p_row(label, val_h, val_a, weight_val):
            pt_h = val_h * weight_val
            pt_a = val_a * weight_val
            # Formattazione: Valore x Peso = Punti
            str_h = f"{val_h:5.2f} x {weight_val:.2f} = {pt_h:5.2f}"
            str_a = f"{val_a:5.2f} x {weight_val:.2f} = {pt_a:5.2f}"
            print(f"   {label:<15} | {str_h:<28} | {str_a:<28}")

        # Stampa delle 9 voci
        p_row("Rating",      h_rat, a_rat, W_RAT)
        p_row("Tecnica",     h_tec, a_tec, W_TEC)   # NUOVO
        p_row("BVS Quote",   h_bvs, a_bvs, W_BVS)
        p_row("Forma",       h_luc, a_luc, W_LUC)
        p_row("Storia H2H",  h_h2h_win, a_h2h_win, W_H2H)
        p_row("Motivazione", h_mot, a_mot, W_MOT)
        p_row("Fattore Campo", h_fld, a_fld, W_FLD)
        p_row("Valore Rosa", h_rosa, a_rosa, W_ROS) # NUOVO
        p_row("Affidabilità", h_rel, a_rel, W_AFF)
        
        print("-" * 80)
        print(f"   {'TOTALE PUNTI':<15} | {score_h:<28.2f} | {score_a:<28.2f}")
        print(f"   {'DIFFERENZA':<15} | {score_h - score_a:.2f} (Vantaggio {'CASA' if score_h > score_a else 'OSPITE'})")
        print("------------------------------------------------")
    # --- FINE SCONTRINO FISCALE ---


    
    # Differenza di dominio (Delta)
    diff_dominio = score_h - score_a
    
    
    
    # Win Shift: Sposta l'inerzia probabilistica
    # Se la differenza è 0 (equilibrio), shift è 0.
    # Usiamo tanh per una curva morbida che non "esplode".
    win_shift = np.tanh(diff_dominio / 25.0) * S["POTENZA_FAVORITA_WINSHIFT"]
    

    # --- C. MOTORE GOL: CHE ARIA TIRA? (Aspettativa Gol) ---
    # Calcoliamo quanti gol ci aspettiamo indipendentemente da chi vince.
    
    # 1. Base statistica (Volume FBRef diviso per divisore Mixer)
    base_lambda_h = vol_h / S["DIVISORE_MEDIA_GOL"]
    base_lambda_a = vol_a / S["DIVISORE_MEDIA_GOL"]
    
    # 2. Lucifero (SHARED - Lato Gol)
    # Una squadra in forma (Lucifero alto) è più cinica e precisa.
    form_factor_h = 1 + ((h_luc - 12.5) / 35.0) 
    form_factor_a = 1 + ((a_luc - 12.5) / 35.0)
    
    # 3. H2H Storico (SHARED - Lato Gol)
    hist_factor_h = max(0.85, min(1.15, h_h2h_g / 1.3)) 
    hist_factor_a = max(0.85, min(1.15, a_h2h_g / 1.1))
    
    # 4. Fattore Tattico (Puro tecnico: Attacco vs Difesa)
    tactical_h = (h_att / 7.5) * (1 + (5.0 - a_def)/S["IMPATTO_DIFESA_TATTICA"]) 
    tactical_a = (a_att / 7.5) * (1 + (5.0 - h_def)/S["IMPATTO_DIFESA_TATTICA"])
    
    # 5. Calcolo RAW (Aspettativa Gol Pura)
    raw_lambda_h = base_lambda_h * tactical_h * form_factor_h * hist_factor_h
    raw_lambda_a = base_lambda_a * tactical_a * form_factor_a * hist_factor_a


    # --- D. FUSIONE MOTORI (SINTESI) ---
    # Il "Chi vince" (Win Shift) piega il "Quanti gol" (Raw Lambda).
    
    final_lambda_h = raw_lambda_h * (1 + win_shift)
    final_lambda_a = raw_lambda_a * (1 - win_shift)
    
    # Safety Cap (Limiti fisici del calcio)
    # Minimo 0.15 gol attesi (mai zero assoluto), Massimo da Mixer
    final_lambda_h = max(0.15, min(S["TETTO_MAX_GOL_ATTESI"], final_lambda_h))
    final_lambda_a = max(0.15, min(S["TETTO_MAX_GOL_ATTESI"], final_lambda_a))
    
    
    # --- E. GENERAZIONE RISULTATO (POISSON) ---
    # Simulazione Monte Carlo basata sulle aspettative finali
    gh = np.random.poisson(final_lambda_h)
    ga = np.random.poisson(final_lambda_a)
    
    # Stringa di debug per vedere i valori calcolati (xG previsti)
    xg_info = f"{final_lambda_h:.2f}-{final_lambda_a:.2f}"
    
    # 📊 RACCOLTA DATI PER STATISTICHE MONTE CARLO
    # Funzione per estrarre il "peso logico" in sicurezza
    def extract_weight_info(w_calculated, peso_key, base_weight):
        """
        Estrae informazioni complete sul peso:
        - weight_base: Il peso teorico (0.20, 0.05, ecc.)
        - multiplier: Il moltiplicatore dal tuning
        - weight_final: Il peso reale applicato
        - is_disabled: Se il peso è disattivato (moltiplicatore = 0)
        """
        multiplier = S.get(peso_key, 1.0)
        
        return {
            'weight_base': base_weight,           # Es. 0.20
            'multiplier': multiplier,             # Es. 3.0 o 0.0
            'weight_final': w_calculated,         # Es. 0.60 o 0.00
            'is_disabled': (multiplier == 0.0)    # True se disattivato
        }
    
    # Raccogli informazioni complete per ogni peso
    pesi_dettagliati = {
        'Rating Rosa': extract_weight_info(W_RAT, "PESO_RATING_ROSA", 0.20),
        'Tecnica': extract_weight_info(W_TEC, "PESO_TECNICA", 0.15),
        'BVS Quote': extract_weight_info(W_BVS, "PESO_BVS_QUOTE", 0.15),
        'Forma Recente': extract_weight_info(W_LUC, "PESO_FORMA_RECENTE", 0.15),
        'Storia H2H': extract_weight_info(W_H2H, "PESO_STORIA_H2H", 0.10),
        'Motivazione': extract_weight_info(W_MOT, "PESO_MOTIVAZIONE", 0.10),
        'Fattore Campo': extract_weight_info(W_FLD, "PESO_FATTORE_CAMPO", 0.05),
        'Valore Rosa Extra': extract_weight_info(W_ROS, "PESO_ROSA_EXTRA", 0.05),
        'Affidabilità': extract_weight_info(W_AFF, "PESO_AFFIDABILITA", 0.05),
    }
    
    # Parametri (non hanno peso base/moltiplicatore, sono valori diretti)
    parametri = {
        'Divisore Media': S.get("DIVISORE_MEDIA_GOL", 2.0),
        'Impatto Difesa': S.get("IMPATTO_DIFESA_TATTICA", 15.0),
        'WinShift Power': S.get("POTENZA_FAVORITA_WINSHIFT", 0.40),
        'Tetto Max Gol': S.get("TETTO_MAX_GOL_ATTESI", 3.8)
    }
    
    # 🧾 SCONTRINI (rimangono uguali)
    scontrino_casa = {
        'Rating': {'valore': h_rat, 'peso': W_RAT, 'punti': h_rat * W_RAT},
        'Tecnica': {'valore': h_tec, 'peso': W_TEC, 'punti': h_tec * W_TEC},
        'BVS Quote': {'valore': h_bvs, 'peso': W_BVS, 'punti': h_bvs * W_BVS},
        'Forma': {'valore': h_luc, 'peso': W_LUC, 'punti': h_luc * W_LUC},
        'Storia H2H': {'valore': h_h2h_win, 'peso': W_H2H, 'punti': h_h2h_win * W_H2H},
        'Motivazione': {'valore': h_mot, 'peso': W_MOT, 'punti': h_mot * W_MOT},
        'Fattore Campo': {'valore': h_fld, 'peso': W_FLD, 'punti': h_fld * W_FLD},
        'Valore Rosa': {'valore': h_rosa, 'peso': W_ROS, 'punti': h_rosa * W_ROS},
        'Affidabilità': {'valore': h_rel, 'peso': W_AFF, 'punti': h_rel * W_AFF}
    }
    
    scontrino_ospite = {
        'Rating': {'valore': a_rat, 'peso': W_RAT, 'punti': a_rat * W_RAT},
        'Tecnica': {'valore': a_tec, 'peso': W_TEC, 'punti': a_tec * W_TEC},
        'BVS Quote': {'valore': a_bvs, 'peso': W_BVS, 'punti': a_bvs * W_BVS},
        'Forma': {'valore': a_luc, 'peso': W_LUC, 'punti': a_luc * W_LUC},
        'Storia H2H': {'valore': a_h2h_win, 'peso': W_H2H, 'punti': a_h2h_win * W_H2H},
        'Motivazione': {'valore': a_mot, 'peso': W_MOT, 'punti': a_mot * W_MOT},
        'Fattore Campo': {'valore': a_fld, 'peso': W_FLD, 'punti': a_fld * W_FLD},
        'Valore Rosa': {'valore': a_rosa, 'peso': W_ROS, 'punti': a_rosa * W_ROS},
        'Affidabilità': {'valore': a_rel, 'peso': W_AFF, 'punti': a_rel * W_AFF}
    }
    
    # RETURN con dati completi
    return gh, ga, final_lambda_h, final_lambda_a, xg_info, pesi_dettagliati, parametri, scontrino_casa, scontrino_ospite
