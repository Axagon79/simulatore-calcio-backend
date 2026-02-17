"""
ANALISI ESCLUSIONE — Breakdown completo per trovare criteri di filtro
=====================================================================
Script SOLA LETTURA. Analizza i 474 pronostici (esclusi XF/RE) per trovare
quali perdono soldi e stabilire criteri di esclusione.

Dimensioni analizzate:
1. Per TIPO (SEGNO, DC, GOL)
2. Per SOTTO-TIPO (1, 2, X, 1X, X2, Over 2.5, Under 2.5, Goal, NoGoal, etc.)
3. Per FASCIA di CONFIDENCE (probabilita_stimata)
4. Per FASCIA di QUOTA
5. Per AVG segnali (media dei punteggi nel dettaglio)
6. Cross: tipo × fascia confidence
7. Cross: sotto-tipo × fascia quota
"""

import os, sys, re
from datetime import datetime
from collections import defaultdict

current_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'functions_python', 'ai_engine')
sys.path.insert(0, current_path)
from config import db

today = datetime.now().strftime('%Y-%m-%d')
docs = list(db.daily_predictions.find({'date': {'$lt': today}}))

print(f"\n{'='*80}")
print(f" ANALISI ESCLUSIONE — Trova pattern dei pronostici perdenti")
print(f"{'='*80}")
print(f" Documenti: {len(docs)} | Data: {today}\n")


# ==================== RACCOLTA DATI ====================

pronostici = []

for doc in docs:
    date = doc.get('date', '')
    home = doc.get('home', '')
    away = doc.get('away', '')
    odds = doc.get('odds', {})
    segno_det = doc.get('segno_dettaglio', {})
    gol_det = doc.get('gol_dettaglio', {})
    league = doc.get('league', doc.get('campionato', '?'))

    for p in doc.get('pronostici', []):
        tipo = p.get('tipo', '?')

        # Skip X_FACTOR e RISULTATO_ESATTO
        if p.get('is_x_factor') or p.get('is_exact_score') or tipo in ('X_FACTOR', 'RISULTATO_ESATTO'):
            continue

        pronostico = p.get('pronostico', '')
        quota = p.get('quota')
        confidence = p.get('probabilita_stimata', 0)
        edge = p.get('edge', 0)
        stake = p.get('stake', 0)
        esito = p.get('esito')
        pl = p.get('profit_loss')

        # Calcola avg dei segnali
        det = segno_det if tipo in ('SEGNO', 'DOPPIA_CHANCE') else gol_det
        scores = [v for v in det.values() if isinstance(v, (int, float))]
        avg = sum(scores) / len(scores) if scores else 0

        pronostici.append({
            'date': date,
            'match': f"{home} vs {away}",
            'league': league,
            'tipo': tipo,
            'pronostico': pronostico,
            'quota': quota or 0,
            'confidence': confidence,
            'edge': edge or 0,
            'stake': stake or 0,
            'esito': esito,
            'pl': pl if pl is not None else 0,
            'avg_segnali': avg,
            'has_result': esito is not None,
        })

# Solo quelli con risultato (escludi pending)
con_risultato = [p for p in pronostici if p['has_result']]
pending = [p for p in pronostici if not p['has_result']]

print(f" Pronostici totali: {len(pronostici)}")
print(f" Con risultato: {len(con_risultato)} | Pending: {len(pending)}")
print(f" Vinti: {sum(1 for p in con_risultato if p['esito'] == True)} | Persi: {sum(1 for p in con_risultato if p['esito'] == False)}")
print(f" HR globale: {sum(1 for p in con_risultato if p['esito'] == True) / len(con_risultato) * 100:.1f}%")


# ==================== HELPER ====================

def stampa_breakdown(titolo, gruppi):
    """Stampa breakdown con HR, P/L, yield per ogni gruppo"""
    print(f"\n{'='*80}")
    print(f" {titolo}")
    print(f"{'='*80}")
    print(f" {'Gruppo':<28} {'Tot':>5} {'V':>4} {'P':>4} {'HR%':>6} {'P/L':>8} {'Stake':>6} {'Yield':>7} {'AvgQ':>6}")
    print(f" {'-'*28} {'-'*5} {'-'*4} {'-'*4} {'-'*6} {'-'*8} {'-'*6} {'-'*7} {'-'*6}")

    totale_v = 0
    totale_p = 0
    totale_pl = 0
    totale_stake = 0

    for nome, items in sorted(gruppi.items()):
        if not items:
            continue
        v = sum(1 for x in items if x['esito'] == True)
        p = sum(1 for x in items if x['esito'] == False)
        tot = v + p
        if tot == 0:
            continue
        hr = v / tot * 100
        pl = sum(x['pl'] for x in items if x['has_result'])
        stk = sum(x['stake'] for x in items if x['has_result'])
        yld = (pl / stk * 100) if stk > 0 else 0
        avg_q = sum(x['quota'] for x in items if x['quota'] > 0) / max(1, sum(1 for x in items if x['quota'] > 0))

        marker = ' <<<' if yld < -10 else (' !!!' if yld > 5 else '')
        print(f" {nome:<28} {tot:>5} {v:>4} {p:>4} {hr:>5.1f}% {pl:>+7.2f}u {stk:>5}u {yld:>+6.1f}%{marker}")

        totale_v += v
        totale_p += p
        totale_pl += pl
        totale_stake += stk

    tot = totale_v + totale_p
    hr = totale_v / tot * 100 if tot > 0 else 0
    yld = (totale_pl / totale_stake * 100) if totale_stake > 0 else 0
    print(f" {'-'*28} {'-'*5} {'-'*4} {'-'*4} {'-'*6} {'-'*8} {'-'*6} {'-'*7}")
    print(f" {'TOTALE':<28} {tot:>5} {totale_v:>4} {totale_p:>4} {hr:>5.1f}% {totale_pl:>+7.2f}u {totale_stake:>5}u {yld:>+6.1f}%")


