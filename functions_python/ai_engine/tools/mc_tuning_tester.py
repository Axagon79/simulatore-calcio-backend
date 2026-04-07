"""
MC TUNING TESTER — Test parametri Monte Carlo senza toccare MongoDB
===================================================================
Simula partite con parametri custom in RAM, confronta con originali e realtà.
Alla fine permette di salvare su MongoDB, su file locale, o scartare.

Uso: cd functions_python/ai_engine && python tools/mc_tuning_tester.py
"""

import sys
import os
import re
import json
import copy
import time
import contextlib
import numpy as np
from datetime import datetime, timedelta
from collections import Counter

# Setup path
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from config import db
from engine.engine_core import predict_match, preload_match_data, WEIGHTS_CACHE
from engine.goals_converter import calculate_goals_from_engine, load_tuning
import ai_engine.calculators.bulk_manager_c as bulk_manager_c

ALGO_MODE = 6
PRESETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'presets')
os.makedirs(PRESETS_DIR, exist_ok=True)

h2h_collection = db['h2h_by_round']


# ==================== SUPPRESS STDOUT ====================
@contextlib.contextmanager
def suppress_stdout():
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old_out = sys.stdout
        old_err = sys.stderr
        sys.stdout = devnull
        sys.stderr = devnull
        try:
            yield
        finally:
            sys.stdout = old_out
            sys.stderr = old_err


# ==================== DEFINIZIONE PARAMETRI ====================

PARAM_DEFS = [
    # BLOCCO A — Parametri GOL diretti
    {
        'key': 'DIVISORE_MEDIA_GOL',
        'blocco': 'A',
        'weight_key': None,  # Non è un peso WEIGHTS_CACHE
        'nome': 'Divisore Media Gol',
        'desc': 'Divide il volume offensivo base. Più basso = più gol per tutti.',
        'su': 'Meno gol, partite più chiuse (0-0, 1-0)',
        'giu': 'Più gol, partite più aperte (2-1, 3-1)',
    },
    {
        'key': 'IMPATTO_DIFESA_TATTICA',
        'blocco': 'A',
        'weight_key': None,
        'nome': 'Impatto Difesa Tattica',
        'desc': 'Quanto le difese frenano i gol. Più alto = difese più forti.',
        'su': 'Difese dominano, pochi gol',
        'giu': 'Difese bucate, più gol per tutti',
    },
    {
        'key': 'POTENZA_FAVORITA_WINSHIFT',
        'blocco': 'A',
        'weight_key': None,
        'nome': 'Potenza Favorita (Win Shift)',
        'desc': 'Quanto il favorito "ruba" gol all\'avversario.',
        'su': 'Il favorito segna molto, l\'altro quasi nulla (3-0, 4-0)',
        'giu': 'Partite più equilibrate (1-1, 2-1)',
    },
    {
        'key': 'TETTO_MAX_GOL_ATTESI',
        'blocco': 'A',
        'weight_key': None,
        'nome': 'Tetto Massimo Gol Attesi',
        'desc': 'Limite massimo lambda per squadra. Sicurezza anti-risultati assurdi.',
        'su': 'Permette partite con molti gol (4-3, 5-2)',
        'giu': 'Blocca risultati alti, max ~3 gol a squadra',
    },
    # BLOCCO B — Pesi fattori
    {
        'key': 'PESO_RATING_ROSA',
        'blocco': 'B',
        'weight_key': 'RATING',
        'nome': 'Peso Rating Rosa',
        'desc': 'Quanto conta la qualità della rosa (valore Transfermarkt).',
        'su': 'Squadre forti dominano di più → più 2-0, 3-0',
        'giu': 'Rosa conta meno → risultati più imprevedibili',
    },
    {
        'key': 'PESO_FORMA_RECENTE',
        'blocco': 'B',
        'weight_key': 'LUCIFERO',
        'nome': 'Peso Forma Recente',
        'desc': 'Quanto conta la forma recente (ultime partite).',
        'su': 'Squadra in forma stravince → più gol favorita',
        'giu': 'Forma conta meno → meno dominio',
    },
    {
        'key': 'PESO_BVS_QUOTE',
        'blocco': 'B',
        'weight_key': 'BVS',
        'nome': 'Peso Quote Bookmaker',
        'desc': 'Quanto contano le quote dei bookmaker.',
        'su': 'Segui di più i bookmaker → favorita domina',
        'giu': 'Ignori i bookmaker → più upset',
    },
    {
        'key': 'PESO_FATTORE_CAMPO',
        'blocco': 'B',
        'weight_key': 'FIELD',
        'nome': 'Peso Fattore Campo',
        'desc': 'Quanto conta giocare in casa.',
        'su': 'Casa fortissima → più vittorie casa con tanti gol',
        'giu': 'Casa/trasferta quasi uguale',
    },
    {
        'key': 'PESO_MOTIVAZIONE',
        'blocco': 'B',
        'weight_key': 'MOTIVATION',
        'nome': 'Peso Motivazione',
        'desc': 'Quanto conta la motivazione (classifica, obiettivi).',
        'su': 'Squadra motivata segna di più',
        'giu': 'Motivazione irrilevante',
    },
    {
        'key': 'PESO_STORIA_H2H',
        'blocco': 'B',
        'weight_key': 'H2H',
        'nome': 'Peso Storia H2H',
        'desc': 'Quanto contano i precedenti. ATTENZIONE: valore negativo = inverte!',
        'su': 'Precedenti contano normalmente',
        'giu': 'Precedenti invertiti (contrarian)',
    },
    {
        'key': 'PESO_STREAK',
        'blocco': 'B',
        'weight_key': 'STREAK',
        'nome': 'Peso Striscia Risultati',
        'desc': 'Quanto conta la striscia di risultati (vinte/perse di fila).',
        'su': 'Striscia positiva → squadra inarrestabile',
        'giu': 'Strisce non contano',
    },
]


# ==================== HELPER ====================

def goals_from_score(s):
    if not s:
        return None
    s = str(s).strip().replace(':', '-')
    parts = re.split(r'[-]', s)
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]) + int(parts[1])
    except (ValueError, TypeError):
        return None


def parse_score(s):
    """Parsa '2-1' → (2, 1) oppure None."""
    if not s:
        return None
    s = str(s).strip().replace(':', '-')
    parts = re.split(r'[-]', s)
    if len(parts) != 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except (ValueError, TypeError):
        return None


def derive_markets(top4_scores, real_score):
    """Dai top4 risultati esatti e il risultato reale, deriva tutti i mercati.

    Ritorna dict con predizione e hit per ogni mercato.
    top4_scores: lista di stringhe es. ['1-0', '2-1', '1-1', '0-0']
    real_score: stringa es. '2-1'
    """
    real = parse_score(real_score)
    if not real:
        return None

    rh, ra = real
    r_tot = rh + ra

    # Risultato reale — mercati
    r_segno = '1' if rh > ra else ('X' if rh == ra else '2')
    r_gg = rh > 0 and ra > 0

    # Parsa top4
    parsed = [parse_score(s) for s in top4_scores]
    parsed = [p for p in parsed if p is not None]
    if not parsed:
        return None

    # --- 1X2 ---
    segni = []
    for h, a in parsed:
        segni.append('1' if h > a else ('X' if h == a else '2'))
    # Voto di maggioranza
    cnt_segno = Counter(segni)
    pred_segno = cnt_segno.most_common(1)[0][0]
    hit_segno = (pred_segno == r_segno)

    # --- Doppia Chance ---
    dcs = []
    for h, a in parsed:
        if h >= a:
            dcs.append('1X')
        if a >= h:
            dcs.append('X2')
        if h != a:
            dcs.append('12')
    cnt_dc = Counter(dcs)
    pred_dc = cnt_dc.most_common(1)[0][0]
    # Hit DC: verifica se il risultato reale rientra nella doppia chance
    r_in_dc = False
    if pred_dc == '1X':
        r_in_dc = rh >= ra
    elif pred_dc == 'X2':
        r_in_dc = ra >= rh
    elif pred_dc == '12':
        r_in_dc = rh != ra
    hit_dc = r_in_dc

    # --- O/U 1.5, 2.5, 3.5 ---
    mercati_ou = {}
    for soglia in [1.5, 2.5, 3.5]:
        over_count = sum(1 for h, a in parsed if (h + a) > soglia)
        pred_ou = 'Over' if over_count >= len(parsed) / 2 else 'Under'  # >= 2 su 4 = Over
        r_ou = 'Over' if r_tot > soglia else 'Under'
        mercati_ou[soglia] = {
            'pred': f"{pred_ou} {soglia}",
            'hit': pred_ou == r_ou,
            'over_count': over_count,
            'total': len(parsed),
        }

    # --- GG/NG ---
    gg_count = sum(1 for h, a in parsed if h > 0 and a > 0)
    pred_gg = 'GG' if gg_count >= len(parsed) / 2 else 'NG'
    hit_gg = (pred_gg == 'GG') == r_gg

    # --- Multigol fasce ---
    def fascia_gol(tot):
        if tot <= 1:
            return '0-1'
        elif tot <= 3:
            return '2-3'
        else:
            return '4+'

    fasce = [fascia_gol(h + a) for h, a in parsed]
    cnt_fasce = Counter(fasce)
    pred_fascia = cnt_fasce.most_common(1)[0][0]
    r_fascia = fascia_gol(r_tot)
    hit_fascia = (pred_fascia == r_fascia)

    return {
        'segno': {'pred': pred_segno, 'hit': hit_segno},
        'dc': {'pred': pred_dc, 'hit': hit_dc},
        'ou_1_5': mercati_ou[1.5],
        'ou_2_5': mercati_ou[2.5],
        'ou_3_5': mercati_ou[3.5],
        'gg_ng': {'pred': pred_gg, 'hit': hit_gg},
        'multigol': {'pred': pred_fascia, 'hit': hit_fascia},
    }


