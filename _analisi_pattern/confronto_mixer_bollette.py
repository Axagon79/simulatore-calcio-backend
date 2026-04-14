"""
Confronto pattern Mixer (74) vs Bollette (183) a livello di pronostico.
Usa i dati reali dal 15/03/2026 per vedere quanti pronostici matchano entrambi, solo uno, o nessuno.
"""
import os, sys, re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

# --- Setup ---
base = os.path.dirname(os.path.abspath(__file__))
backend = os.path.join(base, "..")
sys.path.insert(0, os.path.join(backend, "functions_python", "ai_engine"))
load_dotenv(os.path.join(backend, "functions_python", "ai_engine", ".env"))

client = MongoClient(os.getenv("MONGO_URI"))
db = client["football_simulator_db"]
coll = db["daily_predictions_unified"]

# ======================== MIXER (74 pattern) ========================
def _check_mixer(p):
    tipo = p.get('tipo', '')
    quota = p.get('quota', 0) or 0
    confidence = p.get('confidence', 0) or 0
    stars = p.get('stars', 0) or 0
    source = p.get('source', '')
    pronostico = p.get('pronostico', '')
    routing = p.get('routing_rule', '')
    edge = p.get('edge', 0) or 0
    return {
        'conf50-59': 50 <= confidence <= 59,
        'conf60-69': 60 <= confidence <= 69,
        'conf70-79': 70 <= confidence <= 79,
        'q1.30-1.49': 1.30 <= quota <= 1.49,
        'q1.50-1.79': 1.50 <= quota <= 1.79,
        'q3.00-3.99': 3.00 <= quota <= 3.99,
        'src_C_screm': source == 'C_screm',
        'src_C': source == 'C',
        'route_scrematura': routing == 'scrematura_segno',
        'route_union': routing == 'union',
        'route_single': routing == 'single',
        'tipo_GOL': tipo == 'GOL',
        'tipo_SEGNO': tipo == 'SEGNO',
        'pron_Goal': pronostico == 'Goal',
        'pron_1': pronostico == '1',
        'st3.6-3.9': 3.6 <= stars <= 3.9,
        'edge20-50': 20 < edge <= 50,
        'edge50+': edge > 50,
    }