# ==================== 1. PER TIPO ====================

gruppi_tipo = defaultdict(list)
for p in pronostici:
    gruppi_tipo[p['tipo']].append(p)
stampa_breakdown("1. BREAKDOWN PER TIPO", gruppi_tipo)


# ==================== 2. PER SOTTO-TIPO ====================

gruppi_sotto = defaultdict(list)
for p in pronostici:
    label = f"{p['tipo']}: {p['pronostico']}"
    gruppi_sotto[label].append(p)
stampa_breakdown("2. BREAKDOWN PER SOTTO-TIPO (pronostico specifico)", gruppi_sotto)


# ==================== 3. PER FASCIA CONFIDENCE ====================

def fascia_confidence(c):
    if c < 40: return '< 40%'
    if c < 45: return '40-44%'
    if c < 50: return '45-49%'
    if c < 55: return '50-54%'
    if c < 60: return '55-59%'
    if c < 65: return '60-64%'
    if c < 70: return '65-69%'
    if c < 75: return '70-74%'
    return '>= 75%'

gruppi_conf = defaultdict(list)
for p in pronostici:
    gruppi_conf[fascia_confidence(p['confidence'])].append(p)
stampa_breakdown("3. BREAKDOWN PER FASCIA CONFIDENCE", gruppi_conf)


# ==================== 4. PER FASCIA QUOTA ====================

def fascia_quota(q):
    if q <= 0: return 'No quota'
    if q < 1.30: return '< 1.30'
    if q < 1.50: return '1.30-1.49'
    if q < 1.70: return '1.50-1.69'
    if q < 1.90: return '1.70-1.89'
    if q < 2.10: return '1.90-2.09'
    if q < 2.50: return '2.10-2.49'
    if q < 3.00: return '2.50-2.99'
    return '>= 3.00'

gruppi_quota = defaultdict(list)
for p in pronostici:
    gruppi_quota[fascia_quota(p['quota'])].append(p)
stampa_breakdown("4. BREAKDOWN PER FASCIA QUOTA", gruppi_quota)


# ==================== 5. PER AVG SEGNALI ====================

def fascia_avg(a):
    if a < 50: return '< 50'
    if a < 55: return '50-54'
    if a < 58: return '55-57'
    if a < 60: return '58-59'
    if a < 62: return '60-61'
    if a < 65: return '62-64'
    if a < 68: return '65-67'
    if a < 70: return '68-69'
    return '>= 70'

gruppi_avg = defaultdict(list)
for p in pronostici:
    gruppi_avg[fascia_avg(p['avg_segnali'])].append(p)
stampa_breakdown("5. BREAKDOWN PER AVG SEGNALI (media score dettaglio)", gruppi_avg)


# ==================== 6. CROSS: TIPO × CONFIDENCE ====================

gruppi_cross = defaultdict(list)
for p in pronostici:
    label = f"{p['tipo']:>5} | {fascia_confidence(p['confidence'])}"
    gruppi_cross[label].append(p)
stampa_breakdown("6. CROSS: TIPO × CONFIDENCE", gruppi_cross)


# ==================== 7. CROSS: TIPO × AVG SEGNALI ====================

gruppi_cross2 = defaultdict(list)
for p in pronostici:
    label = f"{p['tipo']:>5} | avg {fascia_avg(p['avg_segnali'])}"
    gruppi_cross2[label].append(p)
stampa_breakdown("7. CROSS: TIPO × AVG SEGNALI", gruppi_cross2)


# ==================== 8. SEGNO: pronostico × quota ====================

gruppi_segno_q = defaultdict(list)
for p in pronostici:
    if p['tipo'] == 'SEGNO':
        label = f"SEGNO {p['pronostico']} @ {fascia_quota(p['quota'])}"
        gruppi_segno_q[label].append(p)
stampa_breakdown("8. SEGNO: pronostico × fascia quota", gruppi_segno_q)


# ==================== 9. TOP/BOTTOM pronostici ====================

