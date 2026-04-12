"""Test copertura pattern bollette su pronostici di oggi."""
import os, sys, re
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions_python', 'ai_engine'))
from config import db
from datetime import datetime

today = datetime.now().strftime('%Y-%m-%d')
docs = list(db.daily_predictions_unified.find({'date': today}, {'pronostici': 1, 'league': 1}))

records = []
for d in docs:
    league = d.get('league', '')
    for p in d.get('pronostici', []):
        if not p.get('tipo'):
            continue
        records.append({
            'tipo': p.get('tipo', ''),
            'pronostico': p.get('pronostico', ''),
            'quota': p.get('quota', 0) or 0,
            'confidence': p.get('confidence', 0) or 0,
            'stars': p.get('stars', 0) or 0,
            'source': p.get('source', ''),
            'routing': p.get('routing_rule', ''),
            'stake': p.get('stake', 0) or 0,
            'edge': p.get('edge', 0) or 0,
            'elite': p.get('elite', False),
        })

print(f"Pronostici totali oggi ({today}): {len(records)}")

def match_b(r):
    t, q, c, s, src, rt, e, pr = r['tipo'], r['quota'], r['confidence'], r['stars'], r['source'], r['routing'], r['edge'], r['pronostico']
    if t == 'SEGNO' and 1.50 <= q < 1.80 and 60 <= c <= 69: return True
    if t == 'SEGNO' and 1.50 <= q < 1.80 and 80 <= c <= 100: return True
    if t == 'SEGNO' and 2.00 <= q < 2.50 and 70 <= c <= 79: return True
    if t == 'SEGNO' and 1.80 <= q < 2.00 and 4.0 <= s <= 4.5: return True
    if t == 'GOL' and 1.50 <= q < 1.80 and 80 <= c <= 100: return True
    if t == 'SEGNO' and 5 <= e <= 9: return True
    if t == 'GOL' and src == 'A+S_o25_s6_conv': return True
    if t == 'DOPPIA_CHANCE' and 1.40 <= q < 1.50 and c >= 60: return True
    if t == 'DOPPIA_CHANCE' and c >= 70 and s >= 3.5 and q < 1.60: return True
    if t == 'GOL' and c >= 85: return True
    if src == 'A+S_mg' and s >= 3.0: return True
    if t == 'DOPPIA_CHANCE' and rt == 'consensus_both' and s >= 3: return True
    if t == 'DOPPIA_CHANCE' and 1.40 <= q < 1.50 and src == 'A+S': return True
    if t == 'DOPPIA_CHANCE' and 1.40 <= q < 1.50 and src == 'C_combo96': return True
    if t == 'GOL' and 1.60 <= q < 1.80 and src == 'C_mg': return True
    if t == 'DOPPIA_CHANCE' and 1.40 <= q < 1.50 and s >= 3: return True
    if src == 'C_combo96' and s >= 3.0: return True
    if t == 'GOL' and 1.30 <= q < 1.40 and c >= 60: return True
    if t == 'DOPPIA_CHANCE' and rt == 'combo_96_dc_flip' and s >= 3: return True
    if t == 'DOPPIA_CHANCE' and 1.40 <= q < 1.50: return True
    if t == 'DOPPIA_CHANCE' and 1.40 <= q < 1.50 and src == 'C_screm': return True
    if t == 'SEGNO' and 1.60 <= q < 1.80 and s >= 3: return True
    if src == 'A' and s >= 3.0: return True
    if t == 'GOL' and c >= 70 and s >= 3.5 and q < 1.60: return True
    if t == 'GOL' and c >= 80 and s >= 3: return True
    if t == 'SEGNO' and e >= 20 and c >= 70: return True
    if t == 'SEGNO' and 1.80 <= q < 2.00 and c >= 70: return True
    if t == 'GOL' and rt == 'single' and s >= 3: return True
    if t == 'SEGNO' and s >= 4.0: return True
    if t == 'SEGNO' and 1.60 <= q < 1.80 and src == 'C': return True
    if pr == '1' and c >= 70: return True
    if t == 'SEGNO' and 2.00 <= q < 2.50 and c >= 70: return True
    if t == 'SEGNO' and 1.60 <= q < 1.80 and c >= 60: return True
    return False

def parse_hybrid_condition(cond_str, r):
    t, q, c, s, src, rt, st, pr = r['tipo'], r['quota'], r['confidence'], r['stars'], r['source'], r['routing'], r['stake'], r['pronostico']
    cs = cond_str.strip()
    m = re.match(r'conf(\d+)-(\d+)', cs)
    if m: return int(m.group(1)) <= c <= int(m.group(2))
    m = re.match(r'conf>=(\d+)', cs)
    if m: return c >= int(m.group(1))
    m = re.match(r'stelle([\d.]+)-([\d.]+)', cs)
    if m: return float(m.group(1)) <= s < float(m.group(2))
    m = re.match(r'stelle>=([\d.]+)', cs)
    if m: return s >= float(m.group(1))
    m = re.match(r'q([\d.]+)-([\d.]+)', cs)
    if m: return float(m.group(1)) <= q <= float(m.group(2)) + 0.001
    m = re.match(r'tipo=(.+)', cs)
    if m: return t == m.group(1)
    m = re.match(r'src=(.+)', cs)
    if m: return src == m.group(1)
    m = re.match(r'routing=(.+)', cs)
    if m: return rt == m.group(1)
    m = re.match(r'pron=(.+)', cs)
    if m: return pr == m.group(1)
    m = re.match(r'stake>=(\d+)', cs)
    if m: return st >= int(m.group(1))
    return False

# Carica hybrid
hybrid_patterns = []
hybrid_file = os.path.join(os.path.dirname(__file__), 'hybrid_75_by_profit.txt')
with open(hybrid_file, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line or line[0] not in '0123456789':
            continue
        parts = line.split()
        pat_parts = []
        for i, p in enumerate(parts[1:], 1):
            if p.startswith('+') or p.startswith('-'):
                try:
                    float(p)
                    break
                except:
                    pass
            pat_parts.append(p)
        pattern = ' '.join(pat_parts)
        conditions = [c.strip() for c in pattern.split('+')]
        hybrid_patterns.append(conditions)

print(f"Pattern hybrid caricati: {len(hybrid_patterns)}")

matched_b = 0
matched_h = 0
matched_any = 0

for r in records:
    b = match_b(r)
    h = any(all(parse_hybrid_condition(c, r) for c in conds) for conds in hybrid_patterns)
    if b or h:
        matched_any += 1
    if b:
        matched_b += 1
    if h:
        matched_h += 1

print(f"")
print(f"Match B1-B33:          {matched_b}/{len(records)}")
print(f"Match Hybrid:          {matched_h}/{len(records)}")
print(f"Match TOTALE (>=1):    {matched_any}/{len(records)} ({matched_any/len(records)*100:.0f}%)")
print(f"NON matchati:          {len(records) - matched_any}/{len(records)}")
