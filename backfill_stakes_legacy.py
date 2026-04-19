"""
BACKFILL STAKES — Ricalcolo storico probabilità, stake e profit/loss
====================================================================
Script one-shot per aggiungere probabilita_stimata, stake, edge, profit_loss
a TUTTI i pronostici passati in daily_predictions.

Usa segno_dettaglio e gol_dettaglio già salvati nel DB.
"""

import os, sys, re, json
from datetime import datetime

# --- FIX PERCORSI ---
current_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'functions_python', 'ai_engine')
sys.path.insert(0, current_path)
from config import db


# ==================== FUNZIONI (copiate da run_daily_predictions.py) ====================

def get_quota_segno(pronostico, odds):
    if pronostico in ['1', '2', 'X']:
        v = float(odds.get(pronostico, 0))
        return v if v > 1.01 else None
    dc_map = {'1X': ('1', 'X'), 'X2': ('X', '2'), '12': ('1', '2')}
    pair = dc_map.get(pronostico)
    if pair:
        q1, q2 = float(odds.get(pair[0], 0)), float(odds.get(pair[1], 0))
        if q1 > 1 and q2 > 1:
            return round(1 / (1/q1 + 1/q2), 2)
    return None

def get_quota_gol(pronostico, odds):
    mapping = {
        'over 2.5': 'over_25', 'under 2.5': 'under_25',
        'over 1.5': 'over_15', 'under 3.5': 'under_35',
        'goal': 'gg', 'nogoal': 'ng',
    }
    key = mapping.get(pronostico.lower())
    if key:
        v = float(odds.get(key, 0))
        return v if v > 1.01 else None
    return None

def calcola_probabilita_stimata(quota, dettaglio, tipo, directions=None):
    if quota and quota > 1.01:
        p_market = (1.0 / quota) * 0.96
        p_market = min(p_market, 0.92)
        has_odds = True
    else:
        p_market = 0.50
        has_odds = False

    scores = [v for v in dettaglio.values() if isinstance(v, (int, float))]
    n = len(scores)
    if n == 0:
        p = round(p_market * 100, 1)
        return {'probabilita_stimata': p, 'prob_mercato': p, 'prob_modello': 50.0, 'has_odds': has_odds}

    avg = sum(scores) / n
    consensus = sum(1 for s in scores if s > 55) / n
    strong = sum(1 for s in scores if s > 70) / n
    variance = sum((s - avg) ** 2 for s in scores) / n
    std = variance ** 0.5

    dir_bonus = 0
    if directions:
        vals = [v for v in directions.values() if v != 'neutro']
        if vals:
            most = max(set(vals), key=vals.count)
            dir_ratio = vals.count(most) / len(vals)
            if dir_ratio > 0.70:
                dir_bonus = (dir_ratio - 0.70) * 0.12

    # Calcolo differenziato per tipo di mercato
    if tipo == 'SEGNO':
        p_model = 0.44 + (avg - 50) * 0.015
    elif tipo == 'DOPPIA_CHANCE':
        # DC copre 2 esiti su 3 → quote basse (1.20-1.50) → serve base/slope più alte
        p_model = 0.52 + (avg - 50) * 0.018
    else:  # GOL (Over/Under, GG/NG)
        p_model = 0.42 + (avg - 50) * 0.013
    # Bonus consensus (a gradini — ibrido dal piano MD)
    if consensus >= 0.80:
        p_model += 0.03
    elif consensus >= 0.70:
        p_model += 0.02
    elif consensus >= 0.60:
        p_model += 0.01

    # Bonus strong signals (a gradini — ibrido dal piano MD)
    if strong >= 0.50:
        p_model += 0.03
    elif strong >= 0.35:
        p_model += 0.02

    # Direction bonus GOL + penalità varianza (dal mio piano)
    p_model += dir_bonus
    if std > 12:
        p_model -= (std - 12) * 0.003
    p_model = max(0.25, min(0.88, p_model))

    # Modello puro — nessun blend con il mercato
    p_final = p_model

    caps = {
        'SEGNO': (0.30, 0.78), 'DOPPIA_CHANCE': (0.45, 0.88), 'GOL': (0.35, 0.80),
    }
    lo, hi = caps.get(tipo, (0.30, 0.85))
    p_final = max(lo, min(hi, p_final))

    return {
        'probabilita_stimata': round(p_final * 100, 1),
        'prob_mercato': round(p_market * 100, 1),
        'prob_modello': round(p_model * 100, 1),
        'has_odds': has_odds,
    }