print(f"\n{'='*80}")
print(f" 9. TOP 15 PRONOSTICI PIU' PROFITTEVOLI (con risultato)")
print(f"{'='*80}")
sorted_by_pl = sorted([p for p in con_risultato if p['pl'] is not None], key=lambda x: x['pl'], reverse=True)
for i, p in enumerate(sorted_by_pl[:15]):
    emoji = 'V' if p['esito'] else 'X'
    print(f" {i+1:>2}. [{emoji}] {p['date']} {p['match']}")
    print(f"     {p['tipo']} → {p['pronostico']} @{p['quota']:.2f} | conf={p['confidence']}% | avg={p['avg_segnali']:.1f} | S:{p['stake']} → P/L:{p['pl']:+.2f}u")

print(f"\n{'='*80}")
print(f" 10. BOTTOM 15 PRONOSTICI PIU' PERDENTI (con risultato)")
print(f"{'='*80}")
for i, p in enumerate(sorted_by_pl[-15:]):
    emoji = 'V' if p['esito'] else 'X'
    print(f" {i+1:>2}. [{emoji}] {p['date']} {p['match']}")
    print(f"     {p['tipo']} → {p['pronostico']} @{p['quota']:.2f} | conf={p['confidence']}% | avg={p['avg_segnali']:.1f} | S:{p['stake']} → P/L:{p['pl']:+.2f}u")


# ==================== 11. SIMULAZIONE ESCLUSIONI ====================

print(f"\n{'='*80}")
print(f" 11. SIMULAZIONE ESCLUSIONI — Cosa succede se escludiamo?")
print(f"{'='*80}\n")

esclusioni = [
    ("Nessuna (baseline)", lambda p: True),
    ("Escludi edge < 0%", lambda p: p['edge'] >= 0),
    ("Escludi edge < 2%", lambda p: p['edge'] >= 2),
    ("Escludi edge < 5%", lambda p: p['edge'] >= 5),
    ("Escludi confidence < 45%", lambda p: p['confidence'] >= 45),
    ("Escludi confidence < 50%", lambda p: p['confidence'] >= 50),
    ("Escludi avg < 55", lambda p: p['avg_segnali'] >= 55),
    ("Escludi avg < 58", lambda p: p['avg_segnali'] >= 58),
    ("Escludi avg < 60", lambda p: p['avg_segnali'] >= 60),
    ("Escludi SEGNO con quota < 1.50", lambda p: not (p['tipo'] == 'SEGNO' and p['quota'] < 1.50 and p['quota'] > 0)),
    ("Escludi SEGNO con quota < 1.70", lambda p: not (p['tipo'] == 'SEGNO' and p['quota'] < 1.70 and p['quota'] > 0)),
    ("Escludi DC (tutte)", lambda p: p['tipo'] != 'DOPPIA_CHANCE'),
    ("Escludi SEGNO X", lambda p: not (p['tipo'] == 'SEGNO' and p['pronostico'] == 'X')),
    ("Escludi edge<0 + avg<55", lambda p: p['edge'] >= 0 and p['avg_segnali'] >= 55),
    ("Escludi edge<0 + avg<58", lambda p: p['edge'] >= 0 and p['avg_segnali'] >= 58),
    ("Combo: edge>=0 + conf>=45 + avg>=55", lambda p: p['edge'] >= 0 and p['confidence'] >= 45 and p['avg_segnali'] >= 55),
    ("Combo: edge>=0 + conf>=50 + avg>=58", lambda p: p['edge'] >= 0 and p['confidence'] >= 50 and p['avg_segnali'] >= 58),
]

print(f" {'Criterio':<42} {'N':>4} {'V':>4} {'P':>4} {'HR%':>6} {'P/L':>8} {'Stk':>5} {'Yield':>7}")
print(f" {'-'*42} {'-'*4} {'-'*4} {'-'*4} {'-'*6} {'-'*8} {'-'*5} {'-'*7}")

for nome, filtro in esclusioni:
    filtered = [p for p in con_risultato if filtro(p)]
    if not filtered:
        print(f" {nome:<42} {'vuoto':>4}")
        continue
    v = sum(1 for x in filtered if x['esito'] == True)
    p = sum(1 for x in filtered if x['esito'] == False)
    tot = v + p
    hr = v / tot * 100 if tot > 0 else 0
    pl = sum(x['pl'] for x in filtered)
    stk = sum(x['stake'] for x in filtered)
    yld = (pl / stk * 100) if stk > 0 else 0
    marker = ' <<<' if yld < -5 else (' ***' if yld > 0 else '')
    print(f" {nome:<42} {tot:>4} {v:>4} {p:>4} {hr:>5.1f}% {pl:>+7.2f}u {stk:>4}u {yld:>+6.1f}%{marker}")


print(f"\n{'='*80}")
print(f" ANALISI COMPLETATA — Nessuna modifica al DB")
print(f"{'='*80}\n")
