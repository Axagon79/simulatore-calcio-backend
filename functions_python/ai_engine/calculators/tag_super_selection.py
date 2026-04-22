"""
Tag Super Selection — flagga i pronostici che hanno ALMENO 2 flag su 3 tra:
  - Alto Rendimento (quota >= soglia: DC>=2.00, altri>=2.51)
  - Elite (p.elite == True)
  - Mixer (p.mixer == True)

Gira DOPO tag_elite.py e tag_mixer.py nella pipeline.

Tagging retroattivo: processa ogni pronostico in daily_predictions_unified
nella finestra (oggi → oggi+6 giorni) e scrive:
  - p.super_selection: bool

Finestra: 7 giorni (oggi + 6 futuri), coerente con orchestrate_experts.

Filosofia: pronostico che ha superato >=2 filtri di qualita' indipendenti
(quota-based + pattern Elite + pattern Mixer) e' statisticamente superiore.
Backtest 15/03-20/04: HR 62.2%, ROI +16.82%, PL +277.52u su 254 pronostici.
"""

import os
import sys
import argparse
from datetime import datetime, timedelta


def _is_alto_rendimento(p):
    """Restituisce True se il pronostico rientra in Alto Rendimento per quota."""
    tipo = p.get('tipo', '')
    quota = p.get('quota', 0) or 0
    try:
        q = float(quota)
    except (TypeError, ValueError):
        return False
    if q <= 0:
        return False
    if tipo == 'RISULTATO_ESATTO':
        return True
    soglia = 2.00 if tipo == 'DOPPIA_CHANCE' else 2.51
    return q >= soglia


def is_super_selection(p):
    """True se il pronostico ha almeno 2 flag su 3 (AR + Elite + Mixer)."""
    if p.get('pronostico') == 'NO BET':
        return False
    is_ar = _is_alto_rendimento(p)
    is_elite = p.get('elite') is True
    is_mixer = p.get('mixer') is True
    return (int(is_ar) + int(is_elite) + int(is_mixer)) >= 2


def _build_dates(from_date, to_date):
    """Genera lista di date YYYY-MM-DD tra from_date e to_date (inclusi)."""
    start = datetime.strptime(from_date, '%Y-%m-%d')
    end = datetime.strptime(to_date, '%Y-%m-%d')
    if end < start:
        return []
    dates = []
    d = start
    while d <= end:
        dates.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)
    return dates


def main():
    from dotenv import load_dotenv
    from pymongo import MongoClient

    parser = argparse.ArgumentParser(description='Tag Super Selection')
    parser.add_argument('--from', dest='date_from', default=None,
                        help='Data inizio YYYY-MM-DD (opzionale). Se assente: oggi.')
    parser.add_argument('--to', dest='date_to', default=None,
                        help='Data fine YYYY-MM-DD (opzionale). Se assente: oggi+6 giorni.')
    args = parser.parse_args()

    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    MONGO_URI = os.getenv('MONGO_URI')
    if not MONGO_URI:
        print("ERRORE: MONGO_URI non trovata")
        sys.exit(1)

    client = MongoClient(MONGO_URI)
    db = client['football_simulator_db']
    coll = db['daily_predictions_unified']

    today = datetime.now()
    if args.date_from or args.date_to:
        date_from = args.date_from or today.strftime('%Y-%m-%d')
        date_to = args.date_to or (today + timedelta(days=6)).strftime('%Y-%m-%d')
        dates = _build_dates(date_from, date_to)
        mode = f'custom range {date_from} -> {date_to}'
    else:
        dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
        mode = 'default (oggi + 6 giorni)'

    print(f"=== TAG SUPER SELECTION — {today.strftime('%Y-%m-%d %H:%M')} ===")
    print(f"Modo: {mode}")
    print(f"Date da processare: {len(dates)} giorni (da {dates[0]} a {dates[-1]})" if dates else "Nessuna data")
    print("Criterio: >=2 flag su 3 tra (Alto Rendimento, Elite, Mixer)")

    total_tagged = 0
    total_matches = 0

    for date in dates:
        docs = list(coll.find({"date": date}, {"_id": 1, "home": 1, "away": 1, "pronostici": 1}))
        if not docs:
            continue

        date_tagged = 0
        for doc in docs:
            pronostici = doc.get('pronostici', [])
            changed = False

            for p in pronostici:
                new_val = is_super_selection(p)
                old_val = p.get('super_selection', False)

                p['super_selection'] = new_val

                if new_val != old_val:
                    changed = True
                if new_val:
                    total_tagged += 1
                    date_tagged += 1

            if changed:
                coll.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"pronostici": pronostici}}
                )
                total_matches += 1

        print(f"  {date}: {len(docs)} partite, {date_tagged} pronostici super_selection")

    print(f"\nTotale: {total_tagged} pronostici super_selection in {total_matches} partite aggiornate")
    client.close()


if __name__ == '__main__':
    main()
