"""Kelly unificato per stake. Modulo condiviso da A, S, C.

Riferimento diagnostica: `ai_engine/diagnostica_motore/03_stake/report.md`.

Architettura:
- `get_calibrated_probability(source_group, mercato, prob_dichiarata)`
  restituisce la probabilita calibrata leggendo da MongoDB
  `calibration_table._id='current'`. Shrinkage con fallback a mercato×bin
  se N<30, fallback a `prob_dichiarata` se la cella e completamente assente.
- `compute_stake_kelly(prob_calibrata, quota, kelly_fraction=0.25)`
  implementa Kelly frazionario puro. Nessun cap, nessun fattore quota.
- `kelly_unified(prob_dichiarata, quota, source, mercato)`
  wrapper: classifica source, calibra prob, calcola stake. Ritorna dict
  con `stake` intero 0-10 e flag `low_value` quando edge <= 0.

Campi del documento calibration_table (creato da refresh_calibration_table.py):
{
  _id: "current",
  updated_at: datetime,
  n_totale: int,
  finestra: { from: "YYYY-MM-DD", to: "YYYY-MM-DD" },
  bins: [35, 50, 60, 70, 80, 101],    # breakpoints
  cells: {
    # key = f"{gruppo}|{mercato}|{bin_label}"
    "A|SEGNO|50-60": { "n": 53, "hr": 67.92, "source": "cell" },
    ...
  },
  fallback_mercato_bin: {
    # key = f"{mercato}|{bin_label}"
    "SEGNO|50-60": { "n": 93, "hr": 56.99 },
    ...
  }
}
"""
from __future__ import annotations

from typing import Optional

try:
    from .source_classify import classify as classify_source
except ImportError:  # quando importato come modulo top-level
    from source_classify import classify as classify_source


BINS = [35, 50, 60, 70, 80, 101]
BIN_LABELS = ['35-50', '50-60', '60-70', '70-80', '80+']
VALID_MERCATI = ('SEGNO', 'DOPPIA_CHANCE', 'GOL')

SHRINK_MIN_N = 30


def _bin_label(prob_pct: float) -> Optional[str]:
    """Restituisce l'etichetta del bin per una probabilita in [0, 100]."""
    if prob_pct is None:
        return None
    try:
        p = float(prob_pct)
    except (TypeError, ValueError):
        return None
    if p < BINS[0]:
        # sotto il minimo: usa il primo bin
        return BIN_LABELS[0]
    for i in range(len(BINS) - 1):
        if BINS[i] <= p < BINS[i + 1]:
            return BIN_LABELS[i]
    return BIN_LABELS[-1]


def _load_calibration_table(db) -> Optional[dict]:
    """Carica il documento corrente da MongoDB. None se assente."""
    if db is None:
        return None
    try:
        return db['calibration_table'].find_one({'_id': 'current'})
    except Exception:
        return None


# Cache in-process (invalida quando `updated_at` cambia)
_CAL_CACHE = {'doc': None, 'updated_at': None}


def _get_table(db) -> Optional[dict]:
    """Accesso cachato alla tabella. Invalida se `updated_at` cambia."""
    doc = _load_calibration_table(db)
    if doc is None:
        return None
    cached_ts = _CAL_CACHE.get('updated_at')
    doc_ts = doc.get('updated_at')
    if cached_ts is None or cached_ts != doc_ts:
        _CAL_CACHE['doc'] = doc
        _CAL_CACHE['updated_at'] = doc_ts
    return _CAL_CACHE['doc']


def get_calibrated_probability(
    db,
    source_group: str,
    mercato: str,
    prob_dichiarata: float,
) -> float:
    """Restituisce la probabilita calibrata (0-100) con shrinkage.

    Fallback in cascata:
    1. Cella (gruppo, mercato, bin) con N>=SHRINK_MIN_N → HR cella.
    2. Cella con N<SHRINK_MIN_N → shrink con mercato×bin.
    3. Cella mancante → mercato×bin.
    4. Mercato×bin mancante → prob_dichiarata (fallback sicuro).
    """
    if prob_dichiarata is None:
        return 0.0
    try:
        p_in = float(prob_dichiarata)
    except (TypeError, ValueError):
        return 0.0
    if p_in <= 0:
        return 0.0
    if mercato not in VALID_MERCATI:
        return p_in

    bin_lab = _bin_label(p_in)
    if bin_lab is None:
        return p_in

    table = _get_table(db)
    if not table:
        return p_in

    cells = table.get('cells') or {}
    fb_map = table.get('fallback_mercato_bin') or {}

    cell_key = f"{source_group}|{mercato}|{bin_lab}"
    fb_key = f"{mercato}|{bin_lab}"

    cell = cells.get(cell_key)
    fb = fb_map.get(fb_key)

    if cell is None:
        if fb is None:
            return p_in
        return float(fb.get('hr', p_in))

    n_cell = int(cell.get('n', 0))
    hr_cell = float(cell.get('hr', p_in))

    if n_cell >= SHRINK_MIN_N:
        return hr_cell

    if fb is None or fb.get('n', 0) == 0:
        return hr_cell

    hr_fb = float(fb.get('hr', p_in))
    w_cell = n_cell
    w_fb = SHRINK_MIN_N - n_cell
    denom = w_cell + w_fb
    if denom <= 0:
        return hr_cell
    return (hr_cell * w_cell + hr_fb * w_fb) / denom


def compute_stake_kelly(
    prob_calibrata_pct: float,
    quota: float,
    kelly_fraction: float = 0.25,
) -> dict:
    """Kelly frazionario puro.

    Ritorna dict {stake: int 1-10, low_value: bool, edge_pct: float}.
    Se edge <= 0 -> stake=1 con low_value=True (policy: niente NO BET
    automatico, lasciamo il pronostico visibile col badge).
    """
    try:
        p = float(prob_calibrata_pct) / 100.0
    except (TypeError, ValueError):
        return {'stake': 1, 'low_value': True, 'edge_pct': 0.0}
    try:
        q = float(quota)
    except (TypeError, ValueError):
        return {'stake': 1, 'low_value': True, 'edge_pct': 0.0}
    if q is None or q <= 1:
        return {'stake': 1, 'low_value': True, 'edge_pct': 0.0}

    edge = p * q - 1.0
    edge_pct = round(edge * 100, 2)

    if edge <= 0:
        return {'stake': 1, 'low_value': True, 'edge_pct': edge_pct}

    b = q - 1.0
    f = edge / b                   # frazione di bankroll "full Kelly"
    raw = kelly_fraction * f * 100 # scala 1-10 coerente con UI
    stake = int(max(1, min(10, round(raw))))
    return {'stake': stake, 'low_value': False, 'edge_pct': edge_pct}


def kelly_unified(
    db,
    prob_dichiarata_pct: float,
    quota: float,
    source: str,
    mercato: str,
    kelly_fraction: float = 0.25,
) -> dict:
    """Wrapper end-to-end. Classifica source, calibra, calcola stake.

    Ritorna dict:
    {
      'stake': int 1-10,
      'low_value': bool,
      'edge_pct': float,
      'prob_calibrata': float (0-100),
      'source_group': str,
    }
    """
    group = classify_source(source)
    p_cal = get_calibrated_probability(db, group, mercato, prob_dichiarata_pct)
    res = compute_stake_kelly(p_cal, quota, kelly_fraction)
    res['prob_calibrata'] = round(float(p_cal), 2)
    res['source_group'] = group
    return res


def invalidate_cache():
    """Forza il reload alla prossima chiamata. Utile nei test."""
    _CAL_CACHE['doc'] = None
    _CAL_CACHE['updated_at'] = None