MIXER_PATTERNS = {
    'G01': {'conf50-59', 'src_C_screm'}, 'G02': {'conf50-59', 'q1.50-1.79'},
    'G03': {'pron_Goal', 'q1.30-1.49'}, 'G04': {'conf60-69', 'q1.30-1.49'},
    'G05': {'route_union'}, 'G06': {'pron_1', 'st3.6-3.9'},
    'G07': {'conf70-79', 'q1.50-1.79'}, 'G08': {'src_C_screm', 'route_scrematura'},
    'G09': {'src_C', 'st3.6-3.9'}, 'G10': {'edge20-50', 'q1.50-1.79'},
    'G11': {'conf60-69', 'edge50+'}, 'G12': {'conf60-69', 'src_C'},
    'G13': {'q3.00-3.99', 'route_single'}, 'G14': {'edge50+', 'tipo_SEGNO'},
    'H01': {'conf50-59', 'route_scrematura'}, 'H02': {'conf60-69', 'src_C_screm'},
    'H03': {'q1.30-1.49', 'src_C'}, 'H04': {'q1.30-1.49', 'st3.6-3.9'},
    'H05': {'route_union', 'tipo_GOL'}, 'H06': {'conf50-59', 'q1.50-1.79', 'src_C_screm'},
    'H07': {'conf50-59', 'q1.50-1.79', 'route_scrematura'},
    'H08': {'conf50-59', 'q1.50-1.79', 'tipo_GOL'},
    'H09': {'conf50-59', 'route_scrematura', 'src_C_screm'},
    'H10': {'conf50-59', 'src_C_screm', 'tipo_GOL'},
    'H11': {'conf50-59', 'route_scrematura', 'tipo_GOL'},
    'H12': {'conf60-69', 'q1.30-1.49', 'st3.6-3.9'},
    'H13': {'conf60-69', 'q1.50-1.79', 'route_single'},
    'H14': {'conf60-69', 'src_C_screm', 'tipo_GOL'},
    'H15': {'conf60-69', 'pron_1', 'src_C'},
    'H16': {'conf60-69', 'pron_1', 'route_single'},
    'H17': {'conf70-79', 'q1.30-1.49', 'src_C'},
    'H18': {'conf70-79', 'q1.30-1.49', 'st3.6-3.9'},
    'H19': {'conf70-79', 'edge20-50', 'pron_1'},
    'H20': {'q1.30-1.49', 'src_C', 'tipo_GOL'},
    'H21': {'pron_Goal', 'q1.30-1.49', 'src_C'},
    'H22': {'q1.30-1.49', 'src_C', 'st3.6-3.9'},
    'H23': {'pron_Goal', 'q1.30-1.49', 'tipo_GOL'},
    'H24': {'q1.30-1.49', 'st3.6-3.9', 'tipo_GOL'},
    'H25': {'pron_Goal', 'q1.30-1.49', 'st3.6-3.9'},
    'H26': {'q1.50-1.79', 'src_C_screm', 'tipo_GOL'},
    'H27': {'q1.50-1.79', 'route_scrematura', 'tipo_GOL'},
    'H28': {'edge20-50', 'q1.50-1.79', 'route_single'},
    'H29': {'edge20-50', 'q1.50-1.79', 'tipo_SEGNO'},
    'H30': {'edge20-50', 'pron_1', 'q1.50-1.79'},
    'H31': {'conf50-59', 'q1.50-1.79', 'route_scrematura', 'src_C_screm'},
    'H32': {'conf50-59', 'q1.50-1.79', 'src_C_screm', 'tipo_GOL'},
    'H33': {'conf50-59', 'q1.50-1.79', 'route_scrematura', 'tipo_GOL'},
    'H34': {'conf50-59', 'route_scrematura', 'src_C_screm', 'tipo_GOL'},
    'H35': {'conf60-69', 'q1.30-1.49', 'st3.6-3.9', 'tipo_GOL'},
    'H36': {'conf60-69', 'q1.50-1.79', 'route_single', 'src_C'},
    'H37': {'conf60-69', 'q1.50-1.79', 'src_C', 'tipo_SEGNO'},
    'H38': {'conf60-69', 'q1.50-1.79', 'route_single', 'tipo_SEGNO'},
    'H39': {'conf60-69', 'pron_1', 'route_single', 'src_C'},
    'H40': {'conf60-69', 'pron_1', 'src_C', 'tipo_SEGNO'},
    'H41': {'conf60-69', 'pron_1', 'route_single', 'tipo_SEGNO'},
    'H42': {'conf70-79', 'q1.30-1.49', 'src_C', 'tipo_GOL'},
    'H43': {'conf70-79', 'pron_Goal', 'q1.30-1.49', 'src_C'},
    'H44': {'conf70-79', 'q1.30-1.49', 'st3.6-3.9', 'tipo_GOL'},
    'H45': {'conf70-79', 'edge20-50', 'pron_1', 'src_C'},
    'H46': {'conf70-79', 'edge20-50', 'pron_1', 'route_single'},
    'H47': {'conf70-79', 'edge20-50', 'pron_1', 'tipo_SEGNO'},
    'H48': {'pron_Goal', 'q1.30-1.49', 'src_C', 'tipo_GOL'},
    'H49': {'q1.30-1.49', 'src_C', 'st3.6-3.9', 'tipo_GOL'},
    'H50': {'pron_Goal', 'q1.30-1.49', 'src_C', 'st3.6-3.9'},
    'H51': {'pron_Goal', 'q1.30-1.49', 'st3.6-3.9', 'tipo_GOL'},
    'H52': {'q1.50-1.79', 'route_scrematura', 'src_C_screm', 'tipo_GOL'},
    'H53': {'edge20-50', 'q1.50-1.79', 'route_single', 'src_C'},
    'H54': {'edge20-50', 'q1.50-1.79', 'src_C', 'tipo_SEGNO'},
    'H55': {'pron_1', 'q1.50-1.79', 'src_C', 'st3.6-3.9'},
    'H56': {'edge20-50', 'pron_1', 'q1.50-1.79', 'src_C'},
    'H57': {'edge20-50', 'q1.50-1.79', 'route_single', 'tipo_SEGNO'},
    'H58': {'pron_1', 'q1.50-1.79', 'route_single', 'st3.6-3.9'},
    'H59': {'edge20-50', 'pron_1', 'q1.50-1.79', 'route_single'},
    'H60': {'edge20-50', 'pron_1', 'q1.50-1.79', 'tipo_SEGNO'},
}

