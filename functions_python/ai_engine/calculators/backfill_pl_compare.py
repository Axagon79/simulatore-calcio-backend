"""
CONFRONTO P/L: Backfill Dry-Run vs Produzione
===============================================
Legge i pronostici generati dal backfill dry-run (JSON)
e i pronostici attualmente in produzione (MongoDB).
Calcola il P/L di entrambi e mostra il confronto.

Uso:
  python backfill_pl_compare.py                     # confronto completo
  python backfill_pl_compare.py --from 2026-03-01   # solo da una certa data
"""

import os, sys, re, json, argparse
from datetime import datetime, timedelta

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db


# ==================== UTILITÀ ====================

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
        mg = re.match(r'MG\s+(\d+)-(\d+)', p, re.IGNORECASE)
        if mg:
            return int(mg.group(1)) <= parsed['total'] <= int(mg.group(2))
    if tipo == 'RISULTATO_ESATTO':
        real_str = f"{parsed['home']}:{parsed['away']}"
        return p.replace('-', ':') == real_str
    return None


def calc_pl_from_docs(docs, results_map, date_filter=None):
    """Calcola P/L su una lista di documenti pronostico."""
    stats = {
        'bets': 0, 'wins': 0, 'losses': 0, 'pending': 0, 'void': 0,
        'pl': 0.0, 'staked': 0.0,
        'by_tipo': {},
        'by_month': {},
    }

    for doc in docs:
        date = doc.get('date', '')
        if date_filter and date < date_filter:
            continue

        home = doc.get('home', '')
        away = doc.get('away', '')
        key = f"{home}|||{away}|||{date}"
        real_score = results_map.get(key)
        parsed = parse_score(real_score) if real_score else None

        month = date[:7] if date else '????'

        for prono in doc.get('pronostici', []):
            pronostico = prono.get('pronostico', '')
            if pronostico == 'NO BET' or not pronostico:
                continue

            tipo = prono.get('tipo', '')
            stake = prono.get('stake') or 0
            quota = prono.get('quota') or 0

            if stake <= 0 or quota <= 1:
                continue

            esito = check_pronostico(pronostico, tipo, parsed)

            if esito is True:
                pl = round(stake * (quota - 1), 2)
                stats['wins'] += 1
            elif esito is False:
                pl = -stake
                stats['losses'] += 1
            elif parsed is None:
                try:
                    days_old = (datetime.now() - datetime.strptime(date, '%Y-%m-%d')).days
                except ValueError:
                    days_old = 0
                if days_old >= 7:
                    pl = 0
                    stats['void'] += 1
                else:
                    stats['pending'] += 1
                    continue
            else:
                stats['pending'] += 1
                continue

            stats['bets'] += 1
            stats['staked'] += stake
            stats['pl'] += pl

            # Per tipo
            if tipo not in stats['by_tipo']:
                stats['by_tipo'][tipo] = {'bets': 0, 'wins': 0, 'pl': 0.0, 'staked': 0.0}
            t = stats['by_tipo'][tipo]
            t['bets'] += 1
            t['staked'] += stake
            t['pl'] += pl
            if esito is True:
                t['wins'] += 1

            # Per mese
            if month not in stats['by_month']:
                stats['by_month'][month] = {'bets': 0, 'wins': 0, 'pl': 0.0, 'staked': 0.0}
            m = stats['by_month'][month]
            m['bets'] += 1
            m['staked'] += stake
            m['pl'] += pl
            if esito is True:
                m['wins'] += 1

    # Arrotonda
    stats['pl'] = round(stats['pl'], 2)
    stats['staked'] = round(stats['staked'], 2)
    return stats