# ── PESI SCORING ──
SCORE_WEIGHTS = {
    'hr_esatto': 1.4,    # Risultato esatto (indicatore qualità modello)
    'segno': 2.3,        # 1X2 = mercato principale
    'ou_2_5': 1.6,       # O/U 2.5 = secondo più giocato
    'dc': 1.2,           # Doppia Chance
    'gg_ng': 1.5,        # GG/NG
    'ou_1_5': 0.8,       # O/U 1.5
    'ou_3_5': 0.8,       # O/U 3.5
    'multigol': 0.8,     # Multigol
}


def calculate_preset_score(hr_esatto_netto, mercati_stats, media_gol_custom, media_gol_reale):
    """Calcola punteggio complessivo del preset.

    Formula: somma(netto × peso) + bonus media gol (0-10).
    Score > 0 = miglioramento, < 0 = peggioramento.
    """
    score = hr_esatto_netto * SCORE_WEIGHTS['hr_esatto']

    market_key_map = {
        'segno': 'segno',
        'dc': 'dc',
        'ou_1_5': 'ou_1_5',
        'ou_2_5': 'ou_2_5',
        'ou_3_5': 'ou_3_5',
        'gg_ng': 'gg_ng',
        'multigol': 'multigol',
    }
    details = [f"HR esatto: {hr_esatto_netto:+d} x {SCORE_WEIGHTS['hr_esatto']:.1f} = {hr_esatto_netto * SCORE_WEIGHTS['hr_esatto']:+.1f}"]

    for weight_key, mkey in market_key_map.items():
        if mkey in mercati_stats:
            netto = mercati_stats[mkey]['netto']
            w = SCORE_WEIGHTS[weight_key]
            score += netto * w
            details.append(f"{mercati_stats[mkey]['nome']}: {netto:+d} x {w:.1f} = {netto * w:+.1f}")

    # Bonus media gol: 10 punti se perfetta, 0 se gap >= 0.20
    gap = abs(media_gol_custom - media_gol_reale)
    media_bonus = max(0, 10 - gap * 50)
    score += media_bonus
    details.append(f"Media gol (gap {gap:.2f}): bonus {media_bonus:+.1f}")

    return round(score, 1), details


def score_giudizio(score):
    """Restituisce un giudizio qualitativo basato sullo score."""
    if score >= 50:
        return "ECCELLENTE"
    elif score >= 20:
        return "BUONO"
    elif score >= 5:
        return "DISCRETO"
    elif score >= -5:
        return "NEUTRO"
    elif score >= -20:
        return "MEDIOCRE"
    else:
        return "SCARSO"


# --- COMMENTATO: serviva per confronto vs #1 in classifica (feature rimossa) ---
# def load_classifica_top1():
#     """Carica nome e parametri custom del #1 in classifica. Ritorna (nome, params) o None."""
#     import glob as glob_mod
#     best = None
#     for fpath in glob_mod.glob(os.path.join(RESULTS_DIR, 'report_*.json')):
#         try:
#             with open(fpath, 'r', encoding='utf-8') as f:
#                 rpt = json.load(f)
#             if 'mercati_derivati' not in rpt:
#                 continue
#             stats = rpt['statistiche']
#             mercati = rpt['mercati_derivati']
#             hr_n = stats['bilancio_netto']
#             sc, _ = calculate_preset_score(hr_n, mercati, stats['media_gol_custom'], stats['media_gol_reale'])
#             nome = rpt.get('nome', os.path.basename(fpath))
#             if best is None or sc > best[0]:
#                 best = (sc, nome, rpt['parametri']['custom'])
#         except Exception:
#             continue
#     if best:
#         return best[1], best[2]
#     return None


