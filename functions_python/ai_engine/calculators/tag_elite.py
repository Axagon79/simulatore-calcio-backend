"""
Step Elite — Tagga i pronostici unified del giorno che matchano i pattern storicamente vincenti.
Gira subito dopo orchestrate_experts.py (step 31).
Aggiunge: elite (bool), elite_patterns (produzione), elite_patterns_trial (in prova).
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
MONGO_URI = os.getenv('MONGO_URI')
if not MONGO_URI:
    print("ERRORE: MONGO_URI non trovata")
    sys.exit(1)

client = MongoClient(MONGO_URI)
db = client['football_simulator_db']
coll = db['daily_predictions_unified']

# Date da processare: oggi + prossimi 6 giorni (pronostici anticipati)
today = datetime.now()
dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]


def get_matched_patterns(p):
    """Restituisce la lista di pattern ID che il pronostico matcha."""
    tipo = p.get('tipo', '')
    quota = p.get('quota', 0) or 0
    confidence = p.get('confidence', 0) or 0
    stars = p.get('stars', 0) or 0
    source = p.get('source', '')
    pronostico = p.get('pronostico', '')
    routing = p.get('routing_rule', '')

    # NO BET esclusi
    if pronostico == 'NO BET':
        return []

    matched = []

    # === PATTERN IN PRODUZIONE (P1-P16) ===

    if tipo == 'SEGNO' and 1.50 <= quota < 1.80 and 3.0 <= stars < 3.5:
        matched.append('P1')
    if tipo == 'SEGNO' and 1.50 <= quota < 1.80 and 50 <= confidence < 60:
        matched.append('P2')
    if tipo == 'DOPPIA_CHANCE' and source == 'C_screm' and 2.00 <= quota < 2.50:
        matched.append('P3')
    if tipo == 'GOL' and 1.30 <= quota < 1.50 and 70 <= confidence < 80:
        matched.append('P4')
    if tipo == 'DOPPIA_CHANCE' and 2.00 <= quota < 2.50:
        matched.append('P5')
    if tipo == 'SEGNO' and confidence >= 80:
        matched.append('P6')
    if tipo == 'DOPPIA_CHANCE' and 1.30 <= quota < 1.50 and 60 <= confidence < 70:
        matched.append('P7')
    if tipo == 'GOL' and source == 'A+S' and 1.30 <= quota < 1.50:
        matched.append('P8')
    if tipo == 'DOPPIA_CHANCE' and 1.40 <= quota < 1.50 and confidence >= 60:
        matched.append('P9')
    if 'MG 2-4' in pronostico or 'Multigol 2-4' in pronostico:
        matched.append('P10')
    if tipo == 'GOL' and 1.30 <= quota < 1.40 and confidence >= 70:
        matched.append('P11')
    if tipo == 'DOPPIA_CHANCE' and 1.40 <= quota < 1.50 and stars >= 3.0:
        matched.append('P12')
    if tipo == 'GOL' and 1.30 <= quota < 1.40 and source == 'A+S':
        matched.append('P13')
    if tipo == 'GOL' and 1.50 <= quota < 1.60 and source == 'C_screm':
        matched.append('P14')
    if tipo == 'SEGNO' and 1.80 <= quota < 2.00 and confidence >= 80:
        matched.append('P15')
    if tipo == 'DOPPIA_CHANCE' and 1.30 <= quota < 1.50 and 70 <= confidence < 80:
        matched.append('P16')

    # === PATTERN IN PROVA (P17-P18) — Aggiunti 11/04/2026 ===

    if pronostico == '1' and 1.60 <= quota < 1.80 and routing == 'single' and stars >= 3.0 and source != 'C':
        matched.append('P17')
    if tipo == 'SEGNO' and 1.60 <= quota < 1.80 and source == 'C' and stars >= 3.0:
        matched.append('P18')

    # Rimuovi pattern meno specifici quando uno più specifico li copre
    return _remove_subsets(matched)


# Numero di condizioni per pattern (per risolvere sovrapposizioni)
PATTERN_CONDITIONS = {
    'P1': 3,   # tipo + quota + stelle
    'P2': 3,   # tipo + quota + confidence
    'P3': 3,   # tipo + source + quota
    'P4': 3,   # tipo + quota + confidence
    'P5': 2,   # tipo + quota
    'P6': 2,   # tipo + confidence
    'P7': 3,   # tipo + quota + confidence
    'P8': 3,   # tipo + source + quota
    'P9': 3,   # tipo + quota + confidence
    'P10': 1,  # pronostico
    'P11': 3,  # tipo + quota + confidence
    'P12': 3,  # tipo + quota + stelle
    'P13': 3,  # tipo + quota + source
    'P14': 3,  # tipo + quota + source
    'P15': 3,  # tipo + quota + confidence
    'P16': 3,  # tipo + quota + confidence
    'P17': 4,  # pronostico + quota + routing + stelle (+ source != C)
    'P18': 4,  # tipo + quota + source + stelle
}

# Quali pattern sono "contenuti" in altri (il meno specifico è coperto dal più specifico)
# Chiave = pattern generico, Valore = lista di pattern più specifici che lo coprono
SUBSET_MAP = {
    'P5': ['P3', 'P7', 'P9', 'P12', 'P16'],   # DC + quota → coperto da DC + quota + altro
    'P6': ['P1', 'P2', 'P15', 'P17', 'P18'],   # SEGNO + conf → coperto da SEGNO + conf + altro
    'P4': ['P8', 'P11', 'P13'],                  # GOL + quota + conf → coperto da chi ha source o quota stretta
    'P11': ['P13'],                               # GOL + quota stretta + conf → coperto da chi ha source
    'P2': ['P1'],                                 # SEGNO + quota + conf → coperto da SEGNO + quota + stelle
    'P1': ['P18'],                                # SEGNO 3 cond → coperto da SEGNO 4 cond con source
    'P8': ['P13'],                                # GOL + A+S + quota larga → coperto da quota stretta
    'P9': ['P16'],                                # DC + quota stretta + conf generica → coperto da conf più stretta
    'P7': ['P9'],                                 # DC + quota + conf 60-69 → coperto da DC + quota stretta + conf ≥60
    'P12': ['P9'],                                # DC + quota + stelle → coperto da DC + quota + conf (stessa fascia)
}


def _remove_subsets(matched):
    """Rimuove pattern meno specifici quando uno più specifico è presente."""
    if len(matched) <= 1:
        return matched
    matched_set = set(matched)
    to_remove = set()
    for generic, specifics in SUBSET_MAP.items():
        if generic in matched_set:
            for specific in specifics:
                if specific in matched_set:
                    to_remove.add(generic)
                    break
    return [p for p in matched if p not in to_remove]


# Pattern in produzione vs in prova
PATTERNS_PRODUZIONE = {'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8',
                       'P9', 'P10', 'P11', 'P12', 'P13', 'P14', 'P15', 'P16'}
PATTERNS_PROVA = {'P17', 'P18'}


def main():
    print(f"=== TAG ELITE — {today.strftime('%Y-%m-%d %H:%M')} ===")
    print(f"Date da processare: {dates}")

    total_tagged = 0
    total_matches = 0

    for date in dates:
        docs = list(coll.find({"date": date}, {"_id": 1, "home": 1, "away": 1, "pronostici": 1}))
        if not docs:
            continue

        for doc in docs:
            pronostici = doc.get('pronostici', [])
            changed = False

            for p in pronostici:
                matched = get_matched_patterns(p)
                is_elite = len(matched) > 0
                old_elite = p.get('elite', False)
                old_prod = p.get('elite_patterns', [])
                old_trial = p.get('elite_patterns_trial', [])

                p['elite'] = is_elite
                prod = sorted([m for m in matched if m in PATTERNS_PRODUZIONE])
                trial = sorted([m for m in matched if m in PATTERNS_PROVA])
                p['elite_patterns'] = prod
                p['elite_patterns_trial'] = trial

                if is_elite != old_elite or prod != old_prod or trial != old_trial:
                    changed = True
                if is_elite:
                    total_tagged += 1

            if changed:
                coll.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"pronostici": pronostici}}
                )
                total_matches += 1

        date_elite = sum(
            1 for d in docs
            for p in d.get('pronostici', [])
            if len(get_matched_patterns(p)) > 0
        )
        print(f"  {date}: {len(docs)} partite, {date_elite} pronostici elite")

    print(f"\nTotale: {total_tagged} pronostici elite in {total_matches} partite aggiornate")
    client.close()


if __name__ == '__main__':
    main()