def load_results_map():
    """Carica tutti i risultati reali da h2h_by_round + coppe."""
    results_map = {}

    # h2h_by_round
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
            for delta in [-1, 1]:
                alt = (d + timedelta(days=delta)).strftime('%Y-%m-%d')
                alt_key = f"{doc['home']}|||{doc['away']}|||{alt}"
                results_map.setdefault(alt_key, doc['score'])

    # Coppe
    for coll_name in ['matches_champions_league', 'matches_europa_league']:
        if coll_name in db.list_collection_names():
            for doc in db[coll_name].find(
                {"$or": [{"real_score": {"$ne": None}}, {"result": {"$exists": True}}]},
                {"home_team": 1, "away_team": 1, "match_date": 1, "real_score": 1, "result": 1, "status": 1}
            ):
                rs = doc.get('real_score')
                if not rs and doc.get('result'):
                    r = doc['result']
                    if r.get('home_score') is not None and r.get('away_score') is not None:
                        rs = f"{r['home_score']}:{r['away_score']}"
                if not rs:
                    continue
                status = (doc.get('status') or '').lower()
                if status not in ('finished', 'ft'):
                    continue
                md = doc.get('match_date', '')
                if md:
                    try:
                        dt = md.split(' ')[0].split('-')
                        date_str = md.split(' ')[0] if len(dt[0]) == 4 else f"{dt[2]}-{dt[1]}-{dt[0]}"
                    except:
                        continue
                    key = f"{doc['home_team']}|||{doc['away_team']}|||{date_str}"
                    results_map[key] = rs

    return results_map


def print_stats(label, stats):
    """Stampa le statistiche P/L."""
    hr = round((stats['wins'] / stats['bets']) * 100, 1) if stats['bets'] > 0 else 0
    roi = round((stats['pl'] / stats['staked']) * 100, 1) if stats['staked'] > 0 else 0
    pl_icon = '🟢' if stats['pl'] >= 0 else '🔴'

    print(f"\n  {label}")
    print(f"  {'─'*50}")
    print(f"  {pl_icon} P/L Totale:  {'+' if stats['pl'] >= 0 else ''}{stats['pl']}u")
    print(f"  Scommesse:   {stats['bets']} ({stats['wins']}W / {stats['losses']}L / {stats['void']}V)")
    print(f"  Staked:       {stats['staked']}u")
    print(f"  HR:           {hr}%")
    print(f"  ROI:          {'+' if roi >= 0 else ''}{roi}%")
    print(f"  Pending:      {stats['pending']}")

    if stats['by_tipo']:
        print(f"\n  Per mercato:")
        for tipo, t in sorted(stats['by_tipo'].items()):
            t_hr = round((t['wins'] / t['bets']) * 100, 1) if t['bets'] > 0 else 0
            t_pl = round(t['pl'], 2)
            icon = '🟢' if t_pl >= 0 else '🔴'
            print(f"    {icon} {tipo:20s}  {'+' if t_pl >= 0 else ''}{t_pl:>8.2f}u  ({t['wins']}/{t['bets']} = {t_hr}%)")

    if stats['by_month']:
        print(f"\n  Per mese:")
        for month, m in sorted(stats['by_month'].items()):
            m_hr = round((m['wins'] / m['bets']) * 100, 1) if m['bets'] > 0 else 0
            m_pl = round(m['pl'], 2)
            icon = '🟢' if m_pl >= 0 else '🔴'
            print(f"    {icon} {month}  {'+' if m_pl >= 0 else ''}{m_pl:>8.2f}u  ({m['wins']}/{m['bets']} = {m_hr}%)")


# ==================== MAIN ====================