def is_mixer(p):
    if p.get('pronostico') == 'NO BET': return False
    flags = _check_mixer(p)
    return any(all(flags.get(c, False) for c in conds) for conds in MIXER_PATTERNS.values())

# ======================== BOLLETTE (33 base + 150 hybrid) ========================
def _match_b(sel):
    t = sel.get('tipo', '')
    q = sel.get('quota', 0) or 0
    c = sel.get('confidence', 0) or 0
    s = sel.get('stars', 0) or 0
    src = sel.get('source', '')
    rt = sel.get('routing_rule', '')
    e = sel.get('edge', 0) or 0
    pr = sel.get('pronostico', '')
    if t == "SEGNO" and 1.50 <= q < 1.80 and 60 <= c <= 69: return True
    if t == "SEGNO" and 1.50 <= q < 1.80 and 80 <= c <= 100: return True
    if t == "SEGNO" and 2.00 <= q < 2.50 and 70 <= c <= 79: return True
    if t == "SEGNO" and 1.80 <= q < 2.00 and 4.0 <= s <= 4.5: return True
    if t == "GOL" and 1.50 <= q < 1.80 and 80 <= c <= 100: return True
    if t == "SEGNO" and 5 <= e <= 9: return True
    if t == "GOL" and src == "A+S_o25_s6_conv": return True
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50 and c >= 60: return True
    if t == "DOPPIA_CHANCE" and c >= 70 and s >= 3.5 and q < 1.60: return True
    if t == "GOL" and c >= 85: return True
    if src == "A+S_mg" and s >= 3.0: return True
    if t == "DOPPIA_CHANCE" and rt == "consensus_both" and s >= 3: return True
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50 and src == "A+S": return True
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50 and src == "C_combo96": return True
    if t == "GOL" and 1.60 <= q < 1.80 and src == "C_mg": return True
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50 and s >= 3: return True
    if src == "C_combo96" and s >= 3.0: return True
    if t == "GOL" and 1.30 <= q < 1.40 and c >= 60: return True
    if t == "DOPPIA_CHANCE" and rt == "combo_96_dc_flip" and s >= 3: return True
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50: return True
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50 and src == "C_screm": return True
    if t == "SEGNO" and 1.60 <= q < 1.80 and s >= 3: return True
    if src == "A" and s >= 3.0: return True
    if t == "GOL" and c >= 70 and s >= 3.5 and q < 1.60: return True
    if t == "GOL" and c >= 80 and s >= 3: return True
    if t == "SEGNO" and e >= 20 and c >= 70: return True
    if t == "SEGNO" and 1.80 <= q < 2.00 and c >= 70: return True
    if t == "GOL" and rt == "single" and s >= 3: return True
    if t == "SEGNO" and s >= 4.0: return True
    if t == "SEGNO" and 1.60 <= q < 1.80 and src == "C": return True
    if pr == "1" and c >= 70: return True
    if t == "SEGNO" and 2.00 <= q < 2.50 and c >= 70: return True
    if t == "SEGNO" and 1.60 <= q < 1.80 and c >= 60: return True
    return False

def _check_hybrid_cond(cs, sel):
    t = sel.get('tipo', '')
    q = sel.get('quota', 0) or 0
    c = sel.get('confidence', 0) or 0
    s = sel.get('stars', 0) or 0
    src = sel.get('source', '')
    rt = sel.get('routing_rule', '')
    st = sel.get('stake', 0) or 0
    pr = sel.get('pronostico', '')
    cs = cs.strip()
    m = re.match(r"conf(\d+)-(\d+)", cs)
    if m: return int(m.group(1)) <= c <= int(m.group(2))
    m = re.match(r"conf>=(\d+)", cs)
    if m: return c >= int(m.group(1))
    m = re.match(r"stelle([\d.]+)-([\d.]+)", cs)
    if m: return float(m.group(1)) <= s < float(m.group(2))
    m = re.match(r"stelle>=([\d.]+)", cs)
    if m: return s >= float(m.group(1))
    m = re.match(r"q([\d.]+)-([\d.]+)", cs)
    if m: return float(m.group(1)) <= q <= float(m.group(2)) + 0.001
    m = re.match(r"tipo=(.+)", cs)
    if m: return t == m.group(1)
    m = re.match(r"src=(.+)", cs)
    if m: return src == m.group(1)
    m = re.match(r"routing=(.+)", cs)
    if m: return rt == m.group(1)
    m = re.match(r"pron=(.+)", cs)
    if m: return pr == m.group(1)
    m = re.match(r"stake>=(\d+)", cs)
    if m: return st >= int(m.group(1))
    return False

