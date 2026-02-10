"""
Genera report Track Record completo (JSON + TXT) da tutti i pronostici storici.
Confronta daily_predictions con risultati reali in h2h_by_round.
Salva in log/track-record-report.json e log/track-record-report.txt
"""
import os, sys, json, re
from datetime import datetime
from collections import defaultdict

# --- LOGGING: output su terminale + file log ---
class _TeeOutput:
    def __init__(self, log_path):
        self.terminal = sys.stdout
        self.log = open(log_path, 'w', encoding='utf-8')
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
    def flush(self):
        self.terminal.flush()
        self.log.flush()

_log_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_log_root, 'log')):
    _p = os.path.dirname(_log_root)
    if _p == _log_root:
        break
    _log_root = _p

LOG_DIR = os.path.join(_log_root, 'log')
sys.stdout = _TeeOutput(os.path.join(LOG_DIR, 'track-record-generazione.txt'))
sys.stderr = sys.stdout
print(f"{'='*60}")
print(f"GENERAZIONE REPORT TRACK RECORD: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
print(f"{'='*60}\n")

# --- CONNESSIONE MONGODB ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# ==============================================================================
# FUNZIONI HELPER
# ==============================================================================

def parse_score(real_score):
    """Parsa '2:1' o '2-1' in componenti."""
    if not real_score:
        return None
    parts = re.split(r'[:\-]', str(real_score).strip())
    if len(parts) != 2:
        return None
    try:
        h, a = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    total = h + a
    if h > a:
        sign = '1'
    elif h == a:
        sign = 'X'
    else:
        sign = '2'
    btts = h > 0 and a > 0
    return {'home': h, 'away': a, 'total': total, 'sign': sign, 'btts': btts}


def check_pronostico(pronostico, tipo, parsed):
    """Verifica se un pronostico e' corretto."""
    if not parsed or not pronostico:
        return None
    p = pronostico.strip()

    if tipo == 'SEGNO':
        return parsed['sign'] == p

    if tipo == 'DOPPIA_CHANCE':
        if p == '1X':
            return parsed['sign'] in ('1', 'X')
        if p == 'X2':
            return parsed['sign'] in ('X', '2')
        if p == '12':
            return parsed['sign'] in ('1', '2')
        return None

    if tipo == 'GOL':
        # Over/Under
        m = re.match(r'(Over|Under)\s+([\d.]+)', p, re.IGNORECASE)
        if m:
            direction = m.group(1).lower()
            threshold = float(m.group(2))
            if direction == 'over':
                return parsed['total'] > threshold
            else:
                return parsed['total'] < threshold
        # Goal / NoGoal
        if p.lower() == 'goal':
            return parsed['btts']
        if p.lower() == 'nogoal':
            return not parsed['btts']

    return None


def get_quota_for_pronostico(pronostico, tipo, odds):
    """Estrae la quota rilevante dall'oggetto odds."""
    if not odds or not pronostico:
        return None
    p = pronostico.strip().lower()

    if tipo == 'SEGNO':
        mapping = {'1': '1', 'x': 'X', '2': '2'}
        return odds.get(mapping.get(p))

    if tipo == 'GOL':
        mapping = {
            'over 1.5': 'over_15', 'under 1.5': 'under_15',
            'over 2.5': 'over_25', 'under 2.5': 'under_25',
            'over 3.5': 'over_35', 'under 3.5': 'under_35',
            'goal': 'gg', 'nogoal': 'ng',
        }
        key = mapping.get(p)
        if key:
            return odds.get(key)

    if tipo == 'DOPPIA_CHANCE':
        # Doppia chance non ha quote dirette
        return None

    return None


def normalize_market(tipo, pronostico):
    """Normalizza il tipo di mercato (GOL -> OVER_UNDER o GG_NG)."""
    if tipo != 'GOL':
        return tipo
    p = pronostico.strip().lower() if pronostico else ''
    if p in ('goal', 'nogoal'):
        return 'GG_NG'
    return 'OVER_UNDER'


QUOTA_BANDS = [
    ('1.01-1.20', 1.01, 1.20),
    ('1.21-1.40', 1.21, 1.40),
    ('1.41-1.60', 1.41, 1.60),
    ('1.61-1.80', 1.61, 1.80),
    ('1.81-2.00', 1.81, 2.00),
    ('2.01-2.20', 2.01, 2.20),
    ('2.21-2.50', 2.21, 2.50),
    ('2.51-3.00', 2.51, 3.00),
    ('3.01-3.50', 3.01, 3.50),
    ('3.51-4.00', 3.51, 4.00),
    ('4.01-5.00', 4.01, 5.00),
    ('5.00+', 5.01, 9999),
]

CONFIDENCE_BANDS = [
    ('60-65', 60, 65),
    ('65-70', 65, 70),
    ('70-75', 70, 75),
    ('75-80', 75, 80),
    ('80-90', 80, 90),
    ('90+', 90, 101),
]

STARS_BANDS = [
    ('2.5-3', 2.5, 3.0),
    ('3-3.5', 3.0, 3.5),
    ('3.5-4', 3.5, 4.0),
    ('4-5', 4.0, 5.1),
]


def get_quota_band(q):
    if q is None:
        return 'N/D'
    for label, lo, hi in QUOTA_BANDS:
        if lo <= q <= hi:
            return label
    return 'N/D'


def get_confidence_band(c):
    for label, lo, hi in CONFIDENCE_BANDS:
        if lo <= c < hi:
            return label
    return None


def get_stars_band(s):
    for label, lo, hi in STARS_BANDS:
        if lo <= s < hi:
            return label
    return None


def hit_rate(total, hits):
    if total == 0:
        return None
    return round(hits / total * 100, 1)


# ==============================================================================
# RACCOLTA DATI
# ==============================================================================

print("1. Caricamento pronostici da daily_predictions...")
predictions = list(db['daily_predictions'].find({}))
print(f"   Trovati {len(predictions)} documenti di pronostici")

print("2. Caricamento risultati da h2h_by_round...")
# Costruisco mappa risultati: "home|||away|||date" -> real_score
results_map = {}
pipeline = [
    {"$unwind": "$matches"},
    {"$match": {"matches.real_score": {"$ne": None}}},
    {"$project": {
        "league": 1,
        "home": "$matches.home",
        "away": "$matches.away",
        "date": "$matches.date_obj",
        "score": "$matches.real_score",
    }}
]
for doc in db['h2h_by_round'].aggregate(pipeline, allowDiskUse=True):
    home = doc.get('home', '')
    away = doc.get('away', '')
    date_obj = doc.get('date')
    if not date_obj or not home or not away:
        continue
    if hasattr(date_obj, 'strftime'):
        date_str = date_obj.strftime('%Y-%m-%d')
    else:
        date_str = str(date_obj)[:10]
    key = f"{home}|||{away}|||{date_str}"
    results_map[key] = doc.get('score', '')

print(f"   Trovati {len(results_map)} risultati reali")

# ==============================================================================
# VERIFICA PRONOSTICI
# ==============================================================================

print("3. Verifica pronostici vs risultati...")

verified = []  # Lista di dict con tutti i dati per analisi

for pred_doc in predictions:
    date = pred_doc.get('date', '')
    home = pred_doc.get('home', '')
    away = pred_doc.get('away', '')
    league = pred_doc.get('league', '')
    odds = pred_doc.get('odds', {})

    key = f"{home}|||{away}|||{date}"
    real_score = results_map.get(key)
    parsed = parse_score(real_score) if real_score else None

    if not parsed:
        continue  # Partita non ancora giocata o risultato non trovato

    pronostici = pred_doc.get('pronostici', [])
    for p in pronostici:
        tipo = p.get('tipo', '')
        pronostico = p.get('pronostico', '')
        confidence = p.get('confidence', 0)
        stars = p.get('stars', 0)

        result = check_pronostico(pronostico, tipo, parsed)
        if result is None:
            continue

        # Estrai quota
        quota = p.get('quota') or get_quota_for_pronostico(pronostico, tipo, odds)
        if quota is not None:
            try:
                quota = float(quota)
            except (ValueError, TypeError):
                quota = None

        market = normalize_market(tipo, pronostico)

        verified.append({
            'date': date,
            'home': home,
            'away': away,
            'league': league,
            'tipo': tipo,
            'market': market,
            'pronostico': pronostico,
            'confidence': confidence,
            'stars': stars,
            'quota': quota,
            'hit': result,
        })

print(f"   Pronostici verificati: {len(verified)}")

# ==============================================================================
# CALCOLO STATISTICHE
# ==============================================================================

print("4. Calcolo statistiche...")

total = len(verified)
hits = sum(1 for v in verified if v['hit'])
misses = total - hits

report = {
    'generato_il': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
    'globale': {
        'total': total,
        'hits': hits,
        'misses': misses,
        'hit_rate': hit_rate(total, hits),
    },
    'breakdown_mercato': {},
    'breakdown_campionato': {},
    'breakdown_confidence': {},
    'breakdown_stelle': {},
    'breakdown_quota': {},
    'quota_stats': {},
    'cross_mercato_campionato': {},
    'serie_temporale': [],
}

# --- Per Mercato ---
markets = defaultdict(lambda: {'total': 0, 'hits': 0})
for v in verified:
    m = v['market']
    markets[m]['total'] += 1
    if v['hit']:
        markets[m]['hits'] += 1

for m, data in sorted(markets.items()):
    report['breakdown_mercato'][m] = {
        'total': data['total'],
        'hits': data['hits'],
        'misses': data['total'] - data['hits'],
        'hit_rate': hit_rate(data['total'], data['hits']),
    }

# --- Per Campionato ---
leagues = defaultdict(lambda: {'total': 0, 'hits': 0})
for v in verified:
    leagues[v['league']]['total'] += 1
    if v['hit']:
        leagues[v['league']]['hits'] += 1

for l, data in sorted(leagues.items(), key=lambda x: x[1]['total'], reverse=True):
    report['breakdown_campionato'][l] = {
        'total': data['total'],
        'hits': data['hits'],
        'misses': data['total'] - data['hits'],
        'hit_rate': hit_rate(data['total'], data['hits']),
    }

# --- Per Confidence ---
conf_bands = defaultdict(lambda: {'total': 0, 'hits': 0})
for v in verified:
    band = get_confidence_band(v['confidence'])
    if band:
        conf_bands[band]['total'] += 1
        if v['hit']:
            conf_bands[band]['hits'] += 1

for band_label, _, _ in CONFIDENCE_BANDS:
    data = conf_bands.get(band_label, {'total': 0, 'hits': 0})
    report['breakdown_confidence'][band_label] = {
        'total': data['total'],
        'hits': data['hits'],
        'misses': data['total'] - data['hits'],
        'hit_rate': hit_rate(data['total'], data['hits']),
    }

# --- Per Stelle ---
stars_bands = defaultdict(lambda: {'total': 0, 'hits': 0})
for v in verified:
    band = get_stars_band(v['stars'])
    if band:
        stars_bands[band]['total'] += 1
        if v['hit']:
            stars_bands[band]['hits'] += 1

for band_label, _, _ in STARS_BANDS:
    data = stars_bands.get(band_label, {'total': 0, 'hits': 0})
    report['breakdown_stelle'][band_label] = {
        'total': data['total'],
        'hits': data['hits'],
        'misses': data['total'] - data['hits'],
        'hit_rate': hit_rate(data['total'], data['hits']),
    }

# --- Per Quota ---
quota_bands = defaultdict(lambda: {'total': 0, 'hits': 0, 'profit': 0.0, 'sum_quota': 0.0})
for v in verified:
    band = get_quota_band(v['quota'])
    quota_bands[band]['total'] += 1
    if v['hit']:
        quota_bands[band]['hits'] += 1
        if v['quota']:
            quota_bands[band]['profit'] += v['quota'] - 1
    else:
        quota_bands[band]['profit'] -= 1
    if v['quota']:
        quota_bands[band]['sum_quota'] += v['quota']

all_band_labels = [b[0] for b in QUOTA_BANDS] + ['N/D']
for band_label in all_band_labels:
    data = quota_bands.get(band_label, {'total': 0, 'hits': 0, 'profit': 0.0, 'sum_quota': 0.0})
    if data['total'] == 0:
        continue
    avg_q = round(data['sum_quota'] / data['hits'], 2) if data['hits'] > 0 and data['sum_quota'] > 0 else None
    # Per avg_quota contiamo quelli con quota non-N/D
    count_with_q = sum(1 for v in verified if get_quota_band(v['quota']) == band_label and v['quota'])
    avg_q = round(data['sum_quota'] / count_with_q, 2) if count_with_q > 0 else None
    report['breakdown_quota'][band_label] = {
        'total': data['total'],
        'hits': data['hits'],
        'misses': data['total'] - data['hits'],
        'hit_rate': hit_rate(data['total'], data['hits']),
        'roi': round(data['profit'] / data['total'] * 100, 1) if data['total'] > 0 else None,
        'profit': round(data['profit'], 2),
        'avg_quota': avg_q,
    }

# --- Quota Stats globali ---
con_quota = [v for v in verified if v['quota'] is not None]
senza_quota = [v for v in verified if v['quota'] is None]
hits_cq = [v for v in con_quota if v['hit']]
miss_cq = [v for v in con_quota if not v['hit']]
profit_tot = sum(v['quota'] - 1 for v in hits_cq) - len(miss_cq)

report['quota_stats'] = {
    'total_con_quota': len(con_quota),
    'total_senza_quota': len(senza_quota),
    'avg_quota_tutti': round(sum(v['quota'] for v in con_quota) / len(con_quota), 2) if con_quota else None,
    'avg_quota_azzeccati': round(sum(v['quota'] for v in hits_cq) / len(hits_cq), 2) if hits_cq else None,
    'avg_quota_sbagliati': round(sum(v['quota'] for v in miss_cq) / len(miss_cq), 2) if miss_cq else None,
    'roi_globale': round(profit_tot / len(con_quota) * 100, 1) if con_quota else None,
    'profit_globale': round(profit_tot, 2),
}

# --- Cross Mercato x Campionato ---
cross = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'hits': 0}))
for v in verified:
    cross[v['market']][v['league']]['total'] += 1
    if v['hit']:
        cross[v['market']][v['league']]['hits'] += 1

