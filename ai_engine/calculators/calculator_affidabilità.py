import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

# CONFIGURAZIONE DB
DB_NAME = "pup_pals_db"
COLLECTION_HISTORY = "matches_history"
COLLECTION_TEAMS = "teams"

def connect_db():
    from config import db
    return db 

def get_team_aliases(db, team_name):
    """Cerca gli alias della squadra per trovarla nello storico anche se il nome è diverso."""
    team = db[COLLECTION_TEAMS].find_one({"name": team_name})
    aliases = [team_name]
    if team:
        # Aggiungi alias da oggetto o lista
        if isinstance(team.get('aliases'), list):
            aliases.extend(team['aliases'])
        elif isinstance(team.get('aliases'), dict):
            aliases.extend(team['aliases'].values())
    return [a.lower() for a in aliases] # Tutto minuscolo per confronti sicuri

def calculate_reliability(team_name):
    """
    Calcola l'indice di affidabilità (0-7) basandosi sullo storico quote.
    Logica:
    - Sei affidabile se vinci da favorita e perdi da sfavorita.
    - Sei inaffidabile se perdi da favorita (delusione) o vinci da sfavorita (sorpresa).
    """
    db = connect_db()
    history_col = db[COLLECTION_HISTORY]

    # 1. Trova tutte le partite della squadra (Casa o Fuori)
    # Usiamo una regex per cercare il nome o gli alias
    # Nota: Per performance vere servirebbe un mapping ID preciso, ma per ora cerchiamo per stringa

    aliases = get_team_aliases(db, team_name)
    regex_pattern = "|".join([f"^{a}$" for a in aliases]) # Match esatto su uno degli alias

    matches = list(history_col.find({
        "$or": [
            {"home_team": {"$regex": team_name, "$options": "i"}}, # Semplificazione: cerca nome principale
            {"away_team": {"$regex": team_name, "$options": "i"}}
        ]
    }))

    if not matches:
        return 5.0 # Valore neutro se nessuna partita trovata

    score = 5.0 # Partenza neutra
    match_count = 0

    for m in matches:
        is_home = m['home_team'].lower() in [a.lower() for a in aliases] or team_name.lower() in m['home_team'].lower()

        # Dati partita
        gh = m['home_goals']
        ga = m['away_goals']

        o1 = m.get('odds_1')
        o2 = m.get('odds_2')

        if not o1 or not o2: continue

        # Determina Risultato per la squadra
        if is_home:
            my_odds = o1
            won = gh > ga
            lost = gh < ga
            draw = gh == ga
        else:
            my_odds = o2
            won = ga > gh
            lost = ga < gh
            draw = gh == ga

        # --- LOGICA PUNTEGGIO ---

        # 1. SQUADRA FAVORITA (Quota < 2.00)
        if my_odds <= 2.00:
            if won:
                score += 0.8  # Affidabile: Ha vinto come previsto
            elif draw:
                score -= 0.5  # Delusione parziale
            elif lost:
                score -= 1.2  # Grave inaffidabilità: Ha perso da favorita

        # 2. SQUADRA SFAVORITA (Quota > 3.00)
        elif my_odds >= 3.00:
            if lost:
                score += 0.2  # Affidabile: Ha perso come previsto (triste ma affidabile)
            elif won:
                score -= 0.5  # Sorpresa: Inaffidabile per il pronostico (ha vinto contro pronostico)
            elif draw:
                score -= 0.3  # Sorpresa parziale

        # 3. PARTITA EQUILIBRATA (2.05 < Quota < 3.00)
        else:
            # Qui l'affidabilità conta meno, ma premia comunque la vittoria
            if won: score += 0.7   # 0.5 * 1.43
            if draw: score -= 0.70
            if lost: score -= 1.40

        match_count += 1

    # Normalizzazione e Cap (0 - 7)
    if score > 10: score = 10.0
    if score < 0: score = 0.0

    # Correzione per poche partite (Regressione verso la media)
    if match_count < 5:
        # Regressione proporzionale ai match
        weight = match_count / 5.0  # 0-1
        score = score * weight + 5.0 * (1 - weight)
    
# Esempio:
# 1 partita: score * 0.2 + 5.0 * 0.8 = più neutro
# 4 partite: score * 0.8 + 5.0 * 0.2 = quasi originale

    return round(score, 2)

# TEST RAPIDO
if __name__ == "__main__":
    t_name = "Inter" # Cambia con una squadra presente
    print(f"--- Calcolo Affidabilità per {t_name} ---")
    val = calculate_reliability(t_name)
    print(f"Affidabilità: {val} / 7.0")