# Carica 150 hybrid
_HYBRID = []
hybrid_file = os.path.join(base, "hybrid_75_by_profit.txt")
if os.path.exists(hybrid_file):
    with open(hybrid_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line[0] not in "0123456789": continue
            parts = line.split()
            pat_parts = []
            for pp in parts[1:]:
                if pp.startswith("+") or pp.startswith("-"):
                    try: float(pp); break
                    except ValueError: pass
                pat_parts.append(pp)
            pattern = " ".join(pat_parts)
            _HYBRID.append([c.strip() for c in pattern.split("+")])
    print(f"Caricati {len(_HYBRID)} pattern hybrid bollette")

def is_bollette(sel):
    if sel.get('pronostico') == 'NO BET': return False
    if _match_b(sel): return True
    for conds in _HYBRID:
        if all(_check_hybrid_cond(c, sel) for c in conds): return True
    return False

# ======================== ANALISI CON HR e P/L ========================
start = datetime(2026, 3, 15)
end = datetime(2026, 4, 13)
dates = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((end - start).days + 1)]

print(f"\n=== CONFRONTO MIXER vs BOLLETTE — {start.strftime('%d/%m')} -> {end.strftime('%d/%m/%Y')} ===\n")

# Categorie: entrambi, solo_mixer, solo_bollette, nessuno
stats = {
    "entrambi":      {"v": 0, "p": 0, "nd": 0, "pl": 0.0},
    "solo_mixer":    {"v": 0, "p": 0, "nd": 0, "pl": 0.0},
    "solo_bollette": {"v": 0, "p": 0, "nd": 0, "pl": 0.0},
    "nessuno":       {"v": 0, "p": 0, "nd": 0, "pl": 0.0},
}
tot = 0

for date in dates:
    docs = list(coll.find({"date": date}, {"pronostici": 1}))
    for doc in docs:
        for p in doc.get("pronostici", []):
            if p.get("pronostico") == "NO BET": continue
            tot += 1
            m = is_mixer(p)
            b = is_bollette(p)
            if m and b: cat = "entrambi"
            elif m and not b: cat = "solo_mixer"
            elif not m and b: cat = "solo_bollette"
            else: cat = "nessuno"

            esito = p.get("esito")  # True/False o None
            pl_val = p.get("profit_loss")

            if esito is True:
                stats[cat]["v"] += 1
                stats[cat]["pl"] += (pl_val or 0)
            elif esito is False:
                stats[cat]["p"] += 1
                stats[cat]["pl"] += (pl_val or 0)
            else:
                stats[cat]["nd"] += 1

def print_cat(label, s):
    n = s["v"] + s["p"]
    if n == 0:
        print(f"  {label:25s}  N={s['v']+s['p']+s['nd']:>4}  (nessun esito)")
        return
    hr = s["v"] / n * 100
    pl = s["pl"]
    yld = pl / n * 100 if n else 0
    print(f"  {label:25s}  V={s['v']:>3}  P={s['p']:>3}  N={n:>4}  HR={hr:5.1f}%  P/L={pl:+8.2f}u  Yield={yld:+5.1f}%  (nd={s['nd']})")

print(f"Pronostici totali (no NO BET): {tot}\n")
print_cat("Entrambi (Mix+Bol)", stats["entrambi"])
print_cat("Solo Mixer", stats["solo_mixer"])
print_cat("Solo Bollette", stats["solo_bollette"])
print_cat("Nessuno dei due", stats["nessuno"])

# Totali aggregati
mix_tot = {k: stats["entrambi"][k] + stats["solo_mixer"][k] for k in stats["entrambi"]}
bol_tot = {k: stats["entrambi"][k] + stats["solo_bollette"][k] for k in stats["entrambi"]}
print()
print_cat("TOTALE Mixer", mix_tot)
print_cat("TOTALE Bollette", bol_tot)

# ======================== DETTAGLIO "SOLO BOLLETTE" ========================
# Per ogni pronostico solo-bollette, mostra quale pattern B/hybrid matcha e il suo esito
print("\n\n=== DETTAGLIO SOLO BOLLETTE — quali pattern B matchano e come vanno ===\n")

# Traccia per ogni pattern B quanti V/P/PL
from collections import defaultdict
b_stats = defaultdict(lambda: {"v": 0, "p": 0, "pl": 0.0, "desc": ""})

