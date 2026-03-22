"""
Step Elite — Tagga i pronostici unified del giorno che matchano i pattern storicamente vincenti.
Gira subito dopo orchestrate_experts.py (step 31).
Aggiunge elite: true ai pronostici che soddisfano almeno uno dei 16 pattern.
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


def matches_elite(p):
    """Controlla se un pronostico matcha uno dei 16 pattern elite."""
    tipo = p.get('tipo', '')
    quota = p.get('quota', 0) or 0
    confidence = p.get('confidence', 0) or 0
    stars = p.get('stars', 0) or 0
    source = p.get('source', '')
    pronostico = p.get('pronostico', '')

    # NO BET esclusi
    if pronostico == 'NO BET':
        return False

    # === PATTERN ORIGINALI (1-8) ===

    # Pattern 1: SEGNO + quota 1.50-1.79 + stelle 3.0-3.5
    if tipo == 'SEGNO' and 1.50 <= quota < 1.80 and 3.0 <= stars < 3.5:
        return True

    # Pattern 2: SEGNO + quota 1.50-1.79 + confidence 50-59
    if tipo == 'SEGNO' and 1.50 <= quota < 1.80 and 50 <= confidence < 60:
        return True

    # Pattern 3: DOPPIA_CHANCE + source C_screm + quota 2.00-2.49
    if tipo == 'DOPPIA_CHANCE' and source == 'C_screm' and 2.00 <= quota < 2.50:
        return True

    # Pattern 4: GOL + quota 1.30-1.49 + confidence 70-79
    if tipo == 'GOL' and 1.30 <= quota < 1.50 and 70 <= confidence < 80:
        return True

    # Pattern 5: DOPPIA_CHANCE + quota 2.00-2.49
    if tipo == 'DOPPIA_CHANCE' and 2.00 <= quota < 2.50:
        return True

    # Pattern 6: SEGNO + confidence >= 80
    if tipo == 'SEGNO' and confidence >= 80:
        return True

    # Pattern 7: DOPPIA_CHANCE + source C_combo96 + quota 1.30-1.49
    if tipo == 'DOPPIA_CHANCE' and source == 'C_combo96' and 1.30 <= quota < 1.50:
        return True

    # Pattern 8: GOL + source A+S + quota 1.30-1.49
    if tipo == 'GOL' and source == 'A+S' and 1.30 <= quota < 1.50:
        return True

    # === NUOVI PATTERN (9-16) — Scoperti 22/03/2026 ===

    # Pattern 9: DOPPIA_CHANCE + quota 1.40-1.49 + confidence >= 60 (92.6%, N=27)
    if tipo == 'DOPPIA_CHANCE' and 1.40 <= quota < 1.50 and confidence >= 60:
        return True

    # Pattern 10: Multigol 2-4 (88.2%, N=17)
    if 'MG 2-4' in pronostico or 'Multigol 2-4' in pronostico:
        return True

    # Pattern 11: GOL + quota 1.30-1.39 + confidence >= 70 (86.4%, N=22)
    if tipo == 'GOL' and 1.30 <= quota < 1.40 and confidence >= 70:
        return True

    # Pattern 12: DOPPIA_CHANCE + quota 1.40-1.49 + stelle >= 3.0 (85.3%, N=34)
    if tipo == 'DOPPIA_CHANCE' and 1.40 <= quota < 1.50 and stars >= 3.0:
        return True

    # Pattern 13: GOL + quota 1.30-1.39 + source A+S (85.2%, N=27)
    if tipo == 'GOL' and 1.30 <= quota < 1.40 and source == 'A+S':
        return True

    # Pattern 14: GOL + quota 1.50-1.59 + source C_screm (84.2%, N=19)
    if tipo == 'GOL' and 1.50 <= quota < 1.60 and source == 'C_screm':
        return True

    # Pattern 15: SEGNO + quota 1.80-1.99 + confidence >= 70 (83.3%, N=18)
    if tipo == 'SEGNO' and 1.80 <= quota < 2.00 and confidence >= 70:
        return True

    # Pattern 16: DOPPIA_CHANCE + quota 1.40-1.49 (81.2%, N=64)
    if tipo == 'DOPPIA_CHANCE' and 1.40 <= quota < 1.50:
        return True

    return False


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
                is_elite = matches_elite(p)
                old_elite = p.get('elite', False)
                p['elite'] = is_elite
                if is_elite != old_elite:
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
            if matches_elite(p)
        )
        print(f"  {date}: {len(docs)} partite, {date_elite} pronostici elite")

    print(f"\nTotale: {total_tagged} pronostici elite in {total_matches} partite aggiornate")
    client.close()


if __name__ == '__main__':
    main()