def main():
    parser = argparse.ArgumentParser(description='Confronto P/L: Backfill Dry-Run vs Produzione')
    parser.add_argument('--from', dest='date_from', help='Data inizio (YYYY-MM-DD)')
    parser.add_argument('--json', dest='json_path', help='Path al file JSON dry-run (default: log/backfill_dry_run.json)')
    args = parser.parse_args()

    # 1. Carica JSON dry-run
    json_path = args.json_path
    if not json_path:
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'log', 'backfill_dry_run.json')

    if not os.path.exists(json_path):
        print(f"❌ File non trovato: {json_path}")
        print(f"   Lancia prima: python orchestrate_experts.py --backfill START END --dry-run")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"CONFRONTO P/L: BACKFILL DRY-RUN vs PRODUZIONE")
    print(f"{'='*60}")

    print(f"\n  Caricamento pronostici dry-run da JSON...")
    with open(json_path, 'r', encoding='utf-8') as f:
        dry_docs = json.load(f)
    print(f"  {len(dry_docs)} documenti caricati")

    # Determina range date dal JSON
    dry_dates = sorted(set(d.get('date', '') for d in dry_docs if d.get('date')))
    if dry_dates:
        print(f"  Range: {dry_dates[0]} → {dry_dates[-1]}")

    # 2. Carica pronostici produzione dallo stesso range
    date_from = args.date_from or (dry_dates[0] if dry_dates else None)
    date_to = dry_dates[-1] if dry_dates else None

    if not date_from or not date_to:
        print("❌ Impossibile determinare le date dal JSON.")
        sys.exit(1)

    print(f"\n  Caricamento pronostici PRODUZIONE da MongoDB...")
    prod_docs = list(db.daily_predictions_unified.find(
        {'date': {'$gte': date_from, '$lte': date_to}},
        {'home': 1, 'away': 1, 'date': 1, 'pronostici': 1}
    ))
    print(f"  {len(prod_docs)} documenti caricati")

    # 3. Carica risultati reali
    print(f"\n  Caricamento risultati reali...")
    results_map = load_results_map()
    print(f"  {len(results_map)} risultati")

    # 4. Calcola P/L
    print(f"\n{'='*60}")

    dry_stats = calc_pl_from_docs(dry_docs, results_map, date_filter=date_from)
    prod_stats = calc_pl_from_docs(prod_docs, results_map, date_filter=date_from)

    print_stats("BACKFILL (nuovi pesi)", dry_stats)
    print_stats("PRODUZIONE (pesi attuali)", prod_stats)

    # 5. Confronto diretto
    delta_pl = round(dry_stats['pl'] - prod_stats['pl'], 2)
    delta_icon = '🟢' if delta_pl >= 0 else '🔴'

    print(f"\n{'='*60}")
    print(f"  CONFRONTO DIRETTO")
    print(f"  {'─'*50}")
    print(f"  {delta_icon} Delta P/L:  {'+' if delta_pl >= 0 else ''}{delta_pl}u")

    dry_hr = round((dry_stats['wins'] / dry_stats['bets']) * 100, 1) if dry_stats['bets'] > 0 else 0
    prod_hr = round((prod_stats['wins'] / prod_stats['bets']) * 100, 1) if prod_stats['bets'] > 0 else 0
    delta_hr = round(dry_hr - prod_hr, 1)
    print(f"  Delta HR:   {'+' if delta_hr >= 0 else ''}{delta_hr}pp ({dry_hr}% vs {prod_hr}%)")

    dry_roi = round((dry_stats['pl'] / dry_stats['staked']) * 100, 1) if dry_stats['staked'] > 0 else 0
    prod_roi = round((prod_stats['pl'] / prod_stats['staked']) * 100, 1) if prod_stats['staked'] > 0 else 0
    delta_roi = round(dry_roi - prod_roi, 1)
    print(f"  Delta ROI:  {'+' if delta_roi >= 0 else ''}{delta_roi}pp ({dry_roi}% vs {prod_roi}%)")

    print(f"\n  Bets: {dry_stats['bets']} (backfill) vs {prod_stats['bets']} (prod)")
    print(f"{'='*60}\n")

    if delta_pl > 0:
        print(f"  ✅ Il backfill avrebbe generato +{delta_pl}u in piu della produzione.")
    elif delta_pl < 0:
        print(f"  ⚠️  Il backfill avrebbe generato {delta_pl}u in meno della produzione.")
    else:
        print(f"  ➡️  Nessuna differenza.")


if __name__ == '__main__':
    main()