B_PATTERNS = {
    "B01": ("SEGNO q1.50-1.79 conf60-69", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and 1.50<=q<1.80 and 60<=c<=69),
    "B02": ("SEGNO q1.50-1.79 conf80-100", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and 1.50<=q<1.80 and 80<=c<=100),
    "B03": ("SEGNO q2.00-2.49 conf70-79", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and 2.00<=q<2.50 and 70<=c<=79),
    "B04": ("SEGNO q1.80-1.99 st4-4.5", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and 1.80<=q<2.00 and 4.0<=s<=4.5),
    "B05": ("GOL q1.50-1.79 conf80-100", lambda t,q,c,s,src,rt,e,pr: t=="GOL" and 1.50<=q<1.80 and 80<=c<=100),
    "B06": ("SEGNO edge5-9", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and 5<=e<=9),
    "B07": ("GOL src=A+S_o25_s6_conv", lambda t,q,c,s,src,rt,e,pr: t=="GOL" and src=="A+S_o25_s6_conv"),
    "B08": ("DC q1.40-1.49 conf>=60", lambda t,q,c,s,src,rt,e,pr: t=="DOPPIA_CHANCE" and 1.40<=q<1.50 and c>=60),
    "B09": ("DC conf>=70 st>=3.5 q<1.60", lambda t,q,c,s,src,rt,e,pr: t=="DOPPIA_CHANCE" and c>=70 and s>=3.5 and q<1.60),
    "B10": ("GOL conf>=85", lambda t,q,c,s,src,rt,e,pr: t=="GOL" and c>=85),
    "B11": ("src=A+S_mg st>=3", lambda t,q,c,s,src,rt,e,pr: src=="A+S_mg" and s>=3.0),
    "B12": ("DC consensus_both st>=3", lambda t,q,c,s,src,rt,e,pr: t=="DOPPIA_CHANCE" and rt=="consensus_both" and s>=3),
    "B13": ("DC q1.40-1.49 src=A+S", lambda t,q,c,s,src,rt,e,pr: t=="DOPPIA_CHANCE" and 1.40<=q<1.50 and src=="A+S"),
    "B14": ("DC q1.40-1.49 src=C_combo96", lambda t,q,c,s,src,rt,e,pr: t=="DOPPIA_CHANCE" and 1.40<=q<1.50 and src=="C_combo96"),
    "B15": ("GOL q1.60-1.79 src=C_mg", lambda t,q,c,s,src,rt,e,pr: t=="GOL" and 1.60<=q<1.80 and src=="C_mg"),
    "B16": ("DC q1.40-1.49 st>=3", lambda t,q,c,s,src,rt,e,pr: t=="DOPPIA_CHANCE" and 1.40<=q<1.50 and s>=3),
    "B17": ("src=C_combo96 st>=3", lambda t,q,c,s,src,rt,e,pr: src=="C_combo96" and s>=3.0),
    "B18": ("GOL q1.30-1.39 conf>=60", lambda t,q,c,s,src,rt,e,pr: t=="GOL" and 1.30<=q<1.40 and c>=60),
    "B19": ("DC combo_96_dc_flip st>=3", lambda t,q,c,s,src,rt,e,pr: t=="DOPPIA_CHANCE" and rt=="combo_96_dc_flip" and s>=3),
    "B20": ("DC q1.40-1.49", lambda t,q,c,s,src,rt,e,pr: t=="DOPPIA_CHANCE" and 1.40<=q<1.50),
    "B21": ("DC q1.40-1.49 src=C_screm", lambda t,q,c,s,src,rt,e,pr: t=="DOPPIA_CHANCE" and 1.40<=q<1.50 and src=="C_screm"),
    "B22": ("SEGNO q1.60-1.79 st>=3", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and 1.60<=q<1.80 and s>=3),
    "B23": ("src=A st>=3", lambda t,q,c,s,src,rt,e,pr: src=="A" and s>=3.0),
    "B24": ("GOL conf>=70 st>=3.5 q<1.60", lambda t,q,c,s,src,rt,e,pr: t=="GOL" and c>=70 and s>=3.5 and q<1.60),
    "B25": ("GOL conf>=80 st>=3", lambda t,q,c,s,src,rt,e,pr: t=="GOL" and c>=80 and s>=3),
    "B26": ("SEGNO edge>=20 conf>=70", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and e>=20 and c>=70),
    "B27": ("SEGNO q1.80-1.99 conf>=70", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and 1.80<=q<2.00 and c>=70),
    "B28": ("GOL single st>=3", lambda t,q,c,s,src,rt,e,pr: t=="GOL" and rt=="single" and s>=3),
    "B29": ("SEGNO st>=4", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and s>=4.0),
    "B30": ("SEGNO q1.60-1.79 src=C", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and 1.60<=q<1.80 and src=="C"),
    "B31": ("pron=1 conf>=70", lambda t,q,c,s,src,rt,e,pr: pr=="1" and c>=70),
    "B32": ("SEGNO q2.00-2.49 conf>=70", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and 2.00<=q<2.50 and c>=70),
    "B33": ("SEGNO q1.60-1.79 conf>=60", lambda t,q,c,s,src,rt,e,pr: t=="SEGNO" and 1.60<=q<1.80 and c>=60),
}