for market, leagues_data in sorted(cross.items()):
    report['cross_mercato_campionato'][market] = {}
    for league, data in sorted(leagues_data.items(), key=lambda x: x[1]['total'], reverse=True):
        report['cross_mercato_campionato'][market][league] = {
            'total': data['total'],
            'hits': data['hits'],
            'misses': data['total'] - data['hits'],
            'hit_rate': hit_rate(data['total'], data['hits']),
        }

# --- Cross Mercato x Confidence ---
cross_mc = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'hits': 0}))
for v in verified:
    band = get_confidence_band(v['confidence'])
    if band:
        cross_mc[v['market']][band]['total'] += 1
        if v['hit']:
            cross_mc[v['market']][band]['hits'] += 1

report['cross_mercato_confidence'] = {}
for market, bands_data in sorted(cross_mc.items()):
    report['cross_mercato_confidence'][market] = {}
    for band, data in sorted(bands_data.items()):
        report['cross_mercato_confidence'][market][band] = {
            'total': data['total'],
            'hits': data['hits'],
            'misses': data['total'] - data['hits'],
            'hit_rate': hit_rate(data['total'], data['hits']),
        }

# --- Serie Temporale ---
daily = defaultdict(lambda: {'total': 0, 'hits': 0})
for v in verified:
    daily[v['date']]['total'] += 1
    if v['hit']:
        daily[v['date']]['hits'] += 1