def update_classifica(results_dir, new_report_file=None):
    """Aggiorna la classifica dei preset. Max 5 posti, ordinati per score.
    Ritorna True se new_report_file è entrato in classifica, False altrimenti."""
    import glob as glob_mod

    # Leggi tutti i report JSON
    entries = []
    for fpath in glob_mod.glob(os.path.join(results_dir, 'report_*.json')):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                rpt = json.load(f)
            # Serve almeno mercati derivati per calcolare lo score
            if 'mercati_derivati' not in rpt:
                continue

            fname = os.path.basename(fpath)
            nome = rpt.get('nome', fname.replace('.json', '').replace('report_', ''))
            ts = rpt.get('timestamp', '')[:16].replace('T', ' ')
            stats = rpt['statistiche']
            params = rpt['parametri']['custom']
            mercati = rpt['mercati_derivati']

            # Ricalcola SEMPRE con pesi attuali (non usare punteggio salvato)
            hr_n = stats['bilancio_netto']
            sc, det = calculate_preset_score(
                hr_n, mercati,
                stats['media_gol_custom'], stats['media_gol_reale']
            )
            punt = {'score': sc, 'giudizio': score_giudizio(sc)}

            # Identifica modifiche chiave
            mods = rpt['parametri'].get('modificati', {})
            mod_keys = list(mods.keys())

            # Punti forti: mercati con netto > 0, ordinati per netto desc
            forti = []
            deboli = []
            for mk, mv in mercati.items():
                n = mv['netto']
                if n > 3:
                    forti.append(f"{mv['nome']} {n:+d}")
                elif n < -3:
                    deboli.append(f"{mv['nome']} {n:+d}")
            # HR esatto
            hr_n = stats['bilancio_netto']
            if hr_n > 1:
                forti.insert(0, f"HR esatto {hr_n:+d}")
            elif hr_n < -1:
                deboli.insert(0, f"HR esatto {hr_n:+d}")

            entries.append({
                'file': fname,
                'nome': nome,
                'fpath': fpath,
                'ts': ts,
                'score': punt['score'],
                'giudizio': punt['giudizio'],
                'partite': rpt['totale_partite'],
                'cicli': rpt.get('cicli_mc', '?'),
                'periodo': f"{rpt['periodo']['inizio']} -> {rpt['periodo']['fine']}",
                'hr_netto': hr_n,
                'hr_custom': stats.get('hr_custom', 0),
                'media_custom': stats['media_gol_custom'],
                'media_reale': stats['media_gol_reale'],
                'gap': round(abs(stats['media_gol_custom'] - stats['media_gol_reale']), 2),
                'params': params,
                'mod_keys': mod_keys,
                'mercati': mercati,
                'forti': forti,
                'deboli': deboli,
            })
        except Exception:
            continue

    if not entries:
        return False

    # Ordina per score desc, tieni top 5
    entries.sort(key=lambda x: x['score'], reverse=True)
    top5 = entries[:5]

    # Controlla se il nuovo report è in classifica
    new_in_classifica = False
    if new_report_file:
        new_fname = os.path.basename(new_report_file)
        new_in_classifica = any(e['file'] == new_fname for e in top5)

    # Scrivi il file
    classifica_path = os.path.join(results_dir, 'classifica_preset.txt')
    with open(classifica_path, 'w', encoding='utf-8') as f:
        W = 106
        f.write("+" + "=" * (W - 2) + "+\n")
        f.write("|" + "CLASSIFICA PRESET MC — TOP 5".center(W - 2) + "|\n")
        f.write("|" + f"Aggiornata: {datetime.now().strftime('%d/%m/%Y %H:%M')}".center(W - 2) + "|\n")
        f.write("+" + "=" * (W - 2) + "+\n\n")

        # Tabella classifica
        f.write(f"  {'#':<4}{'Score':>8}  {'HR':>5}  {'Gap':>6}  {'Nome':<36}  {'Giudizio':<10}  {'Cicli':>5}  {'Data'}\n")
        f.write("  " + "-" * 100 + "\n")
        for i, e in enumerate(top5, 1):
            medal = {1: '>>>', 2: ' >>', 3: '  >'}.get(i, '   ')
            nome_trunc = e['nome'][:34]
            ts_short = e['ts'][5:] if len(e['ts']) >= 16 else e['ts']  # MM-DD HH:MM
            f.write(f"  {medal}{i}  {e['score']:>+7.1f}  {e['hr_netto']:>+4d}  {e['gap']:>5.2f}  {nome_trunc:<36}  {e['giudizio']:<10}  {e['cicli']:>5}  {ts_short}\n")
        f.write("  " + "-" * 100 + "\n")
        f.write(f"  ({len(entries)} report totali, mostrati i migliori 5)\n")

        # Dettaglio per ogni preset
        for i, e in enumerate(top5, 1):
            f.write(f"\n  {'─' * 82}\n")
            f.write(f"  #{i}  {e['nome']}  |  SCORE: {e['score']:+.1f}\n")
            f.write(f"  File: {e['file']}\n")
            f.write(f"  {'─' * 82}\n")

            # Parametri modificati (compatto, una riga)
            mods_str = ', '.join(f"{k.split('_', 1)[-1][:12]}={e['params'].get(k, '?')}" for k in e['mod_keys'][:6])
            if len(e['mod_keys']) > 6:
                mods_str += f" (+{len(e['mod_keys'])-6})"
            f.write(f"  Periodo: {e['periodo']}  |  Media gol: {e['media_custom']:.2f} (reale {e['media_reale']:.2f}, gap {e['gap']:.2f})\n")
            f.write(f"  Modifiche: {mods_str}\n")

            # Tabella mercati compatta (incluso HR esatto)
            f.write(f"\n  {'Mercato':<16}{'Netto':>7}  {'HR Custom':>14}  |  {'Mercato':<16}{'Netto':>7}  {'HR Custom':>14}\n")
            f.write(f"  {'-'*40}  |  {'-'*40}\n")

            # Aggiungi HR esatto come primo mercato
            hr_entry = ('hr_esatto', {'nome': 'HR esatto', 'netto': e['hr_netto'], 'hr_custom': e['hr_custom']})
            mk_list = [hr_entry] + list(e['mercati'].items())
            # Dividi in 2 colonne
            half = (len(mk_list) + 1) // 2
            for row in range(half):
                left = mk_list[row] if row < len(mk_list) else None
                right = mk_list[row + half] if (row + half) < len(mk_list) else None

                if left:
                    lm = left[1]
                    ln = lm['netto']
                    ln_s = f"{ln:+d}"
                    left_str = f"  {lm['nome']:<16}{ln_s:>7}  {lm['hr_custom']:>14}"
                else:
                    left_str = f"  {'':40}"

                if right:
                    rm = right[1]
                    rn = rm['netto']
                    rn_s = f"{rn:+d}"
                    right_str = f"  {rm['nome']:<16}{rn_s:>7}  {rm['hr_custom']:>14}"
                else:
                    right_str = ""

                f.write(f"{left_str}  |{right_str}\n")

            # Punti forti/deboli (una riga ciascuno)
            if e['forti']:
                f.write(f"\n  Forti: {', '.join(e['forti'])}\n")
            if e['deboli']:
                f.write(f"  Deboli: {', '.join(e['deboli'])}\n")

        # Footer
        f.write(f"\n  {'═' * 82}\n")
        f.write(f"  Formula: sum(netto x peso) + bonus media gol (max 10pt)\n")
        w = SCORE_WEIGHTS
        f.write(f"  Pesi: HR esatto {w['hr_esatto']} | 1X2 {w['segno']} | O/U 2.5 {w['ou_2_5']} | DC {w['dc']} | GG/NG {w['gg_ng']} | O/U 1.5 {w['ou_1_5']} | O/U 3.5 {w['ou_3_5']} | MG {w['multigol']}\n")
        f.write(f"  {'═' * 82}\n")

    # ── Pulizia preset: tieni solo quelli in top 5 + default ──
    presets_dir = os.path.join(os.path.dirname(results_dir), 'presets') if os.path.isdir(os.path.join(os.path.dirname(results_dir), 'presets')) else None
    if not presets_dir:
        presets_dir = os.path.join(results_dir, '..', 'presets')
    if os.path.isdir(presets_dir):
        # Raccogli parametri custom di tutti i top 5
        top5_params = []
        for e in top5:
            top5_params.append(e['params'])

        removed = []
        for pfile in glob_mod.glob(os.path.join(presets_dir, '*.json')):
            pname = os.path.basename(pfile)
            # Preserva sempre il default
            if pname.startswith('default_') or pname.startswith('backup_'):
                continue
            try:
                with open(pfile, 'r', encoding='utf-8') as pf:
                    preset = json.load(pf)
                preset_params = preset.get('parameters', {})
                # Confronta con ogni entry in top 5
                match = False
                for tp in top5_params:
                    if all(abs(preset_params.get(k, -999) - tp.get(k, -998)) < 0.001 for k in preset_params):
                        match = True
                        break
                if not match:
                    os.remove(pfile)
                    removed.append(pname)
            except Exception:
                continue
        if removed:
            print(f"  🧹 Preset rimossi (fuori top 5): {', '.join(removed)}")

    return new_in_classifica


def get_matches_for_range(start_date, end_date):
    """Carica partite con risultato reale da h2h_by_round per un range di date."""
    pipeline = [
        {"$unwind": "$matches"},
        {"$match": {
            "matches.date_obj": {"$gte": start_date, "$lt": end_date + timedelta(days=1)},
            "matches.real_score": {"$ne": None}
        }},
        {"$project": {
            "league": 1,
            "match": "$matches"
        }}
    ]
    results = []
    for doc in h2h_collection.aggregate(pipeline):
        m = doc['match']
        m['_league'] = doc.get('league', 'Unknown')
        results.append(m)
    return results


def run_mc_single(preloaded, home, away, cycles, settings_cache, is_cup=False):
    """Esegue MC con parametri custom. Ritorna distribuzione gol e top scores."""
    results = []
    for _ in range(cycles):
        with suppress_stdout():
            out = predict_match(home, away, mode=ALGO_MODE, preloaded_data=preloaded)
        if out is None or out[0] is None:
            continue
        s_h, s_a, r_h, r_a = out

        with suppress_stdout():
            goal_result = calculate_goals_from_engine(
                s_h, s_a, r_h, r_a,
                algo_mode=ALGO_MODE,
                home_name=home,
                away_name=away,
                settings_cache=settings_cache,
                debug_mode=False,
                is_cup=is_cup
            )
        gh, ga = int(goal_result[0]), int(goal_result[1])
        results.append((gh, ga))

    if not results:
        return None

    n = len(results)
    scores = [f"{g[0]}-{g[1]}" for g in results]
    top_scores = Counter(scores).most_common(5)
    avg_goals = sum(g[0] + g[1] for g in results) / n

    return {
        'top_scores': top_scores,
        'avg_goals': avg_goals,
        'valid': n,
        'results': results,
    }


# ==================== FASE 1: INPUT INTERATTIVO ====================

def parse_date_input(s):
    """Parsa una data in vari formati: YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, DD-M-YYYY."""
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%d-%m-%y', '%d/%m/%y'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Formato data non riconosciuto: '{s}'. Usa YYYY-MM-DD o DD-MM-YYYY o DD/MM/YYYY")


def ask_date_range():
    print("\n" + "=" * 60)
    print("  PERIODO DI SIMULAZIONE")
    print("=" * 60)

    now = datetime.now()
    default_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
    default_end = now.replace(day=1)

    ds = default_start.strftime('%Y-%m-%d')
    de = default_end.strftime('%Y-%m-%d')

    print(f"\n  Default: {ds} → {de}")
    print(f"  (formati accettati: 2026-02-28, 28-2-2026, 28/02/2026)")
    s = input(f"  Data inizio [{ds}]: ").strip()
    if s:
        default_start = parse_date_input(s)

    e = input(f"  Data fine [{de}]: ").strip()
    if e:
        default_end = parse_date_input(e)

    # Se stessa data o fine <= inizio, aggiungi 1 giorno alla fine
    if default_end <= default_start:
        default_end = default_start + timedelta(days=1)
        print(f"  (fine automatica: {default_end.strftime('%Y-%m-%d')})")

    cycles_str = input(f"  Cicli MC per partita [100]: ").strip().rstrip('.')
    cycles = int(float(cycles_str)) if cycles_str else 100

    return default_start, default_end, cycles


def load_original_settings():
    """Carica i parametri ALGO_C originali da MongoDB."""
    settings = load_tuning(ALGO_MODE)
    return settings