# Per i 150 hybrid, serve un indice
hybrid_stats = defaultdict(lambda: {"v": 0, "p": 0, "pl": 0.0, "desc": ""})

for date in dates:
    docs = list(coll.find({"date": date}, {"pronostici": 1}))
    for doc in docs:
        for p in doc.get("pronostici", []):
            if p.get("pronostico") == "NO BET": continue
            if is_mixer(p): continue  # solo quelli che NON sono mixer
            if not is_bollette(p): continue  # e che SONO bollette

            t = p.get('tipo', '')
            q = p.get('quota', 0) or 0
            c = p.get('confidence', 0) or 0
            s = p.get('stars', 0) or 0
            src = p.get('source', '')
            rt = p.get('routing_rule', '')
            e = p.get('edge', 0) or 0
            pr = p.get('pronostico', '')
            esito = p.get("esito")
            pl_val = p.get("profit_loss", 0) or 0

            # Check B1-B33
            for bid, (desc, fn) in B_PATTERNS.items():
                if fn(t, q, c, s, src, rt, e, pr):
                    b_stats[bid]["desc"] = desc
                    if esito is True:
                        b_stats[bid]["v"] += 1
                        b_stats[bid]["pl"] += pl_val
                    elif esito is False:
                        b_stats[bid]["p"] += 1
                        b_stats[bid]["pl"] += pl_val

            # Check hybrid
            for i, conds in enumerate(_HYBRID):
                if all(_check_hybrid_cond(cc, p) for cc in conds):
                    hid = f"HYB_{i+1:03d}"
                    hybrid_stats[hid]["desc"] = " + ".join(conds)
                    if esito is True:
                        hybrid_stats[hid]["v"] += 1
                        hybrid_stats[hid]["pl"] += pl_val
                    elif esito is False:
                        hybrid_stats[hid]["p"] += 1
                        hybrid_stats[hid]["pl"] += pl_val

print("--- Pattern B (base) che catturano SOLO bollette (non mixer) ---")
for bid in sorted(b_stats.keys()):
    s = b_stats[bid]
    n = s["v"] + s["p"]
    if n == 0: continue
    hr = s["v"] / n * 100
    print(f"  {bid} {s['desc']:40s}  V={s['v']:>2} P={s['p']:>2} N={n:>3} HR={hr:5.1f}% PL={s['pl']:+7.2f}u")

print(f"\n--- Pattern Hybrid che catturano SOLO bollette (non mixer) ---")
salvabili = []
for hid in sorted(hybrid_stats.keys()):
    s = hybrid_stats[hid]
    n = s["v"] + s["p"]
    if n == 0: continue
    hr = s["v"] / n * 100
    if hr >= 70 and s["pl"] > 0:
        salvabili.append((hid, s))
    print(f"  {hid} {s['desc']:55s}  V={s['v']:>2} P={s['p']:>2} N={n:>3} HR={hr:5.1f}% PL={s['pl']:+7.2f}u")

if salvabili:
    print(f"\n=== PATTERN SALVABILI (HR>=70% e PL>0, solo nella zona 'solo bollette') ===")
    for hid, s in salvabili:
        n = s["v"] + s["p"]
        hr = s["v"] / n * 100
        print(f"  {hid} {s['desc']:55s}  V={s['v']:>2} P={s['p']:>2} HR={hr:5.1f}% PL={s['pl']:+7.2f}u")
else:
    print("\n  Nessun pattern hybrid salvabile (HR>=70% e PL>0)")

client.close()