for date in sorted(daily.keys()):
    data = daily[date]
    report['serie_temporale'].append({
        'date': date,
        'total': data['total'],
        'hits': data['hits'],
        'misses': data['total'] - data['hits'],
        'hit_rate': hit_rate(data['total'], data['hits']),
    })

# ==============================================================================
# SALVATAGGIO JSON
# ==============================================================================

json_path = os.path.join(LOG_DIR, 'track-record-report.json')
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(f"\n5. JSON salvato: {json_path}")

# ==============================================================================
# SALVATAGGIO TXT
# ==============================================================================

txt_path = os.path.join(LOG_DIR, 'track-record-report.txt')

def fmt_hr(hr):
    return f"{hr}%" if hr is not None else "N/D"

with open(txt_path, 'w', encoding='utf-8') as f:
    f.write("=" * 70 + "\n")
    f.write(f"  REPORT TRACK RECORD — Generato il {report['generato_il']}\n")
    f.write("=" * 70 + "\n\n")

    g = report['globale']
    f.write(f"RIEPILOGO GLOBALE\n")
    f.write(f"-" * 40 + "\n")
    f.write(f"  Pronostici verificati: {g['total']}\n")
    f.write(f"  Azzeccati:            {g['hits']}\n")
    f.write(f"  Sbagliati:            {g['misses']}\n")
    f.write(f"  Hit Rate:             {fmt_hr(g['hit_rate'])}\n\n")

    # Per Mercato
    f.write(f"PER MERCATO\n")
    f.write(f"-" * 40 + "\n")
    f.write(f"  {'Mercato':<16} {'Tot':>5} {'Hit':>5} {'Miss':>5} {'HR':>8}\n")
    for m, data in report['breakdown_mercato'].items():
        f.write(f"  {m:<16} {data['total']:>5} {data['hits']:>5} {data['misses']:>5} {fmt_hr(data['hit_rate']):>8}\n")
    f.write("\n")

    # Per Confidence
    f.write(f"PER FASCIA CONFIDENCE\n")
    f.write(f"-" * 40 + "\n")
    f.write(f"  {'Fascia':<10} {'Tot':>5} {'Hit':>5} {'Miss':>5} {'HR':>8}\n")
    for band, data in report['breakdown_confidence'].items():
        if data['total'] > 0:
            f.write(f"  {band:<10} {data['total']:>5} {data['hits']:>5} {data['misses']:>5} {fmt_hr(data['hit_rate']):>8}\n")
    f.write("\n")

    # Per Stelle
    f.write(f"PER STELLE\n")
    f.write(f"-" * 40 + "\n")
    f.write(f"  {'Stelle':<10} {'Tot':>5} {'Hit':>5} {'Miss':>5} {'HR':>8}\n")
    for band, data in report['breakdown_stelle'].items():
        if data['total'] > 0:
            f.write(f"  {band:<10} {data['total']:>5} {data['hits']:>5} {data['misses']:>5} {fmt_hr(data['hit_rate']):>8}\n")
    f.write("\n")

    # Cross Mercato x Confidence
    if 'cross_mercato_confidence' in report:
        f.write(f"MERCATO x CONFIDENCE\n")
        f.write(f"-" * 40 + "\n")
        for market, bands in report['cross_mercato_confidence'].items():
            f.write(f"  {market}:\n")
            for band, data in bands.items():
                if data['total'] > 0:
                    f.write(f"    {band:<10} {data['total']:>4} pred  HR {fmt_hr(data['hit_rate']):>6}\n")
        f.write("\n")

    # Per Campionato (top 15)
    f.write(f"PER CAMPIONATO (ordinato per volume)\n")
    f.write(f"-" * 40 + "\n")
    f.write(f"  {'Campionato':<35} {'Tot':>5} {'Hit':>5} {'HR':>8}\n")
    for league, data in list(report['breakdown_campionato'].items())[:20]:
        f.write(f"  {league:<35} {data['total']:>5} {data['hits']:>5} {fmt_hr(data['hit_rate']):>8}\n")
    f.write("\n")

    # Per Quota
    f.write(f"PER FASCIA QUOTA\n")
    f.write(f"-" * 40 + "\n")
    f.write(f"  {'Fascia':<12} {'Tot':>5} {'HR':>8} {'ROI':>8} {'Profit':>8}\n")
    for band, data in report['breakdown_quota'].items():
        roi_str = f"{data['roi']}%" if data['roi'] is not None else "N/D"
        f.write(f"  {band:<12} {data['total']:>5} {fmt_hr(data['hit_rate']):>8} {roi_str:>8} {data['profit']:>+8.2f}\n")
    f.write("\n")

    # Quota Stats
    qs = report['quota_stats']
    f.write(f"STATISTICHE QUOTE\n")
    f.write(f"-" * 40 + "\n")
    f.write(f"  Con quota:     {qs['total_con_quota']}\n")
    f.write(f"  Senza quota:   {qs['total_senza_quota']}\n")
    f.write(f"  Quota media:   {qs['avg_quota_tutti'] or 'N/D'}\n")
    f.write(f"  Q. azzeccati:  {qs['avg_quota_azzeccati'] or 'N/D'}\n")
    f.write(f"  Q. sbagliati:  {qs['avg_quota_sbagliati'] or 'N/D'}\n")
    f.write(f"  ROI globale:   {qs['roi_globale']}%\n" if qs['roi_globale'] else "")
    f.write(f"  Profitto:      {qs['profit_globale']:+.2f} unita\n\n")

    # Serie Temporale (ultimi 15 giorni)
    f.write(f"SERIE TEMPORALE (ultimi 15 giorni)\n")
    f.write(f"-" * 40 + "\n")
    for entry in report['serie_temporale'][-15:]:
        f.write(f"  {entry['date']}  {entry['total']:>3} pred  {entry['hits']:>3} hit  HR {fmt_hr(entry['hit_rate']):>6}\n")
    f.write("\n")

    # Segnalazioni (campionati con HR < 50% e almeno 5 pronostici)
    f.write(f"SEGNALAZIONI (campionati con HR < 50%, min 5 pred)\n")
    f.write(f"-" * 40 + "\n")
    warnings = [(l, d) for l, d in report['breakdown_campionato'].items()
                if d['total'] >= 5 and d['hit_rate'] is not None and d['hit_rate'] < 50]
    if warnings:
        for league, data in sorted(warnings, key=lambda x: x[1]['hit_rate']):
            f.write(f"  ⚠ {league}: {fmt_hr(data['hit_rate'])} su {data['total']} pronostici\n")
    else:
        f.write(f"  Nessun campionato sotto il 50%\n")
    f.write("\n")

    # Cross Mercato x Campionato — problemi
    f.write(f"COMBINAZIONI PROBLEMATICHE (mercato x campionato, HR < 50%, min 3 pred)\n")
    f.write(f"-" * 40 + "\n")
    problems = []
    for market, leagues_data in report['cross_mercato_campionato'].items():
        for league, data in leagues_data.items():
            if data['total'] >= 3 and data['hit_rate'] is not None and data['hit_rate'] < 50:
                problems.append((market, league, data))
    if problems:
        for market, league, data in sorted(problems, key=lambda x: x[2]['hit_rate']):
            f.write(f"  ⚠ {market} in {league}: {fmt_hr(data['hit_rate'])} su {data['total']} pred\n")
    else:
        f.write(f"  Nessuna combinazione critica\n")

    f.write(f"\n{'='*70}\n")
    f.write(f"  File JSON: {json_path}\n")
    f.write(f"{'='*70}\n")

print(f"6. TXT salvato: {txt_path}")
print(f"\n{'='*60}")
print(f"REPORT COMPLETATO: {len(verified)} pronostici, HR {fmt_hr(report['globale']['hit_rate'])}")
print(f"{'='*60}")
