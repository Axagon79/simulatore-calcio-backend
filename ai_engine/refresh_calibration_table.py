"""Rigenera la tabella di calibrazione per `kelly_unified`.

Letture: TUTTI i pronostici storici da `daily_predictions_unified` con
`profit_loss` valorizzato (quindi esito noto).

Calcolo per ogni (source_group, mercato, bin probabilita):
- n: numero di pronostici nella cella
- hr: hit rate reale (media di `esito` × 100)

+ fallback mercato×bin (cella con N aggregato su tutti i gruppi) per lo
shrinkage fatto lato client in `stake_kelly.py`.

Scrive il documento in `calibration_table._id='current'` (upsert).

Uso CLI:
    python ai_engine/refresh_calibration_table.py
    python ai_engine/refresh_calibration_table.py --from 2026-02-19

Step 29.3 della pipeline notturna lo invoca senza argomenti (finestra
completa = tutto lo storico disponibile).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

# Path setup: risale 1 livello (ai_engine → root).
# FUNCTIONS_PYTHON in cima fa risolvere `ai_engine` al package
# functions_python/ai_engine/ (dove vivono stake_kelly e source_classify).
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FUNCTIONS_PYTHON = os.path.join(PROJECT_ROOT, "functions_python")
if FUNCTIONS_PYTHON not in sys.path:
    sys.path.insert(0, FUNCTIONS_PYTHON)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config import db  # noqa: E402
from ai_engine.source_classify import classify as classify_source  # noqa: E402
from ai_engine.stake_kelly import BINS, BIN_LABELS, VALID_MERCATI  # noqa: E402


def _bin_label(p):
    if p is None:
        return None
    try:
        x = float(p)
    except (TypeError, ValueError):
        return None
    if x < BINS[0]:
        return BIN_LABELS[0]
    for i in range(len(BINS) - 1):
        if BINS[i] <= x < BINS[i + 1]:
            return BIN_LABELS[i]
    return BIN_LABELS[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--from', dest='date_from', default=None,
                        help='Data minima YYYY-MM-DD (opzionale, default = tutto)')
    parser.add_argument('--to', dest='date_to', default=None,
                        help='Data massima YYYY-MM-DD (opzionale, default = oggi)')
    args = parser.parse_args()

    q = {}
    if args.date_from or args.date_to:
        q['date'] = {}
        if args.date_from:
            q['date']['$gte'] = args.date_from
        if args.date_to:
            q['date']['$lte'] = args.date_to

    print(f"[calibration] query: {q or 'tutti gli storici'}")

    # --- Raccolta ---
    cells_counts = {}   # (gruppo, mercato, bin) -> [n, hits]
    fb_counts = {}      # (mercato, bin) -> [n, hits]
    total = 0
    date_min = None
    date_max = None

    for doc in db['daily_predictions_unified'].find(q,
        {'date': 1, 'pronostici.tipo': 1, 'pronostici.pronostico': 1,
         'pronostici.source': 1, 'pronostici.probabilita_stimata': 1,
         'pronostici.profit_loss': 1, 'pronostici.esito': 1}):
        d = doc.get('date')
        if d:
            if date_min is None or d < date_min:
                date_min = d
            if date_max is None or d > date_max:
                date_max = d
        for p in doc.get('pronostici') or []:
            mercato = p.get('tipo')
            if mercato not in VALID_MERCATI:
                continue
            if p.get('pronostico') == 'NO BET':
                continue
            # Criterio backend-compatible: basta `esito` noto (prima richiedeva
            # anche `profit_loss`, ora allineato a popola_pl_storico.py)
            if p.get('esito') is None:
                continue
            prob = p.get('probabilita_stimata')
            if prob is None:
                continue
            bin_lab = _bin_label(prob)
            if bin_lab is None:
                continue
            grp = classify_source(p.get('source'))
            esito = bool(p.get('esito'))
            hit = 1 if esito else 0

            key_c = (grp, mercato, bin_lab)
            if key_c not in cells_counts:
                cells_counts[key_c] = [0, 0]
            cells_counts[key_c][0] += 1
            cells_counts[key_c][1] += hit

            key_f = (mercato, bin_lab)
            if key_f not in fb_counts:
                fb_counts[key_f] = [0, 0]
            fb_counts[key_f][0] += 1
            fb_counts[key_f][1] += hit

            total += 1

    print(f"[calibration] pronostici validi processati: {total}")
    print(f"[calibration] celle uniche (grp x mkt x bin): {len(cells_counts)}")
    print(f"[calibration] fallback (mkt x bin): {len(fb_counts)}")

    # --- Costruzione documento ---
    cells = {}
    for (grp, mkt, lab), (n, hits) in cells_counts.items():
        hr = round(hits / n * 100, 2) if n > 0 else None
        cells[f"{grp}|{mkt}|{lab}"] = {'n': n, 'hr': hr, 'source': 'cell'}

    fallback_mercato_bin = {}
    for (mkt, lab), (n, hits) in fb_counts.items():
        hr = round(hits / n * 100, 2) if n > 0 else None
        fallback_mercato_bin[f"{mkt}|{lab}"] = {'n': n, 'hr': hr}

    doc_out = {
        '_id': 'current',
        'updated_at': datetime.now(timezone.utc),
        'n_totale': total,
        'finestra': {
            'from': date_min or args.date_from,
            'to': date_max or args.date_to,
        },
        'bins': BINS,
        'bin_labels': BIN_LABELS,
        'cells': cells,
        'fallback_mercato_bin': fallback_mercato_bin,
    }

    # --- Upsert ---
    db['calibration_table'].replace_one({'_id': 'current'}, doc_out, upsert=True)
    print(f"[calibration] salvato in MongoDB: "
          f"{len(cells)} celle + {len(fallback_mercato_bin)} fallback, "
          f"n_totale={total}, finestra={doc_out['finestra']['from']} -> {doc_out['finestra']['to']}")


if __name__ == '__main__':
    main()