def calcola_stake_kelly(quota, probabilita_stimata, tipo='GOL'):
    p = probabilita_stimata / 100
    if not quota or quota <= 1:
        return 1, 0.0  # Stake minimo 1 anche senza quota
    edge = (p * quota - 1) * 100
    if (p * quota) <= 1:
        # Edge negativo ma il modello ha comunque emesso il pronostico → stake minimo
        return 1, round(edge, 2)
    full_kelly = (p * quota - 1) / (quota - 1)
    quarter_kelly = full_kelly / 4
    # Nessun edge minimo — tutti i pronostici ricevono stake
    stake = min(max(round(quarter_kelly * 100), 1), 10)

    # Protezioni tipo-specifiche (ibrido: MD + mio)
    if tipo == 'SEGNO':
        if quota < 1.30:
            stake = min(stake, 2)   # Favorita fortissima
        elif quota < 1.50:
            stake = min(stake, 4)   # Favorita media
    if quota < 1.20:
        stake = min(stake, 2)       # Generale: quote bassissime
    if probabilita_stimata > 85:
        stake = min(stake, 3)       # Overconfidence protection
    if quota > 5.0:
        stake = min(stake, 2)       # Value trap protection
    return stake, round(edge, 2)

def parse_score(real_score):
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
    sign = '1' if h > a else ('X' if h == a else '2')
    btts = h > 0 and a > 0
    return {'home': h, 'away': a, 'total': total, 'sign': sign, 'btts': btts}

def check_pronostico(pronostico, tipo, parsed):
    if not parsed or not pronostico:
        return None
    p = pronostico.strip()
    if tipo == 'SEGNO':
        return parsed['sign'] == p
    if tipo == 'DOPPIA_CHANCE':
        if p == '1X': return parsed['sign'] in ('1', 'X')
        if p == 'X2': return parsed['sign'] in ('X', '2')
        if p == '12': return parsed['sign'] in ('1', '2')
        return None
    if tipo == 'GOL':
        m = re.match(r'(Over|Under)\s+([\d.]+)', p, re.IGNORECASE)
        if m:
            return parsed['total'] > float(m.group(2)) if m.group(1).lower() == 'over' else parsed['total'] < float(m.group(2))
        if p.lower() == 'goal': return parsed['btts']
        if p.lower() == 'nogoal': return not parsed['btts']
    return None


# ==================== CARICA RISULTATI REALI ====================

print(f"\n{'='*60}")
print(f"BACKFILL STAKES + PROFIT/LOSS")
print(f"{'='*60}")
start_time = datetime.now()
print(f"Avvio: {start_time.strftime('%d/%m/%Y %H:%M:%S')}\n")

today = datetime.now().strftime('%Y-%m-%d')

print("Caricamento risultati da h2h_by_round...")
results_map = {}
pipeline = [
    {"$unwind": "$matches"},
    {"$match": {"matches.real_score": {"$ne": None}}},
    {"$project": {
        "home": "$matches.home",
        "away": "$matches.away",
        "date": "$matches.date_obj",
        "score": "$matches.real_score",
    }}
]
for doc in db.h2h_by_round.aggregate(pipeline):
    d = doc.get('date')
    if d:
        date_str = d.strftime('%Y-%m-%d')
        key = f"{doc['home']}|||{doc['away']}|||{date_str}"
        results_map[key] = doc['score']

# Coppe
for coll_name in ['matches_champions_league', 'matches_europa_league']:
    if coll_name in db.list_collection_names():
        for doc in db[coll_name].find({"real_score": {"$ne": None}}, {"home_team": 1, "away_team": 1, "match_date": 1, "real_score": 1}):
            md = doc.get('match_date', '')
            if md:
                try:
                    dt = md.split(' ')[0].split('-')
                    date_str = md.split(' ')[0] if len(dt[0]) == 4 else f"{dt[2]}-{dt[1]}-{dt[0]}"
                except:
                    continue
                key = f"{doc['home_team']}|||{doc['away_team']}|||{date_str}"
                results_map[key] = doc['real_score']

print(f"  {len(results_map)} risultati caricati.\n")


# ==================== BACKFILL ====================

# Leggi TUTTI i documenti passati (non solo quelli senza profit_loss)
docs = list(db.daily_predictions.find({'date': {'$lt': today}}))
print(f"Documenti totali da processare: {len(docs)}")

stats = {
    'inizio': start_time.isoformat(),
    'totale_documenti': 0,
    'totale_pronostici': 0,
    'successi': 0,
    'errori': [],
    'warning': [],
    'quote_mancanti': 0,
    'stake_zero': 0,
    'vinti': 0,
    'persi': 0,
    'pending': 0,
}

