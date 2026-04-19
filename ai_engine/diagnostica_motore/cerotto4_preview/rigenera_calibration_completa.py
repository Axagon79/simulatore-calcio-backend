"""Rigenera calibration_table usando il criterio backend completo.

Differenze dal `refresh_calibration_table.py`:
- Accetta pronostici con `esito` non-None anche se `profit_loss` è None
  (50 casi edge dove il PL non è stato ancora calcolato ma l'esito è noto).
- Tutto il resto identico.

Output: sovrascrive `calibration_table._id='current'`.

Nota: questo script è una tantum per allineare la tabella attualmente in
produzione. Lo step 29.3 nightly continuerà a usare `refresh_calibration_table.py`
(criterio più stretto). Se vogliamo, in futuro allineiamo anche quello.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError('Impossibile trovare config.py')
    current_path = parent
sys.path.insert(0, current_path)
fp_path = os.path.join(current_path, 'functions_python')
if fp_path not in sys.path:
    sys.path.insert(0, fp_path)

from config import db
from ai_engine.source_classify import classify as classify_source
from ai_engine.stake_kelly import BINS, BIN_LABELS, VALID_MERCATI


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
    print('[calibration-complete] criterio backend (no dedup, solo esito not None)')

    cells_counts = {}
    fb_counts = {}
    total = 0
    date_min = None
    date_max = None

    for doc in db['daily_predictions_unified'].find({},
        {'date': 1, 'pronostici.tipo': 1, 'pronostici.pronostico': 1,
         'pronostici.source': 1, 'pronostici.probabilita_stimata': 1,
         'pronostici.esito': 1}):
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
            if p.get('esito') is None:
                continue
            prob = p.get('probabilita_stimata')
            if prob is None:
                continue
            bin_lab = _bin_label(prob)
            if bin_lab is None:
                continue
            grp = classify_source(p.get('source'))
            hit = 1 if bool(p.get('esito')) else 0
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

    print(f'[calibration-complete] pronostici validi: {total}')
    print(f'[calibration-complete] celle uniche: {len(cells_counts)}')
    print(f'[calibration-complete] fallback mkt×bin: {len(fb_counts)}')

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
        'finestra': {'from': date_min, 'to': date_max},
        'bins': BINS,
        'bin_labels': BIN_LABELS,
        'cells': cells,
        'fallback_mercato_bin': fallback_mercato_bin,
        'metodo': 'backend_esito_not_none',
    }

    db['calibration_table'].replace_one({'_id': 'current'}, doc_out, upsert=True)
    print(f"[calibration-complete] salvato in MongoDB. n_totale={total}, "
          f"finestra {date_min} → {date_max}")


if __name__ == '__main__':
    main()