def ask_parameters(original_settings):
    """Chiede all'utente i parametri custom, mostrando descrizioni.
    Ritorna (custom_settings, changed_params, preset_name)."""
    custom = dict(original_settings)
    changed = {}
    preset_name = None

    # Controlla se ci sono preset salvati
    presets = load_presets_list()
    if presets:
        print("\n" + "=" * 60)
        print("  PRESET SALVATI")
        print("=" * 60)
        for i, preset_item in enumerate(presets):
            fname, summary = preset_item[0], preset_item[1]
            name = preset_item[2] if len(preset_item) > 2 else fname
            letter = chr(65 + i)  # A, B, C...
            print(f"  [{letter}] {name}")
            print(f"      {summary}")
        print(f"  [N] Nuovo — inserisci parametri manualmente")

        choice = input(f"\n  Scelta [{chr(65)}/N]: ").strip().upper()
        if choice and choice != 'N' and ord(choice) - 65 < len(presets):
            idx = ord(choice) - 65
            preset_path = os.path.join(PRESETS_DIR, presets[idx][0])
            with open(preset_path, 'r', encoding='utf-8') as f:
                preset_data = json.load(f)

            # Applica preset
            for k, v in preset_data.get('parameters', {}).items():
                if k in custom and custom[k] != v:
                    changed[k] = (custom[k], v)
                custom[k] = v

            preset_name = preset_data.get('name', presets[idx][0].replace('.json', '').replace('tuning_', ''))
            print(f"\n  Caricato preset: {preset_name}")

            # ── Menu revisione post-caricamento ──
            while True:
                print(f"\n  {'─' * 60}")
                print(f"  PARAMETRI CARICATI:")
                print(f"  {'─' * 60}")
                for pdef in PARAM_DEFS:
                    k = pdef['key']
                    orig_val = original_settings.get(k, '?')
                    cust_val = custom.get(k, '?')
                    marker = '  ←' if k in changed else ''
                    print(f"    {k:<32} {str(orig_val):>8} → {str(cust_val):>8}{marker}")
                print(f"  {'─' * 60}")

                print(f"\n  [M] Modifica un parametro")
                print(f"  [L] Lancia simulazione con questi parametri")
                print(f"  [S] Scarta e ricomincia da zero")

                rev_choice = input(f"\n  Scelta [M/L/S]: ").strip().upper()

                if rev_choice == 'L' or rev_choice == '':
                    break
                elif rev_choice == 'S':
                    # Ricomincia: ritorna parametri originali non modificati
                    return ask_parameters(original_settings)
                elif rev_choice == 'M':
                    # Mostra lista numerata
                    print()
                    for i, pdef in enumerate(PARAM_DEFS, 1):
                        k = pdef['key']
                        print(f"    {i:>2}. {k:<32} = {custom.get(k, '?')}")

                    num_str = input(f"\n  Numero parametro da modificare (1-{len(PARAM_DEFS)}): ").strip()
                    try:
                        num = int(num_str)
                        if 1 <= num <= len(PARAM_DEFS):
                            pdef = PARAM_DEFS[num - 1]
                            k = pdef['key']
                            curr = custom.get(k, '?')
                            print(f"\n    {pdef['nome']}: {pdef['desc']}")
                            print(f"    Valore attuale: {curr} (originale: {original_settings.get(k, '?')})")
                            new_val = input(f"    Nuovo valore [INVIO = mantieni {curr}]: ").strip()
                            if new_val:
                                try:
                                    new_val_f = float(new_val)
                                    orig_val = original_settings.get(k)
                                    if new_val_f != orig_val:
                                        changed[k] = (orig_val, new_val_f)
                                    elif k in changed:
                                        del changed[k]  # Ripristinato all'originale
                                    custom[k] = new_val_f
                                    print(f"    ✓ {k} = {new_val_f}")
                                except ValueError:
                                    print(f"    ⚠️ Valore non valido")
                        else:
                            print(f"  ⚠️ Numero fuori range")
                    except ValueError:
                        print(f"  ⚠️ Inserisci un numero")
                else:
                    print(f"  ⚠️ Scelta non valida")

            if changed:
                print(f"\n  {len(changed)} parametri modificati rispetto all'originale.")
            return custom, changed, preset_name

    print("\n" + "=" * 60)
    print("  PARAMETRI — BLOCCO A: GOL DIRETTI")
    print("  (controllano quanti gol escono)")
    print("=" * 60)

    blocco_a = [p for p in PARAM_DEFS if p['blocco'] == 'A']
    blocco_b = [p for p in PARAM_DEFS if p['blocco'] == 'B']

    for i, pdef in enumerate(blocco_a, 1):
        val = original_settings.get(pdef['key'], '?')
        print(f"\n  {i}. {pdef['nome']}")
        print(f"     Valore attuale: {val}")
        print(f"     {pdef['desc']}")
        print(f"     ↑ Aumenti: {pdef['su']}")
        print(f"     ↓ Diminuisci: {pdef['giu']}")

        new_val = input(f"     Nuovo valore [INVIO = mantieni {val}]: ").strip()
        if new_val:
            try:
                new_val_f = float(new_val)
                if new_val_f != val:
                    changed[pdef['key']] = (val, new_val_f)
                custom[pdef['key']] = new_val_f
            except ValueError:
                print(f"     ⚠️ Valore non valido, mantengo {val}")

    print("\n" + "=" * 60)
    print("  PARAMETRI — BLOCCO B: PESI FATTORI")
    print("  (controllano chi è favorito e quanto → influisce sui gol)")
    print("=" * 60)

    for i, pdef in enumerate(blocco_b, len(blocco_a) + 1):
        val = original_settings.get(pdef['key'], '?')
        print(f"\n  {i}. {pdef['nome']}")
        print(f"     Valore attuale: {val}")
        print(f"     {pdef['desc']}")
        print(f"     ↑ Aumenti: {pdef['su']}")
        print(f"     ↓ Diminuisci: {pdef['giu']}")

        new_val = input(f"     Nuovo valore [INVIO = mantieni {val}]: ").strip()
        if new_val:
            try:
                new_val_f = float(new_val)
                if new_val_f != val:
                    changed[pdef['key']] = (val, new_val_f)
                custom[pdef['key']] = new_val_f
            except ValueError:
                print(f"     ⚠️ Valore non valido, mantengo {val}")

    return custom, changed, preset_name


