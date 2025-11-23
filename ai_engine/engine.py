import os
import random
from pymongo import MongoClient
from dotenv import load_dotenv

# --- SETUP ---
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'functions', '.env')
load_dotenv(dotenv_path)
mongo_uri = os.getenv('MONGO_URI')

# --- PESI ALGORITMO v3.0 (Configurazione Serie A) ---
WEIGHTS = {
    "LUCIFERO": 0.13,      # Forma ponderata
    "COEFF_GOL": 0.13,     # Attacco/Difesa
    "BVS": 0.12,           # Base Variante Sorpresa (Quote)
    "CAMPO": 0.11,         # Fattore Campo
    "AFFIDABILITA": 0.11,  # Rispetto pronostici storici
    "MOTIVAZIONE": 0.10,   # Classifica/Obiettivi
    "VALORE_ROSA": 0.09,   # Transfermarkt
    "H2H": 0.08,           # Scontri diretti
    "INFORTUNI": 0.07,     # Assenze pesanti
    "QUOTE_MOV": 0.06,     # Movimenti di mercato
    "DROPPING": 0.04,      # Crolli improvvisi quota
    "FORMA_BREVE": 0.02,   # Trend ultime partite
    "STRISCE": 0.02,       # Serie vittorie/sconfitte
    "ALTRI": 0.02          # Meteo, Viaggi
}

CASUALITA_BASE = 0.15 # 15% di imprevisto

def calculate_v3_prediction(match, home, away):
    print(f"\n⚙️  AVVIO ALGORITMO v3.0: {home['name']} vs {away['name']}")
    print("-" * 50)

    # Partiamo da un equilibrio perfetto (33-33-33) e spostiamo l'ago della bilancia
    # Usiamo un punteggio "Strength" relativo. 0 = Equilibrio. 
    # >0 = Vantaggio Casa, <0 = Vantaggio Trasferta.
    balance_score = 0 

    # 1. LUCIFERO (13%)
    # Confrontiamo i punteggi forma (0-100)
    score_h = home.get('form', {}).get('score', 50)
    score_a = away.get('form', {}).get('score', 50)
    diff_lucifero = (score_h - score_a) / 100 # Normalizzato tra -1 e 1
    impact_lucifero = diff_lucifero * WEIGHTS["LUCIFERO"]
    balance_score += impact_lucifero
    print(f"   🔥 Lucifero ({score_h} vs {score_a}): Impatto {impact_lucifero:+.4f}")

    # 2. VALORE ROSA (9%)
    val_h = home.get('marketValue', 1)
    val_a = away.get('marketValue', 1)
    # Formula v3.0: Differenza percentuale cappata al 35%
    diff_value = (val_h - val_a) / val_a
    diff_value = max(min(diff_value, 0.35), -0.35) # Cap +/- 35%
    impact_value = diff_value * WEIGHTS["VALORE_ROSA"]
    balance_score += impact_value
    print(f"   💰 Valore Rosa ({val_h}M vs {val_a}M): Impatto {impact_value:+.4f}")

    # 3. FATTORE CAMPO (11%)
    # Bonus fisso per chi gioca in casa
    impact_field = 0.5 * WEIGHTS["CAMPO"] # Un boost medio
    balance_score += impact_field
    print(f"   🏟️  Fattore Campo: Impatto {impact_field:+.4f}")

    # 4. COEFFICIENTI GOL (13%)
    # Potenziale attacco casa vs difesa ospite
    att_h = home.get('stats', {}).get('goalsScoredHome', 1)
    def_a = away.get('stats', {}).get('goalsConcededAway', 1)
    # Semplificazione logica per il test
    goal_power_h = att_h * def_a
    goal_power_a = away.get('stats', {}).get('goalsScoredAway', 1) * home.get('stats', {}).get('goalsConcededHome', 1)
    diff_goals = (goal_power_h - goal_power_a) / 5 # Normalizzazione empirica
    impact_goals = diff_goals * WEIGHTS["COEFF_GOL"]
    balance_score += impact_goals
    print(f"   ⚽ Coefficienti Gol: Impatto {impact_goals:+.4f}")

    # 5. BVS - BASE VARIANTE SORPRESA (12%)
    # Analisi quote
    odds = match.get('odds', {})
    odd_1 = odds.get('one', 3.0)
    odd_2 = odds.get('two', 3.0)
    # Se la quota 1 è molto più bassa della 2, vantaggio casa
    diff_odds = 0
    if odd_1 < odd_2:
        diff_odds = 0.5 # Vantaggio teorico casa
    elif odd_2 < odd_1:
        diff_odds = -0.5 # Vantaggio teorico trasferta
    
    impact_bvs = diff_odds * WEIGHTS["BVS"]
    balance_score += impact_bvs
    print(f"   📊 BVS (Quote {odd_1} vs {odd_2}): Impatto {impact_bvs:+.4f}")

    print("-" * 50)

    # --- CALCOLO PROBABILITÀ FINALI ---
    # Convertiamo il balance_score in percentuali
    # Base: 34% - 32% - 34%
    base_home = 34.0
    base_draw = 32.0
    base_away = 34.0

    # Lo score sposta punti percentuali (moltiplicatore x100 per leggibilità)
    shift = balance_score * 100 

    prob_home = base_home + shift
    prob_away = base_away - shift
    
    # Il pareggio soffre leggermente se c'è una squadra molto favorita
    if abs(shift) > 15:
        base_draw -= 5
        prob_home += 2.5
        prob_away += 2.5

    # Normalizzazione a 100%
    total = prob_home + base_draw + prob_away
    final_home = (prob_home / total) * 100
    final_draw = (base_draw / total) * 100
    final_away = (prob_away / total) * 100

    return {"1": final_home, "X": final_draw, "2": final_away}