for doc in docs:
    stats['totale_documenti'] += 1
    date = doc.get('date', '')
    home = doc.get('home', '')
    away = doc.get('away', '')
    odds = doc.get('odds', {})
    segno_det = doc.get('segno_dettaglio', {})
    gol_det = doc.get('gol_dettaglio', {})
    gol_dirs = doc.get('gol_directions', {})

    key = f"{home}|||{away}|||{date}"
    real_score = results_map.get(key)
    parsed = parse_score(real_score) if real_score else None

    updates = {}
    match_id = f"{home} vs {away}"

    for i, prono in enumerate(doc.get('pronostici', [])):
        stats['totale_pronostici'] += 1

        try:
            tipo = prono.get('tipo', '')
            pronostico = prono.get('pronostico', '')

            # Skip X_FACTOR e RISULTATO_ESATTO
            if prono.get('is_x_factor') or prono.get('is_exact_score') or tipo in ('X_FACTOR', 'RISULTATO_ESATTO'):
                continue

            # Calcola quota
            if tipo in ('SEGNO', 'DOPPIA_CHANCE'):
                quota = prono.get('quota') or get_quota_segno(pronostico, odds)
                det = segno_det
                dirs = None
            else:
                quota = get_quota_gol(pronostico, odds)
                det = gol_det
                dirs = gol_dirs

            if not quota:
                stats['quote_mancanti'] += 1
                stats['warning'].append({
                    'date': date, 'match': match_id, 'tipo': tipo,
                    'problema': 'quota_mancante'
                })

            # Probabilità e stake
            prob_result = calcola_probabilita_stimata(quota, det, tipo, dirs)
            stake, edge = calcola_stake_kelly(quota, prob_result['probabilita_stimata'], tipo)

            if stake == 0:
                stats['stake_zero'] += 1

            # Profit/loss
            esito = check_pronostico(pronostico, tipo, parsed)
            if esito is True and quota:
                pl = round(stake * (quota - 1), 2)
                stats['vinti'] += 1
            elif esito is False:
                pl = -stake
                stats['persi'] += 1
            else:
                pl = None
                stats['pending'] += 1

            # Update fields
            prefix = f'pronostici.{i}'
            updates[f'{prefix}.quota'] = prono.get('quota') or quota
            updates[f'{prefix}.probabilita_stimata'] = prob_result['probabilita_stimata']
            updates[f'{prefix}.prob_mercato'] = prob_result['prob_mercato']
            updates[f'{prefix}.prob_modello'] = prob_result['prob_modello']
            updates[f'{prefix}.has_odds'] = prob_result['has_odds']
            updates[f'{prefix}.stake'] = stake
            updates[f'{prefix}.edge'] = edge
            updates[f'{prefix}.esito'] = esito
            updates[f'{prefix}.profit_loss'] = pl

            stats['successi'] += 1

        except Exception as e:
            stats['errori'].append({
                'date': date, 'match': match_id,
                'pronostico': prono.get('pronostico', '?'),
                'errore': str(e)
            })

    if updates:
        try:
            db.daily_predictions.update_one({'_id': doc['_id']}, {'$set': updates})
        except Exception as e:
            stats['errori'].append({
                'date': date, 'match': match_id,
                'errore': f'DB update failed: {e}'
            })

    # Progress ogni 50 documenti
    if stats['totale_documenti'] % 50 == 0:
        print(f"  ... {stats['totale_documenti']}/{len(docs)} documenti processati")


# ==================== RIEPILOGO ====================

end_time = datetime.now()
stats['fine'] = end_time.isoformat()
stats['durata_secondi'] = (end_time - start_time).total_seconds()

# Salva report JSON
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log')
os.makedirs(log_dir, exist_ok=True)
report_path = os.path.join(log_dir, 'backfill_report.json')
with open(report_path, 'w', encoding='utf-8') as f:
    json.dump(stats, f, indent=2, ensure_ascii=False)

# Calcola P/L totale
total_pl = 0
total_staked = 0
for doc in db.daily_predictions.find({'date': {'$lt': today}}):
    for p in doc.get('pronostici', []):
        if p.get('profit_loss') is not None:
            total_pl += p['profit_loss']
            total_staked += p.get('stake', 0)

yield_pct = (total_pl / total_staked * 100) if total_staked > 0 else 0

print(f"""
{'='*60}
 BACKFILL COMPLETATO
{'='*60}
 Documenti processati:  {stats['totale_documenti']}
 Pronostici totali:     {stats['totale_pronostici']}
 Successi:              {stats['successi']}
 Errori:                {len(stats['errori'])}
 Warning:               {len(stats['warning'])}

 Dettagli:
   Quote mancanti:      {stats['quote_mancanti']}
   Stake = 0:           {stats['stake_zero']}
   Vinti:               {stats['vinti']}
   Persi:               {stats['persi']}
   Pending:             {stats['pending']}

 RISULTATI ECONOMICI:
   P/L Totale:          {total_pl:+.2f} unita
   Stake Totale:        {total_staked} unita
   Yield:               {yield_pct:+.1f}%

 Durata: {stats['durata_secondi']:.1f}s
 Report: {report_path}
{'='*60}
""")

if stats['errori']:
    print("ERRORI DETTAGLIATI:")
    for err in stats['errori'][:10]:
        print(f"  - {err.get('date', '?')} {err.get('match', '?')}: {err.get('errore', '?')}")
    if len(stats['errori']) > 10:
        print(f"  ... e altri {len(stats['errori']) - 10} errori (vedi JSON)")