def load_presets_list():
    """Carica lista dei preset salvati."""
    presets = []
    if not os.path.exists(PRESETS_DIR):
        return presets
    for fname in sorted(os.listdir(PRESETS_DIR)):
        if fname.endswith('.json') and not fname.startswith('backup_'):
            try:
                with open(os.path.join(PRESETS_DIR, fname), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Genera summary dalle modifiche
                name = data.get('name', fname.replace('.json', ''))
                diffs = data.get('changes', {})
                if diffs:
                    summary = ', '.join(f"{k}: {v[0]}→{v[1]}" for k, v in list(diffs.items())[:3])
                else:
                    summary = "Parametri originali (baseline)"
                presets.append((fname, summary, name))
            except Exception:
                continue
    return presets[:10]  # Max 10 preset


# ==================== FASE 2: SIMULAZIONE ====================

def run_simulation(matches, cycles, original_settings, custom_settings, changed_params):
    """Esegue MC originale e custom per tutte le partite."""

    # Se i pesi Blocco B sono cambiati, dobbiamo fare monkey-patch di WEIGHTS_CACHE
    blocco_b_changed = any(
        pdef['key'] in changed_params and pdef['weight_key'] is not None
        for pdef in PARAM_DEFS
    )

    # Salva WEIGHTS_CACHE originale per ripristino
    original_weights_6 = copy.deepcopy(WEIGHTS_CACHE[6])

    # Prepara custom weights se servono
    custom_weights_6 = copy.deepcopy(WEIGHTS_CACHE[6])
    if blocco_b_changed:
        for pdef in PARAM_DEFS:
            if pdef['blocco'] == 'B' and pdef['key'] in changed_params:
                wk = pdef['weight_key']
                if wk:
                    custom_weights_6[wk] = custom_settings[pdef['key']]

    # Raggruppa per lega
    leagues = {}
    for m in matches:
        lg = m.get('_league', 'Unknown')
        if lg not in leagues:
            leagues[lg] = []
        leagues[lg].append(m)

    results = []
    total = len(matches)
    done = 0
    skipped = 0
    t_start = time.time()

    for league, league_matches in leagues.items():
        # Raccogli squadre
        all_teams = []
        for m in league_matches:
            all_teams.append(m.get('home', ''))
            all_teams.append(m.get('away', ''))
        all_teams = list(set(t for t in all_teams if t))

        # Carica cache lega
        try:
            with suppress_stdout():
                league_cache = bulk_manager_c.load_league_cache(all_teams, league)
        except Exception as e:
            print(f"  ⚠️ Skip lega {league}: {e}")
            skipped += len(league_matches)
            done += len(league_matches)
            continue

        for m in league_matches:
            home = m.get('home', '')
            away = m.get('away', '')
            real_score = m.get('real_score', '')
            date_str = m.get('date_obj', datetime.now()).strftime('%Y-%m-%d') if m.get('date_obj') else '?'

            done += 1
            elapsed = time.time() - t_start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0

            # Progress ogni 10 partite
            if done % 10 == 0 or done == total:
                elaborated = done - skipped
                print(f"\r  Progresso: {done}/{total} ({done/total*100:.0f}%) "
                      f"| {rate:.1f} partite/s | ETA: {eta:.0f}s "
                      f"| OK: {elaborated} Skip: {skipped}   ", end='', flush=True)

            # Build cache + preload
            try:
                with suppress_stdout():
                    bulk_cache = bulk_manager_c.build_match_cache(league_cache, home, away)
                    preloaded = preload_match_data(home, away, league=league, bulk_cache=bulk_cache)
            except Exception:
                skipped += 1
                continue

            if not preloaded:
                skipped += 1
                continue

            # --- MC ORIGINALE ---
            try:
                WEIGHTS_CACHE[6] = original_weights_6
                dist_orig = run_mc_single(preloaded, home, away, cycles, original_settings)

                # --- MC CUSTOM ---
                if blocco_b_changed:
                    WEIGHTS_CACHE[6] = custom_weights_6
                dist_custom = run_mc_single(preloaded, home, away, cycles, custom_settings)
            except Exception:
                WEIGHTS_CACHE[6] = original_weights_6
                skipped += 1
                continue

            # Ripristina weights originali
            WEIGHTS_CACHE[6] = original_weights_6

            if not dist_orig or not dist_custom:
                skipped += 1
                continue

            results.append({
                'date': date_str,
                'home': home,
                'away': away,
                'league': league,
                'real_score': real_score.replace(':', '-') if real_score else '?',
                'real_goals': goals_from_score(real_score),
                'orig': dist_orig,
                'custom': dist_custom,
            })

    elapsed_total = time.time() - t_start
    print(f"\n  ✅ Completato in {elapsed_total:.0f}s — Elaborate: {len(results)} | Skip: {skipped} | Totale: {total}")
    return results


# ==================== FASE 3: REPORT ====================

def print_report(results, changed_params, original_settings, custom_settings, start_date, end_date, cycles):
    """Stampa report comparativo."""

    if not results:
        print("\n⚠️ Nessun risultato da mostrare.")
        return

    n = len(results)

    print("\n" + "═" * 70)
    print("   MC TUNING TESTER — REPORT COMPARATIVO")
    print(f"   Periodo: {start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}")
    print(f"   Partite: {n} | Cicli MC: {cycles}")
    print("═" * 70)

    # Tabella completa parametri
    print(f"\n  PARAMETRI:")
    print(f"    {'Parametro':<30} {'Originale':>12} {'Custom':>12} {'Mod.'}")
    print(f"    {'-'*62}")
    for pdef in PARAM_DEFS:
        k = pdef['key']
        orig_val = original_settings.get(k, '?') if original_settings else '?'
        cust_val = custom_settings.get(k, '?') if custom_settings else '?'
        marker = '  ←' if k in changed_params else ''
        print(f"    {k:<30} {str(orig_val):>12} {str(cust_val):>12} {marker}")

    # Media gol
    avg_orig = sum(r['orig']['avg_goals'] for r in results) / n
    avg_custom = sum(r['custom']['avg_goals'] for r in results) / n
    real_goals = [r['real_goals'] for r in results if r['real_goals'] is not None]
    avg_real = sum(real_goals) / len(real_goals) if real_goals else 0

    print(f"\n  MEDIA GOL PER PARTITA:")
    print(f"    {'':20} {'Originale':>12} {'Custom':>12} {'Realtà':>12}")
    print(f"    {'Media gol':20} {avg_orig:>12.2f} {avg_custom:>12.2f} {avg_real:>12.2f}")

    # Distribuzione gol per fascia
    print(f"\n  DISTRIBUZIONE GOL (% partite nei top4):")
    print(f"    {'Fascia':>12} {'Originale':>12} {'Custom':>12} {'Realtà':>12}")
    print(f"    {'-'*50}")

    for label, lo, hi in [('0-1 gol', 0, 1), ('2 gol', 2, 2), ('3 gol', 3, 3), ('4+ gol', 4, 99)]:
        # Conta nei top 4 scores
        orig_count = 0
        custom_count = 0
        orig_total = 0
        custom_total = 0
        for r in results:
            for score, cnt in r['orig']['top_scores'][:4]:
                g = goals_from_score(score)
                if g is not None:
                    orig_total += cnt
                    if lo <= g <= hi:
                        orig_count += cnt
            for score, cnt in r['custom']['top_scores'][:4]:
                g = goals_from_score(score)
                if g is not None:
                    custom_total += cnt
                    if lo <= g <= hi:
                        custom_count += cnt

        orig_pct = orig_count / orig_total * 100 if orig_total > 0 else 0
        custom_pct = custom_count / custom_total * 100 if custom_total > 0 else 0
        real_count = sum(1 for r in results if r['real_goals'] is not None and lo <= r['real_goals'] <= hi)
        real_pct = real_count / len(real_goals) * 100 if real_goals else 0

        print(f"    {label:>12} {orig_pct:>11.1f}% {custom_pct:>11.1f}% {real_pct:>11.1f}%")

    # HR top 4
    orig_hits = sum(1 for r in results
                    if r['real_score'] in [s for s, _ in r['orig']['top_scores'][:4]])
    custom_hits = sum(1 for r in results
                      if r['real_score'] in [s for s, _ in r['custom']['top_scores'][:4]])

    print(f"\n  TOP SCORES:")
    print(f"    {'':20} {'Originale':>12} {'Custom':>12}")
    print(f"    {'HR top 4':20} {orig_hits}/{n} ({orig_hits/n*100:.1f}%) {'':<1}"
          f"{custom_hits}/{n} ({custom_hits/n*100:.1f}%)")

    # Risultati unici
    orig_unique = set()
    custom_unique = set()
    for r in results:
        for s, _ in r['orig']['top_scores'][:4]:
            orig_unique.add(s)
        for s, _ in r['custom']['top_scores'][:4]:
            custom_unique.add(s)

    print(f"    {'Risultati unici':20} {len(orig_unique):>12} {len(custom_unique):>12}")

    # Nuovi HIT (custom becca ma originale no)
    new_hits = sum(1 for r in results
                   if r['real_score'] in [s for s, _ in r['custom']['top_scores'][:4]]
                   and r['real_score'] not in [s for s, _ in r['orig']['top_scores'][:4]])
    lost_hits = sum(1 for r in results
                    if r['real_score'] not in [s for s, _ in r['custom']['top_scores'][:4]]
                    and r['real_score'] in [s for s, _ in r['orig']['top_scores'][:4]])

    print(f"    {'Nuovi HIT (custom)':20} {'+' + str(new_hits):>12}")
    print(f"    {'HIT persi':20} {'-' + str(lost_hits):>12}")
    print(f"    {'Bilancio netto':20} {'+' + str(new_hits - lost_hits) if new_hits >= lost_hits else str(new_hits - lost_hits):>12}")

    # ── MERCATI DERIVATI ──
    mercati_names = [
        ('segno', '1X2'),
        ('dc', 'Doppia Chance'),
        ('ou_1_5', 'O/U 1.5'),
        ('ou_2_5', 'O/U 2.5'),
        ('ou_3_5', 'O/U 3.5'),
        ('gg_ng', 'GG/NG'),
        ('multigol', 'Multigol'),
    ]
    print(f"\n  MERCATI DERIVATI (dai top4):")
    print(f"    {'Mercato':<16} {'HR Originale':>16} {'HR Custom':>16} {'Nuovi':>7} {'Persi':>7} {'Netto':>7}")
    print(f"    {'-'*72}")

    mercati_stats_pr = {}
    for mkey, mname in mercati_names:
        orig_h = cust_h = valid = new_m = lost_m = 0
        for r in results:
            orig_t4 = [s for s, _ in r['orig']['top_scores'][:4]]
            cust_t4 = [s for s, _ in r['custom']['top_scores'][:4]]
            dm_orig = derive_markets(orig_t4, r['real_score'])
            dm_cust = derive_markets(cust_t4, r['real_score'])
            if dm_orig and dm_cust:
                valid += 1
                o_hit = dm_orig[mkey]['hit']
                c_hit = dm_cust[mkey]['hit']
                if o_hit:
                    orig_h += 1
                if c_hit:
                    cust_h += 1
                if c_hit and not o_hit:
                    new_m += 1
                if not c_hit and o_hit:
                    lost_m += 1

        if valid > 0:
            orig_pct = orig_h / valid * 100
            cust_pct = cust_h / valid * 100
            netto = new_m - lost_m
            netto_str = f"+{netto}" if netto >= 0 else str(netto)
            print(f"    {mname:<16} {orig_h:>4}/{valid} ({orig_pct:>5.1f}%) {cust_h:>4}/{valid} ({cust_pct:>5.1f}%) {'+' + str(new_m):>7} {'-' + str(lost_m):>7} {netto_str:>7}")
            mercati_stats_pr[mkey] = {'nome': mname, 'netto': netto}

    print(f"    {'-'*72}")

    # ── PUNTEGGIO PRESET ──
    hr_netto = new_hits - lost_hits
    score, score_details = calculate_preset_score(hr_netto, mercati_stats_pr, avg_custom, avg_real)
    print(f"\n  PUNTEGGIO PRESET:")
    print(f"    {'-'*55}")
    for det in score_details:
        print(f"    {det}")
    print(f"    {'-'*55}")
    giudizio = score_giudizio(score)
    print(f"    SCORE TOTALE: {score:+.1f}  ({giudizio})")
    print(f"    {'-'*55}")

    # Alert risultati estremi
    print(f"\n  ALERT RISULTATI ESTREMI (custom):")
    extreme_count = 0
    max_goals = 0
    max_score = ''
    for r in results:
        for score, cnt in r['custom']['top_scores'][:4]:
            g = goals_from_score(score)
            if g and g >= 7:
                extreme_count += 1
            if g and g > max_goals:
                max_goals = g
                max_score = score

    print(f"    Previsioni con 7+ gol nei top4: {extreme_count}")
    print(f"    Risultato più estremo: {max_score} ({max_goals} gol)")

    # Top scores più frequenti (custom)
    print(f"\n  TOP SCORES PIÙ FREQUENTI (custom):")
    all_custom_scores = Counter()
    for r in results:
        for s, cnt in r['custom']['top_scores'][:4]:
            all_custom_scores[s] += cnt
    total_custom = sum(all_custom_scores.values())
    for s, c in all_custom_scores.most_common(10):
        g = goals_from_score(s)
        print(f"    {s} ({g}g): {c/total_custom*100:.1f}%")

    # Dettaglio partite (prime 30)
    print(f"\n  DETTAGLIO (prime 30 partite):")
    print(f"  {'Data':<12} {'Partita':<35} {'Top4 ORIG':<24} {'Top4 CUSTOM':<24} {'Reale':<8} {'Note'}")
    print(f"  {'-'*110}")

    for r in sorted(results, key=lambda x: x['date'])[:30]:
        orig_top4 = ','.join(s for s, _ in r['orig']['top_scores'][:4])
        custom_top4 = ','.join(s for s, _ in r['custom']['top_scores'][:4])

        in_orig = r['real_score'] in [s for s, _ in r['orig']['top_scores'][:4]]
        in_custom = r['real_score'] in [s for s, _ in r['custom']['top_scores'][:4]]

        note = ''
        if in_custom and not in_orig:
            note = '★ NEW HIT!'
        elif not in_custom and in_orig:
            note = '✗ PERSO'
        elif in_custom and in_orig:
            note = '✓ HIT'

        partita = f"{r['home'][:16]} vs {r['away'][:16]}"
        print(f"  {r['date']:<12} {partita:<35} {orig_top4:<24} {custom_top4:<24} {r['real_score']:<8} {note}")

    print(f"\n  (Totale partite: {n} — dettaglio completo nel file JSON)")


def save_full_report(results, changed_params, original_settings, custom_settings, start_date, end_date, cycles, nome=None):
    """Salva il report completo con TUTTE le partite in un file JSON."""

    RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
    os.makedirs(RESULTS_DIR, exist_ok=True)

    n = len(results)
    if n == 0:
        return None

    # Calcola statistiche aggregate
    avg_orig = sum(r['orig']['avg_goals'] for r in results) / n
    avg_custom = sum(r['custom']['avg_goals'] for r in results) / n
    real_goals = [r['real_goals'] for r in results if r['real_goals'] is not None]
    avg_real = sum(real_goals) / len(real_goals) if real_goals else 0

    orig_hits = sum(1 for r in results
                    if r['real_score'] in [s for s, _ in r['orig']['top_scores'][:4]])
    custom_hits = sum(1 for r in results
                      if r['real_score'] in [s for s, _ in r['custom']['top_scores'][:4]])
    new_hits = sum(1 for r in results
                   if r['real_score'] in [s for s, _ in r['custom']['top_scores'][:4]]
                   and r['real_score'] not in [s for s, _ in r['orig']['top_scores'][:4]])
    lost_hits = sum(1 for r in results
                    if r['real_score'] not in [s for s, _ in r['custom']['top_scores'][:4]]
                    and r['real_score'] in [s for s, _ in r['orig']['top_scores'][:4]])

    # Distribuzione gol
    distribuzione = {}
    for label, lo, hi in [('0-1 gol', 0, 1), ('2 gol', 2, 2), ('3 gol', 3, 3), ('4+ gol', 4, 99)]:
        orig_count = custom_count = orig_total = custom_total = 0
        for r in results:
            for score, cnt in r['orig']['top_scores'][:4]:
                g = goals_from_score(score)
                if g is not None:
                    orig_total += cnt
                    if lo <= g <= hi:
                        orig_count += cnt
            for score, cnt in r['custom']['top_scores'][:4]:
                g = goals_from_score(score)
                if g is not None:
                    custom_total += cnt
                    if lo <= g <= hi:
                        custom_count += cnt
        real_count = sum(1 for r in results if r['real_goals'] is not None and lo <= r['real_goals'] <= hi)
        distribuzione[label] = {
            'originale_pct': round(orig_count / orig_total * 100, 1) if orig_total > 0 else 0,
            'custom_pct': round(custom_count / custom_total * 100, 1) if custom_total > 0 else 0,
            'realta_pct': round(real_count / len(real_goals) * 100, 1) if real_goals else 0,
        }

    # Build dettaglio TUTTE le partite
    dettaglio = []
    for r in sorted(results, key=lambda x: (x['date'], x['league'], x['home'])):
        orig_top4 = [s for s, _ in r['orig']['top_scores'][:4]]
        custom_top4 = [s for s, _ in r['custom']['top_scores'][:4]]

        in_orig = r['real_score'] in orig_top4
        in_custom = r['real_score'] in custom_top4

        if in_custom and not in_orig:
            nota = 'NEW_HIT'
        elif not in_custom and in_orig:
            nota = 'PERSO'
        elif in_custom and in_orig:
            nota = 'HIT'
        else:
            nota = ''

        dettaglio.append({
            'data': r['date'],
            'lega': r['league'],
            'casa': r['home'],
            'trasferta': r['away'],
            'reale': r['real_score'],
            'gol_reali': r['real_goals'],
            'top4_orig': orig_top4,
            'top4_custom': custom_top4,
            'top5_orig': [s for s, _ in r['orig']['top_scores'][:5]],
            'top5_custom': [s for s, _ in r['custom']['top_scores'][:5]],
            'media_gol_orig': round(r['orig']['avg_goals'], 2),
            'media_gol_custom': round(r['custom']['avg_goals'], 2),
            'nota': nota,
        })

    report = {
        'nome': nome or 'Senza nome',
        'timestamp': datetime.now().isoformat(),
        'periodo': {
            'inizio': start_date.strftime('%Y-%m-%d'),
            'fine': end_date.strftime('%Y-%m-%d'),
        },
        'cicli_mc': cycles,
        'totale_partite': n,
        'parametri': {
            'originali': {p['key']: original_settings.get(p['key']) for p in PARAM_DEFS},
            'custom': {p['key']: custom_settings.get(p['key']) for p in PARAM_DEFS},
            'modificati': {k: {'da': v[0], 'a': v[1]} for k, v in changed_params.items()},
        },
        'statistiche': {
            'media_gol_orig': round(avg_orig, 2),
            'media_gol_custom': round(avg_custom, 2),
            'media_gol_reale': round(avg_real, 2),
            'hr_orig': f"{orig_hits}/{n}",
            'hr_orig_pct': round(orig_hits / n * 100, 1),
            'hr_custom': f"{custom_hits}/{n}",
            'hr_custom_pct': round(custom_hits / n * 100, 1),
            'nuovi_hit': new_hits,
            'hit_persi': lost_hits,
            'bilancio_netto': new_hits - lost_hits,
            'distribuzione_gol': distribuzione,
        },
        'partite': dettaglio,
    }

    # ── Calcola mercati derivati per JSON ──
    mercati_keys = [
        ('segno', '1X2'),
        ('dc', 'Doppia Chance'),
        ('ou_1_5', 'O/U 1.5'),
        ('ou_2_5', 'O/U 2.5'),
        ('ou_3_5', 'O/U 3.5'),
        ('gg_ng', 'GG/NG'),
        ('multigol', 'Multigol'),
    ]
    mercati_stats = {}
    for mkey, mname in mercati_keys:
        orig_h = cust_h = valid = new_m = lost_m = 0
        for r in results:
            orig_t4 = [s for s, _ in r['orig']['top_scores'][:4]]
            cust_t4 = [s for s, _ in r['custom']['top_scores'][:4]]
            dm_orig = derive_markets(orig_t4, r['real_score'])
            dm_cust = derive_markets(cust_t4, r['real_score'])
            if dm_orig and dm_cust:
                valid += 1
                o_hit = dm_orig[mkey]['hit']
                c_hit = dm_cust[mkey]['hit']
                if o_hit:
                    orig_h += 1
                if c_hit:
                    cust_h += 1
                if c_hit and not o_hit:
                    new_m += 1
                if not c_hit and o_hit:
                    lost_m += 1
        if valid > 0:
            mercati_stats[mkey] = {
                'nome': mname,
                'hr_orig': f"{orig_h}/{valid}",
                'hr_orig_pct': round(orig_h / valid * 100, 1),
                'hr_custom': f"{cust_h}/{valid}",
                'hr_custom_pct': round(cust_h / valid * 100, 1),
                'nuovi': new_m,
                'persi': lost_m,
                'netto': new_m - lost_m,
            }
    report['mercati_derivati'] = mercati_stats

    # ── Calcola punteggio preset ──
    hr_netto = new_hits - lost_hits
    score, score_details = calculate_preset_score(hr_netto, mercati_stats, avg_custom, avg_real)
    report['punteggio'] = {
        'score': score,
        'giudizio': score_giudizio(score),
        'dettagli': score_details,
        'pesi': dict(SCORE_WEIGHTS),
    }

    ts_str = datetime.now().strftime('%Y-%m-%d_%H-%M')
    fname_json = f"report_{ts_str}.json"
    fname_txt = f"report_{ts_str}.txt"
    fpath_json = os.path.join(RESULTS_DIR, fname_json)
    fpath_txt = os.path.join(RESULTS_DIR, fname_txt)

    # Salva JSON
    with open(fpath_json, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Salva TXT leggibile (formattazione curata, TUTTE le partite)
    W = 90  # larghezza blocco principale
    with open(fpath_txt, 'w', encoding='utf-8') as f:

        # ── HEADER ──
        f.write("\n")
        f.write("+" + "=" * (W - 2) + "+\n")
        f.write("|" + "MC TUNING TESTER — REPORT COMPARATIVO".center(W - 2) + "|\n")
        f.write("+" + "=" * (W - 2) + "+\n")
        f.write(f"|  Periodo:  {start_date.strftime('%d/%m/%Y')} -> {end_date.strftime('%d/%m/%Y')}" + " " * (W - 2 - 35) + "|\n")
        f.write(f"|  Partite:  {n}" + " " * (W - 2 - 13 - len(str(n))) + "|\n")
        f.write(f"|  Cicli MC: {cycles}" + " " * (W - 2 - 13 - len(str(cycles))) + "|\n")
        f.write("+" + "=" * (W - 2) + "+\n")

        # ── SEZIONE 1: PARAMETRI ──
        f.write("\n")
        f.write("  PARAMETRI\n")
        f.write("  " + "-" * 66 + "\n")
        f.write(f"  {'Parametro':<32}{'Originale':>10}  {'Custom':>10}  {'':>4}\n")
        f.write("  " + "-" * 66 + "\n")
        for pdef in PARAM_DEFS:
            k = pdef['key']
            ov = original_settings.get(k, '?')
            cv = custom_settings.get(k, '?')
            mk = ' <--' if k in changed_params else ''
            f.write(f"  {k:<32}{str(ov):>10}  {str(cv):>10}  {mk}\n")
        f.write("  " + "-" * 66 + "\n")

        # ── SEZIONE 2: MEDIA GOL ──
        f.write("\n")
        f.write("  MEDIA GOL PER PARTITA\n")
        f.write("  " + "-" * 50 + "\n")
        f.write(f"  {'':22}{'Originale':>10}  {'Custom':>10}  {'Realta':>10}\n")
        f.write("  " + "-" * 50 + "\n")
        f.write(f"  {'Media gol':22}{avg_orig:>10.2f}  {avg_custom:>10.2f}  {avg_real:>10.2f}\n")
        f.write("  " + "-" * 50 + "\n")

        # ── SEZIONE 3: DISTRIBUZIONE GOL ──
        f.write("\n")
        f.write("  DISTRIBUZIONE GOL (% partite nei top4)\n")
        f.write("  " + "-" * 50 + "\n")
        f.write(f"  {'Fascia':>14}{'Originale':>12}{'Custom':>12}{'Realta':>12}\n")
        f.write("  " + "-" * 50 + "\n")
        for label, data_d in distribuzione.items():
            f.write(f"  {label:>14}{data_d['originale_pct']:>11.1f}%{data_d['custom_pct']:>11.1f}%{data_d['realta_pct']:>11.1f}%\n")
        f.write("  " + "-" * 50 + "\n")

        # ── SEZIONE 4: HIT RATE ──
        f.write("\n")
        f.write("  HIT RATE TOP 4\n")
        f.write("  " + "-" * 50 + "\n")
        orig_hr_str = f"{orig_hits}/{n} ({orig_hits/n*100:.1f}%)"
        cust_hr_str = f"{custom_hits}/{n} ({custom_hits/n*100:.1f}%)"
        f.write(f"  {'':22}{'Originale':>14}  {'Custom':>14}\n")
        f.write("  " + "-" * 50 + "\n")
        f.write(f"  {'HR top 4':22}{orig_hr_str:>14}  {cust_hr_str:>14}\n")
        f.write(f"  {'Risultati unici':22}{'':>14}  {'':>14}\n")
        f.write("  " + "-" * 50 + "\n")
        bal = new_hits - lost_hits
        bal_str = f"+{bal}" if bal >= 0 else str(bal)
        f.write(f"  {'Nuovi HIT (custom)':22}{'+' + str(new_hits):>14}\n")
        f.write(f"  {'HIT persi':22}{'-' + str(lost_hits):>14}\n")
        f.write(f"  {'Bilancio netto':22}{bal_str:>14}\n")
        f.write("  " + "-" * 50 + "\n")

        # ── SEZIONE 5: MERCATI DERIVATI ──
        f.write("\n")
        f.write("  MERCATI DERIVATI (dai top4)\n")
        f.write("  " + "-" * 82 + "\n")
        f.write(f"  {'Mercato':<16}{'HR Originale':>16}{'HR Custom':>16}{'Nuovi':>8}{'Persi':>8}{'Netto':>8}\n")
        f.write("  " + "-" * 82 + "\n")
        for mkey, mname in mercati_keys:
            if mkey in mercati_stats:
                ms = mercati_stats[mkey]
                orig_str = f"{ms['hr_orig']} ({ms['hr_orig_pct']:.1f}%)"
                cust_str = f"{ms['hr_custom']} ({ms['hr_custom_pct']:.1f}%)"
                netto = ms['netto']
                netto_str = f"+{netto}" if netto >= 0 else str(netto)
                f.write(f"  {mname:<16}{orig_str:>16}{cust_str:>16}{'+' + str(ms['nuovi']):>8}{'-' + str(ms['persi']):>8}{netto_str:>8}\n")
        f.write("  " + "-" * 82 + "\n")

        # ── SEZIONE 6: PUNTEGGIO PRESET ──
        f.write("\n")
        f.write("  PUNTEGGIO PRESET\n")
        f.write("  " + "-" * 58 + "\n")
        for det in score_details:
            f.write(f"  {det}\n")
        f.write("  " + "-" * 58 + "\n")
        giudizio = report['punteggio']['giudizio']
        f.write(f"  SCORE TOTALE: {score:+.1f}  ({giudizio})\n")
        f.write("  " + "-" * 58 + "\n")

        # ── SEZIONE 7: DETTAGLIO PARTITE ──
        f.write("\n")
        f.write(f"  DETTAGLIO COMPLETO — {n} partite\n")
        f.write("  " + "=" * 148 + "\n")

        # Colonne: N(4) Data(12) Lega(22) Partita(36) Top4Orig(28) Top4Custom(28) Reale(8) Nota(12)
        hdr = (f"  {'#':>4}"
               f"  {'Data':<12}"
               f"{'Lega':<22}"
               f"{'Partita':<36}"
               f"{'Top4 ORIGINALE':<28}"
               f"{'Top4 CUSTOM':<28}"
               f"{'Reale':<8}"
               f"{'Nota'}")
        f.write(hdr + "\n")
        f.write("  " + "=" * 148 + "\n")

        prev_date = None
        for i, d in enumerate(dettaglio, 1):
            # Separatore tra date diverse
            if prev_date and d['data'] != prev_date:
                f.write("  " + "." * 148 + "\n")
            prev_date = d['data']

            orig_t4 = ', '.join(d['top4_orig'])
            cust_t4 = ', '.join(d['top4_custom'])
            casa = d['casa'][:15]
            trasf = d['trasferta'][:15]
            partita = f"{casa} vs {trasf}"
            lega = d['lega'][:20]

            nota = d['nota']
            if nota == 'NEW_HIT':
                nota = '** NEW HIT'
            elif nota == 'PERSO':
                nota = 'X  PERSO'
            elif nota == 'HIT':
                nota = 'OK HIT'
            else:
                nota = ''

            row = (f"  {i:>4}"
                   f"  {d['data']:<12}"
                   f"{lega:<22}"
                   f"{partita:<36}"
                   f"{orig_t4:<28}"
                   f"{cust_t4:<28}"
                   f"{d['reale']:<8}"
                   f"{nota}")
            f.write(row + "\n")

        f.write("  " + "=" * 148 + "\n")

        # ── RIEPILOGO FINALE ──
        f.write("\n")
        f.write(f"  Totale partite:  {n}\n")
        f.write(f"  HIT originale:   {orig_hits}/{n} ({orig_hits/n*100:.1f}%)\n")
        f.write(f"  HIT custom:      {custom_hits}/{n} ({custom_hits/n*100:.1f}%)\n")
        f.write(f"  Bilancio:        {bal_str}\n")
        f.write(f"  SCORE:           {score:+.1f} ({giudizio})\n")
        f.write("\n")
        f.write("  " + "=" * 40 + "\n")
        f.write("  Fine report\n")
        f.write("  " + "=" * 40 + "\n")

    print(f"\n  Report salvato:")
    print(f"    JSON: tools/results/{fname_json}")
    print(f"    TXT:  tools/results/{fname_txt}")
    print(f"    ({n} partite con dettaglio completo)")

    # Aggiorna classifica automaticamente
    in_classifica = update_classifica(RESULTS_DIR, fpath_json)
    if in_classifica:
        print(f"\n  ★ ENTRATO IN CLASSIFICA! (top 5)")
    else:
        print(f"\n  ✗ Score troppo basso — non entra in classifica")
    print(f"    Classifica: tools/results/classifica_preset.txt")

    return fpath_json


# ==================== FASE 4: POST-SIMULAZIONE ====================

def post_simulation(custom_settings, original_settings, changed_params):
    """Chiede all'utente cosa fare con i parametri."""

    if not changed_params:
        print("\n  Nessun parametro modificato — nulla da salvare.")
        return

    print("\n" + "═" * 60)
    print("  COSA VUOI FARE CON QUESTI PARAMETRI?")
    print("═" * 60)
    print()
    print("  [1] APPLICA SU MONGODB")
    print("      Sovrascrive algo_c_config in produzione.")
    print("      I pronostici notturni useranno questi parametri.")
    print()
    print("  [2] SALVA IN LOCALE (file JSON)")
    print("      Puoi ricaricarli la prossima volta.")
    print()
    print("  [3] SCARTA (non salva nulla)")
    print()
    print("  [4] RIPRISTINA ORIGINALI SU MONGODB")
    print("      Rimette i valori ALGO_C di backup.")
    print()

    choice = input("  Scelta [1/2/3/4]: ").strip()

    if choice == '1':
        apply_to_mongodb(custom_settings, original_settings, changed_params)
    elif choice == '2':
        save_preset_local(custom_settings, changed_params)
    elif choice == '4':
        restore_original_mongodb(original_settings)
    else:
        print("\n  Parametri scartati. Nessuna modifica.")


def apply_to_mongodb(custom_settings, original_settings, changed_params):
    """Scrive i parametri custom su MongoDB dopo conferma."""
    print("\n  RIEPILOGO MODIFICHE:")
    for k, (old, new) in changed_params.items():
        print(f"    {k}: {old} → {new}")

    confirm = input("\n  Sei sicuro? Scrivi SI per confermare: ").strip()
    if confirm != 'SI':
        print("  Annullato.")
        return

    # Backup automatico locale
    backup_name = f"backup_pre_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
    backup_path = os.path.join(PRESETS_DIR, backup_name)
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'type': 'backup_before_apply',
            'parameters': {k: original_settings.get(k) for k in changed_params},
            'changes': {k: [v[0], v[0]] for k, v in changed_params.items()},  # old → old
        }, f, indent=2)
    print(f"  Backup salvato: {backup_name}")

    # Aggiorna MongoDB
    ts = db['tuning_settings']
    algo_c_doc = ts.find_one({'_id': 'algo_c_config'})

    if algo_c_doc and 'config' in algo_c_doc and 'ALGO_C' in algo_c_doc['config']:
        config = algo_c_doc['config']['ALGO_C']
        for k, (old, new) in changed_params.items():
            if k in config:
                config[k]['valore'] = new
            else:
                config[k] = {'valore': new}

        ts.update_one(
            {'_id': 'algo_c_config'},
            {'$set': {'config.ALGO_C': config}}
        )
        print(f"\n  ✅ MongoDB aggiornato! {len(changed_params)} parametri modificati.")
    else:
        print("  ⚠️ Documento algo_c_config non trovato su MongoDB!")