def simulate_match_event(probs):
    """
    Applica la Casualità Dinamica e genera il risultato
    """
    print(f"\n🎲 Applicazione Casualità Dinamica (Base {CASUALITA_BASE*100}%)")
    
    # Estrazione casuale ponderata
    outcomes = ["1", "X", "2"]
    weights = [probs["1"], probs["X"], probs["2"]]
    
    # Python random.choices fa il lavoro sporco usando i nostri pesi
    result = random.choices(outcomes, weights=weights, k=1)[0]
    
    # Generazione punteggio realistico basato sul segno
    if result == "1":
        h_goals = random.randint(1, 4)
        a_goals = random.randint(0, h_goals - 1)
    elif result == "X":
        h_goals = random.randint(0, 3)
        a_goals = h_goals
    else: # Segno 2
        a_goals = random.randint(1, 4)
        h_goals = random.randint(0, a_goals - 1)

    return f"{h_goals} - {a_goals}", result


# --- ESECUZIONE ---
try:
    client = MongoClient(mongo_uri)
    db = client.get_database()
    
    match = db.matches.find_one({"status": "SCHEDULED"})
    if not match:
        print("❌ Nessuna partita in programma.")
        exit()

    home = db.teams.find_one({"_id": match["homeTeam"]})
    away = db.teams.find_one({"_id": match["awayTeam"]})

    # 1. Calcola Probabilità
    probs = calculate_v3_prediction(match, home, away)
    
    print(f"\n📈 PRONOSTICO ALGORITMO:")
    print(f"   1 (Casa): {probs['1']:.1f}%")
    print(f"   X (Pari): {probs['X']:.1f}%")
    print(f"   2 (Ospiti): {probs['2']:.1f}%")

    # 2. Simula Partita
    score, sign = simulate_match_event(probs)
    
    print(f"\n⚽ RISULTATO FINALE SIMULATO:")
    print(f"   {home['name']}  {score}  {away['name']}")
    print(f"   Segno Vincente: {sign}")

except Exception as e:
    print(f"❌ Errore: {e}")