def save_preset_local(custom_settings, changed_params):
    """Salva preset in file JSON locale. Se esiste già un preset identico, avvisa."""
    new_params = {p['key']: custom_settings.get(p['key']) for p in PARAM_DEFS}

    # Controlla se esiste già un preset con gli stessi parametri
    for fname in os.listdir(PRESETS_DIR):
        if fname.endswith('.json') and not fname.startswith('backup_'):
            try:
                with open(os.path.join(PRESETS_DIR, fname), 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                if existing.get('parameters') == new_params:
                    ename = existing.get('name', fname)
                    print(f"\n  ⚠️ Esiste già un preset identico: {ename}")
                    overwrite = input(f"  Vuoi salvarne un altro comunque? [s/N]: ").strip().lower()
                    if overwrite != 's':
                        print("  Nessun nuovo preset salvato.")
                        return
                    break
            except Exception:
                continue

    fname = f"tuning_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
    fpath = os.path.join(PRESETS_DIR, fname)

    data = {
        'timestamp': datetime.now().isoformat(),
        'type': 'custom_preset',
        'parameters': new_params,
        'changes': {k: [v[0], v[1]] for k, v in changed_params.items()},
    }

    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    print(f"\n  ✅ Preset salvato: {fname}")


def restore_original_mongodb(original_settings):
    """Ripristina i parametri originali su MongoDB."""
    confirm = input("\n  Ripristinare gli originali su MongoDB? Scrivi SI: ").strip()
    if confirm != 'SI':
        print("  Annullato.")
        return

    # Legge backup più recente dalla cartella presets
    backups = sorted([
        f for f in os.listdir(PRESETS_DIR)
        if f.startswith('backup_pre_') and f.endswith('.json')
    ], reverse=True)

    if backups:
        backup_path = os.path.join(PRESETS_DIR, backups[0])
        with open(backup_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)

        ts = db['tuning_settings']
        algo_c_doc = ts.find_one({'_id': 'algo_c_config'})

        if algo_c_doc and 'config' in algo_c_doc and 'ALGO_C' in algo_c_doc['config']:
            config = algo_c_doc['config']['ALGO_C']
            for k, v in backup_data.get('parameters', {}).items():
                if k in config:
                    config[k]['valore'] = v
                else:
                    config[k] = {'valore': v}

            ts.update_one(
                {'_id': 'algo_c_config'},
                {'$set': {'config.ALGO_C': config}}
            )
            print(f"\n  ✅ Ripristinati valori da {backups[0]}")
        else:
            print("  ⚠️ Documento algo_c_config non trovato!")
    else:
        print("  ⚠️ Nessun backup trovato in presets/")


# ==================== MAIN ====================

def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       MC TUNING TESTER — Test Parametri Monte Carlo     ║")
    print("║       Simula con parametri custom SENZA toccare MongoDB ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # Fase 1: Input
    start_date, end_date, cycles = ask_date_range()

    print(f"\n  Caricamento parametri originali ALGO_C da MongoDB...")
    original_settings = load_original_settings()

    custom_settings, changed_params, preset_name = ask_parameters(original_settings)

    if not changed_params:
        print("\n  ⚠️ Nessun parametro modificato. Eseguo comunque per verifica.")
    else:
        print(f"\n  {len(changed_params)} parametri modificati.")

    # Fase 2: Carica partite
    print(f"\n  Caricamento partite {start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}...")
    matches = get_matches_for_range(start_date, end_date)
    print(f"  Trovate {len(matches)} partite con risultato reale.")

    if not matches:
        print("  ❌ Nessuna partita trovata. Controlla le date.")
        return

    # Fase 3: Simulazione (sempre vs Default ALGO_C da MongoDB)
    print(f"\n  Avvio simulazione MC ({cycles} cicli × {len(matches)} partite)...")
    print(f"  Stima tempo: ~{len(matches) * 2}s")
    print()

    results = run_simulation(matches, cycles, original_settings, custom_settings, changed_params)

    # Fase 4: Report
    print_report(results, changed_params, original_settings, custom_settings, start_date, end_date, cycles)

    # Fase 4b: Chiedi se salvare il report completo
    save_choice = input("\n  Vuoi salvare il report completo con TUTTE le partite? [s/N]: ").strip().lower()
    if save_choice == 's':
        default_name = preset_name or ''
        prompt = f"\n  Nome per questo test [INVIO = '{default_name}']: " if default_name else "\n  Nome per questo test: "
        report_name = input(prompt).strip()
        if not report_name and default_name:
            report_name = default_name
        if not report_name:
            report_name = f"Test {datetime.now().strftime('%H:%M')}"
        save_full_report(results, changed_params, original_settings, custom_settings, start_date, end_date, cycles, nome=report_name)

    # Fase 5: Post-simulazione
    post_simulation(custom_settings, original_settings, changed_params)

    print("\n  Done.\n")


if __name__ == '__main__':
    main()
