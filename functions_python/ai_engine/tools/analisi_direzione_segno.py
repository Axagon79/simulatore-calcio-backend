#!/usr/bin/env python3
"""
Analisi Direzione Segno dei Top 4 MC
Legge un report JSON del mc_tuning_tester e analizza la direzione
del segno (1/X/2) per ogni partita.
"""
import json
import sys
import os
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'results')

# ============================================================
# MAPPA COMPLETA: 81 combinazioni → nota
# {home} = squadra casa, {away} = squadra trasferta
# ============================================================
NOTES_MAP = {
    # ===== 4-0-0: UNANIME =====
    '1111': '{home} nettamente favorito',
    'XXXX': 'Pari netto',
    '2222': '{away} nettamente favorito',

    # ===== 3-1-0: MAGGIORANZA 1 =====
    # 3×1, 1×X
    '111X': '{home} favorito, pareggio improbabile',
    '11X1': '{home} favorito, pareggio improbabile',
    '1X11': '{home} favorito, eventualmente pareggio',
    'X111': '{home} favorito o pareggio',
    # 3×1, 1×2
    '1112': '{home} favorito, vittoria {away} improbabile',
    '1121': '{home} favorito, vittoria {away} improbabile',
    '1211': '{home} favorito, {away} da non sottovalutare',
    '2111': '{home} favorito, partita aperta',

    # ===== 3-1-0: MAGGIORANZA X =====
    # 3×X, 1×1 (posizione non conta)
    'XXX1': 'Pareggio probabile o vittoria {home}',
    'XX1X': 'Pareggio probabile o vittoria {home}',
    'X1XX': 'Pareggio probabile o vittoria {home}',
    '1XXX': 'Pareggio probabile o vittoria {home}',
    # 3×X, 1×2 (posizione non conta)
    'XXX2': 'Pareggio probabile o vittoria {away}',
    'XX2X': 'Pareggio probabile o vittoria {away}',
    'X2XX': 'Pareggio probabile o vittoria {away}',
    '2XXX': 'Pareggio probabile o vittoria {away}',

    # ===== 3-1-0: MAGGIORANZA 2 =====
    # 3×2, 1×X
    '222X': '{away} favorito, pareggio improbabile',
    '22X2': '{away} favorito, eventualmente pareggio',
    '2X22': '{away} favorito, eventualmente pareggio',
    'X222': '{away} favorito o pareggio',
    # 3×2, 1×1
    '2221': '{away} favorito, vittoria {home} improbabile',
    '2212': '{away} favorito, vittoria {home} improbabile',
    '2122': '{away} favorito, {home} da non sottovalutare',
    '1222': '{away} favorito, {home} da non sottovalutare',

    # ===== 2-2-0: 2×1, 2×X (tutte uguali) =====
    '11XX': '{home} favorito o pareggio',
    '1X1X': '{home} favorito o pareggio',
    '1XX1': '{home} favorito o pareggio',
    'X11X': '{home} favorito o pareggio',
    'X1X1': '{home} favorito o pareggio',
    'XX11': '{home} favorito o pareggio',

    # ===== 2-2-0: 2×1, 2×2 =====
    '1122': 'Esito incerto',
    '1212': 'Partita aperta',
    '1221': 'Partita aperta',
    '2112': 'Partita aperta',
    '2121': 'Partita aperta',
    '2211': 'Partita aperta, {away} leggermente favorito',

    # ===== 2-2-0: 2×X, 2×2 =====
    # Top1=X
    'XX22': 'Pareggio o vittoria {away}',
    'X2X2': 'Pareggio o vittoria {away}',
    'X22X': 'Pareggio o vittoria {away}',
    # Top1=2
    '2XX2': 'Vittoria {away} o pareggio',
    '2X2X': 'Vittoria {away} o pareggio',
    '22XX': 'Vittoria {away} o pareggio',

    # ===== 2-1-1: MAGGIORANZA 1 (2×1, 1×X, 1×2) =====
    '11X2': 'Possibile vittoria {home}, partita aperta',
    '112X': '{home} leggermente favorito, partita aperta',
    '1X12': 'Partita aperta, leggermente a favore del {home}',
    '121X': 'Partita aperta',
    '1X21': 'Partita aperta, leggermente a favore del {home}',
    '12X1': 'Partita aperta, leggermente a favore del {home}',
    'X112': '{home} leggermente favorito, partita aperta',
    'X121': 'Partita incerta, {home} leggermente favorito',
    '211X': 'Partita aperta',
    '21X1': 'Partita aperta, {home} leggermente favorito',
    'X211': 'Partita incerta, {home} leggermente favorito',
    '2X11': 'Partita incerta, {home} leggermente favorito',

    # ===== 2-1-1: MAGGIORANZA X (2×X, 1×1, 1×2) =====
    'XX12': 'Partita incerta',
    'XX21': 'Partita incerta',
    'X1X2': 'Partita incerta',
    'X2X1': 'Partita incerta',
    'X12X': 'Partita incerta',
    'X21X': 'Partita incerta',
    '1XX2': 'Partita aperta, incerta',
    '2XX1': 'Partita incerta',
    '1X2X': 'Partita aperta, incerta',
    '2X1X': 'Partita incerta',
    '12XX': 'Partita incerta',
    '21XX': 'Partita incerta',

    # ===== 2-1-1: MAGGIORANZA 2 (2×2, 1×1, 1×X) =====
    '221X': '{away} favorito, partita incerta',
    '22X1': '{away} favorito, partita incerta',
    '212X': 'Partita aperta, {away} leggermente favorito',
    '2X21': 'Partita incerta, {away} leggermente favorito',
    '21X2': 'Partita incerta, {away} leggermente favorito',
    '2X12': 'Partita incerta, {away} leggermente favorito',
    '122X': 'Partita incerta, leggermente a favore del {away}',
    'X221': '{away} leggermente favorito, partita incerta',
    '12X2': 'Partita incerta, leggermente a favore del {away}',
    'X212': 'Partita incerta, {away} leggermente favorito',
    '1X22': 'Partita aperta, leggermente a favore del {away}',
    'X122': 'Partita incerta, {away} leggermente favorito',
}


def score_to_sign(score):
    """Converte un risultato (es. '2-1') in segno (1, X, 2)."""
    h, a = map(int, score.split('-'))
    if h > a:
        return '1'
    if h == a:
        return 'X'
    return '2'


def get_signs(top4):
    """Converte i top4 risultati in lista di segni."""
    return [score_to_sign(s) for s in top4]


def get_top2(signs):
    """Restituisce i due segni piu presenti."""
    counts = Counter(signs)
    ranked = sorted(counts.keys(), key=lambda s: (-counts[s], signs.index(s)))
    if len(ranked) >= 2:
        return f"{ranked[0]},{ranked[1]}"
    return ranked[0]


def get_dir(signs):
    """Restituisce il segno dominante (direzione)."""
    counts = Counter(signs)
    max_count = max(counts.values())
    candidates = [s for s in ['1', 'X', '2'] if counts.get(s, 0) == max_count]
    if len(candidates) == 1:
        return candidates[0]
    return signs[0]


def get_nota(signs, home, away):
    """Genera la nota dalla mappa delle 81 combinazioni."""
    pattern = ''.join(signs)
    template = NOTES_MAP.get(pattern, '???')
    return template.format(home='Segno 1', away='Segno 2')


# ============================================================
# FASCE DI CERTEZZA DELLE NOTE
# A = Dominio (nettamente favorito)
# B = Favorito chiaro
# C = Leggero vantaggio
# D1 = Aperta (attesa GG, entrambe segnano)
# D2 = Incerta (qualsiasi risultato plausibile)
# D1D2 = Sia aperta che incerta
# ============================================================
FASCIA_NOTE = {
    # A — Dominio
    'Segno 1 nettamente favorito': 'A',
    'Segno 2 nettamente favorito': 'A',
    # B — Favorito chiaro
    'Segno 1 favorito, pareggio improbabile': 'B',
    'Segno 2 favorito, pareggio improbabile': 'B',
    'Segno 1 favorito, vittoria Segno 2 improbabile': 'B',
    'Segno 2 favorito, vittoria Segno 1 improbabile': 'B',
    'Segno 1 favorito, eventualmente pareggio': 'B',
    'Segno 2 favorito, eventualmente pareggio': 'B',
    # C — Leggero vantaggio
    'Segno 1 favorito, Segno 2 da non sottovalutare': 'C',
    'Segno 2 favorito, Segno 1 da non sottovalutare': 'C',
    'Segno 1 favorito, partita aperta': 'C',
    'Segno 2 favorito, partita incerta': 'C',
    'Segno 1 favorito o pareggio': 'C',
    'Segno 2 favorito o pareggio': 'C',
    'Segno 1 leggermente favorito, partita aperta': 'C',
    'Segno 2 leggermente favorito, partita incerta': 'C',
    'Pareggio probabile o vittoria Segno 1': 'C',
    'Pareggio probabile o vittoria Segno 2': 'C',
    'Possibile vittoria Segno 1, partita aperta': 'C',
    'Vittoria Segno 2 o pareggio': 'C',
    # D1 — Aperta (attesa GG)
    'Partita aperta': 'D1',
    'Partita aperta, Segno 1 leggermente favorito': 'D1',
    'Partita aperta, Segno 2 leggermente favorito': 'D1',
    'Partita aperta, leggermente a favore del Segno 1': 'D1',
    'Partita aperta, leggermente a favore del Segno 2': 'D1',
    # D2 — Incerta (qualsiasi risultato)
    'Partita incerta': 'D2',
    'Partita incerta, Segno 1 leggermente favorito': 'D2',
    'Partita incerta, Segno 2 leggermente favorito': 'D2',
    'Partita incerta, leggermente a favore del Segno 2': 'D2',
    'Esito incerto': 'D2',
    'Pari netto': 'D2',
    'Pareggio o vittoria Segno 2': 'D2',
    # D1D2 — Sia aperta che incerta
    'Partita aperta, incerta': 'D1D2',
}

# Ordine numerico fasce per calcolo distanza
FASCIA_ORD = {'A': 0, 'B': 1, 'C': 2, 'D1': 3, 'D2': 3, 'D1D2': 3}


def get_fascia_nota(nota):
    """Restituisce la fascia della nota."""
    return FASCIA_NOTE.get(nota, 'D2')


def get_fascia_reale(score):
    """Restituisce la fascia reale del risultato.
    Scarto 3+ → A, Scarto 2 → B, Scarto 1 senza GG → C,
    Scarto 1 con GG → D1, Pareggio con gol → D1, 0-0 → D2
    """
    h, a = map(int, score.split('-'))
    scarto = abs(h - a)
    gg = h > 0 and a > 0
    if scarto >= 3:
        return 'A'
    if scarto == 2:
        return 'B'
    if scarto == 1:
        if gg:
            return 'D1'
        return 'C'
    # Pareggio
    if gg:
        return 'D1'
    return 'D2'


def calcola_distanza_fascia(fascia_nota, fascia_reale, nota='', score=''):
    """Calcola la distanza tra fascia della nota e fascia reale.
    Tiene conto di tolleranze:
    - Se la nota menziona 'pareggio' e il risultato è pareggio → distanza ridotta
    - Se la nota dice 'favorito' e il segno è corretto → distanza ridotta
    - Per D1D2: restituisce la distanza minima (piu favorevole)
    """
    ord_reale = FASCIA_ORD[fascia_reale]

    if fascia_nota == 'D1D2':
        dist = min(abs(FASCIA_ORD['D1'] - ord_reale), abs(FASCIA_ORD['D2'] - ord_reale))
    else:
        dist = abs(FASCIA_ORD[fascia_nota] - ord_reale)

    if dist == 0:
        return 0

    # Tolleranza: nota menziona 'pareggio' e risultato è pareggio
    nota_lower = nota.lower()
    if score:
        h, a = map(int, score.split('-'))
        is_pareggio = (h == a)
        segno_reale = '1' if h > a else ('X' if h == a else '2')

        if is_pareggio and ('pareggio' in nota_lower or 'pari' in nota_lower):
            dist = max(0, dist - 1)

        # Tolleranza: nota dice 'favorito' e il segno favorito ha effettivamente vinto
        if 'favorit' in nota_lower and segno_reale != 'X':
            # Determina chi è il favorito nella nota
            if ('segno 1' in nota_lower and segno_reale == '1') or \
               ('segno 2' in nota_lower and segno_reale == '2'):
                dist = max(0, dist - 1)

    return dist


def get_consensus_type(signs):
    """Restituisce il tipo di consenso: unanime/chiaro/split/tripla."""
    counts = Counter(signs)
    max_c = max(counts.values())
    n_unique = len(counts)
    if max_c == 4:
        return 'unanime'
    if max_c == 3:
        return 'chiaro'
    if n_unique == 2:
        return 'split'
    return 'tripla'


def main():
    # Trova il report
    if len(sys.argv) >= 2:
        report_path = sys.argv[1]
        if not os.path.isabs(report_path):
            report_path = os.path.join(RESULTS_DIR, report_path)
    else:
        reports = sorted([
            f for f in os.listdir(RESULTS_DIR)
            if f.startswith('report_') and f.endswith('.json')
        ])
        if not reports:
            print("  Nessun report trovato!")
            return
        report_path = os.path.join(RESULTS_DIR, reports[-1])
        print(f"  Ultimo report: {os.path.basename(report_path)}")

    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    partite = report.get('partite', [])
    nome = report.get('nome', 'N/A')
    baseline = report.get('baseline', 'N/A')

    # File output automatico
    out_name = os.path.basename(report_path).replace('report_', 'direzione_').replace('.json', '.txt')
    out_path = os.path.join(RESULTS_DIR, out_name)
    out_file = open(out_path, 'w', encoding='utf-8')

    def out(text=''):
        print(text)
        out_file.write(text + '\n')

    # ============================================================
    # HEADER
    # ============================================================
    out()
    out(f"  {'=' * 160}")
    out(f"  ANALISI DIREZIONE SEGNO — {nome}")
    out(f"  Baseline: {baseline}")
    out(f"  Partite: {len(partite)}")
    out(f"  {'=' * 160}")
    out()

    # Colonne
    header = (
        f"  {'Data':<10}  {'Partita':<30}  "
        f"{'Segni':>4}  {'Top2':>5}  {'Dir':>3}  {'Nota ORIG':<45}  "
        f"{'Segni':>4}  {'Top2':>5}  {'Dir':>3}  {'Nota CUSTOM':<45}  "
        f"{'Reale':>5}  {'OK':>2}"
    )
    out(header)
    out(f"  {'-' * 158}")

    # ============================================================
    # STATISTICHE
    # ============================================================
    stats_orig = {'unanime': [0, 0], 'chiaro': [0, 0], 'split': [0, 0], 'tripla': [0, 0]}
    stats_cust = {'unanime': [0, 0], 'chiaro': [0, 0], 'split': [0, 0], 'tripla': [0, 0]}
    dir_match_orig = 0
    dir_match_cust = 0
    dir_changed = 0
    total = 0
    note_identiche = 0
    note_diverse = 0
    note_dir_cambiata = 0
    note_dir_uguale_intensita_diversa = 0
    transizioni = Counter()  # conta le coppie (nota_orig, nota_custom)
    spostamenti_giusti = 0    # CUSTOM si avvicina alla realtà
    spostamenti_sbagliati = 0  # CUSTOM si allontana dalla realtà
    spostamenti_neutri = 0     # stessa distanza
    esempi_giusti = []
    esempi_sbagliati = []

    for m in partite:
        home = m['casa']
        away = m['trasferta']
        reale = m['reale']
        reale_sign = score_to_sign(reale)

        signs_o = get_signs(m['top4_orig'])
        signs_c = get_signs(m['top4_custom'])

        pattern_o = ''.join(signs_o)
        pattern_c = ''.join(signs_c)

        top2_o = get_top2(signs_o)
        top2_c = get_top2(signs_c)

        dir_o = get_dir(signs_o)
        dir_c = get_dir(signs_c)

        nota_o = get_nota(signs_o, home, away)
        nota_c = get_nota(signs_c, home, away)

        ok_o = '✓' if dir_o == reale_sign else '✗'
        ok_c = '✓' if dir_c == reale_sign else '✗'

        # Nome partita troncato
        partita_str = f"{home[:13]} vs {away[:13]}"

        row = (
            f"  {m['data']:<10}  {partita_str:<30}  "
            f"{pattern_o:>4}  {top2_o:>5}  {dir_o:>3}  {nota_o:<45.45}  "
            f"{pattern_c:>4}  {top2_c:>5}  {dir_c:>3}  {nota_c:<45.45}  "
            f"{reale_sign}({reale})  {ok_o}{ok_c}"
        )
        out(row)

        # Aggiorna stats
        total += 1
        cons_o = get_consensus_type(signs_o)
        cons_c = get_consensus_type(signs_c)

        stats_orig[cons_o][0] += 1
        if dir_o == reale_sign:
            stats_orig[cons_o][1] += 1
            dir_match_orig += 1

        stats_cust[cons_c][0] += 1
        if dir_c == reale_sign:
            stats_cust[cons_c][1] += 1
            dir_match_cust += 1

        if dir_o != dir_c:
            dir_changed += 1

        # Confronto note ORIG vs CUSTOM
        if nota_o == nota_c:
            note_identiche += 1
        else:
            note_diverse += 1
            transizioni[(nota_o, nota_c)] += 1
            if dir_o != dir_c:
                note_dir_cambiata += 1
            else:
                note_dir_uguale_intensita_diversa += 1

            # Valutazione spostamento: CUSTOM si è avvicinato alla realtà?
            fascia_o = get_fascia_nota(nota_o)
            fascia_c = get_fascia_nota(nota_c)
            fascia_r = get_fascia_reale(reale)
            dist_o = calcola_distanza_fascia(fascia_o, fascia_r, nota_o, reale)
            dist_c = calcola_distanza_fascia(fascia_c, fascia_r, nota_c, reale)
            info = f"{home} vs {away} ({reale}): \"{nota_o}\" [{fascia_o}] → \"{nota_c}\" [{fascia_c}] [realtà: {fascia_r}]"
            if dist_c < dist_o:
                spostamenti_giusti += 1
                if len(esempi_giusti) < 5:
                    esempi_giusti.append(info)
            elif dist_c > dist_o:
                spostamenti_sbagliati += 1
                if len(esempi_sbagliati) < 5:
                    esempi_sbagliati.append(info)
            else:
                spostamenti_neutri += 1

    # ============================================================
    # RIEPILOGO
    # ============================================================
    out()
    out(f"  {'=' * 100}")
    out(f"  RIEPILOGO DIREZIONE SEGNO")
    out(f"  {'=' * 100}")
    out()

    out(f"  {'Tipo consenso':<20}  {'ORIG':>10}  {'HR% ORIG':>10}  {'CUSTOM':>10}  {'HR% CUSTOM':>10}")
    out(f"  {'-' * 66}")

    for tipo in ['unanime', 'chiaro', 'split', 'tripla']:
        n_o, hit_o = stats_orig[tipo]
        n_c, hit_c = stats_cust[tipo]
        hr_o = f"{hit_o / n_o * 100:.1f}%" if n_o > 0 else '-'
        hr_c = f"{hit_c / n_c * 100:.1f}%" if n_c > 0 else '-'
        label = {
            'unanime': 'Unanime (4/4)',
            'chiaro': 'Chiaro (3/4)',
            'split': 'Split (2/2)',
            'tripla': 'Tripla (2/1/1)',
        }[tipo]
        out(f"  {label:<20}  {n_o:>10}  {hr_o:>10}  {n_c:>10}  {hr_c:>10}")

    out(f"  {'-' * 66}")
    hr_tot_o = f"{dir_match_orig / total * 100:.1f}%" if total > 0 else '-'
    hr_tot_c = f"{dir_match_cust / total * 100:.1f}%" if total > 0 else '-'
    out(f"  {'TOTALE':<20}  {total:>10}  {hr_tot_o:>10}  {total:>10}  {hr_tot_c:>10}")

    out()
    out(f"  Direzione cambiata (orig → custom): {dir_changed}/{total} ({dir_changed / total * 100:.1f}%)")
    out()

    # ============================================================
    # CONFRONTO NOTE ORIG vs CUSTOM
    # ============================================================
    out(f"  {'=' * 100}")
    out(f"  CONFRONTO NOTE: ORIG vs CUSTOM")
    out(f"  {'=' * 100}")
    out()

    pct_id = f"{note_identiche / total * 100:.1f}%" if total > 0 else '-'
    pct_div = f"{note_diverse / total * 100:.1f}%" if total > 0 else '-'
    out(f"  Note IDENTICHE:                    {note_identiche:>5} / {total}  ({pct_id})")
    out(f"  Note DIVERSE:                      {note_diverse:>5} / {total}  ({pct_div})")
    out()

    if note_diverse > 0:
        pct_dir = f"{note_dir_cambiata / note_diverse * 100:.1f}%"
        pct_int = f"{note_dir_uguale_intensita_diversa / note_diverse * 100:.1f}%"
        out(f"  Tra le note diverse:")
        out(f"    Direzione CAMBIATA (1↔X↔2):     {note_dir_cambiata:>5} / {note_diverse}  ({pct_dir})")
        out(f"    Stessa direzione, tono diverso:  {note_dir_uguale_intensita_diversa:>5} / {note_diverse}  ({pct_int})")
        out()

        # Top transizioni
        top_trans = transizioni.most_common()
        out(f"  TOP TRANSIZIONI (nota ORIG → nota CUSTOM):")
        out(f"  {'-' * 95}")
        for (n_from, n_to), count in top_trans:
            out(f"    {count:>4}x  {n_from:<45}  →  {n_to}")
        out()

    # ============================================================
    # RESOCONTO FINALE IN LINGUAGGIO NATURALE
    # ============================================================
    out(f"  {'=' * 100}")
    out(f"  RESOCONTO FINALE")
    out(f"  {'=' * 100}")
    out()

    # 1. Impatto del preset
    pct_diverse_val = note_diverse / total * 100 if total > 0 else 0
    if pct_diverse_val < 10:
        impatto = "molto conservativo: cambia pochissime letture"
    elif pct_diverse_val < 25:
        impatto = "moderato: sposta una partita su quattro"
    elif pct_diverse_val < 40:
        impatto = "significativo: modifica circa un terzo delle letture"
    else:
        impatto = "aggressivo: stravolge quasi metà delle letture"
    out(f"  Il preset CUSTOM è {impatto} ({pct_diverse_val:.1f}% note diverse).")
    out()

    # 2. Tipo di cambiamento
    if note_diverse > 0:
        pct_dir_val = note_dir_cambiata / note_diverse * 100
        pct_int_val = note_dir_uguale_intensita_diversa / note_diverse * 100
        if pct_dir_val > 60:
            out(f"  Quando cambia, lo fa in modo FORTE: nel {pct_dir_val:.0f}% dei casi ribalta la direzione")
            out(f"  del pronostico (es. da \"Segno 1 favorito\" a \"Partita incerta\").")
        elif pct_dir_val > 35:
            out(f"  I cambiamenti sono MISTI: {pct_dir_val:.0f}% ribaltano la direzione,")
            out(f"  {pct_int_val:.0f}% cambiano solo il grado di certezza.")
        else:
            out(f"  I cambiamenti sono perlopiù di SFUMATURA: nel {pct_int_val:.0f}% dei casi cambia")
            out(f"  solo il tono (es. da \"nettamente favorito\" a \"favorito\"), non la direzione.")
        out()

    # 3. Confronto hit rate direzione
    if total > 0:
        hr_o_val = dir_match_orig / total * 100
        hr_c_val = dir_match_cust / total * 100
        delta_hr = hr_c_val - hr_o_val
        if abs(delta_hr) < 0.5:
            out(f"  Hit rate direzione: ORIG {hr_o_val:.1f}% vs CUSTOM {hr_c_val:.1f}% → praticamente uguali.")
        elif delta_hr > 0:
            out(f"  Hit rate direzione: ORIG {hr_o_val:.1f}% vs CUSTOM {hr_c_val:.1f}% → CUSTOM migliora di {delta_hr:+.1f} punti.")
        else:
            out(f"  Hit rate direzione: ORIG {hr_o_val:.1f}% vs CUSTOM {hr_c_val:.1f}% → CUSTOM peggiora di {delta_hr:+.1f} punti.")
        out()

    # 4. Transizione più frequente
    if note_diverse > 0:
        top1 = transizioni.most_common(1)[0]
        (n_from, n_to), count = top1
        out(f"  Transizione più frequente ({count}x):")
        out(f"    \"{n_from}\" → \"{n_to}\"")
        # Interpretazione
        if 'incert' in n_to.lower() or 'aperta' in n_to.lower():
            if 'favorit' in n_from.lower() or 'nettamente' in n_from.lower():
                out(f"  → Il CUSTOM tende a rendere MENO CERTE le partite che l'ORIG dava per decise.")
        elif 'favorit' in n_to.lower() or 'nettamente' in n_to.lower():
            if 'incert' in n_from.lower() or 'aperta' in n_from.lower():
                out(f"  → Il CUSTOM tende a dare PIÙ CERTEZZA a partite che l'ORIG vedeva incerte.")
        out()

    # 5. Qualità degli spostamenti
    if note_diverse > 0:
        out(f"  QUALITÀ DEGLI SPOSTAMENTI (le note diverse erano giustificate dal risultato reale?)")
        out(f"  Fasce nota: A=dominio, B=favorito chiaro, C=leggero vantaggio, D1=aperta (GG), D2=incerta")
        out(f"  Fasce reale: A=scarto 3+, B=scarto 2, C=scarto 1 no GG, D1=scarto 0-1 con GG, D2=0-0")
        out()
        tot_spost = spostamenti_giusti + spostamenti_sbagliati + spostamenti_neutri
        pct_g = f"{spostamenti_giusti / tot_spost * 100:.1f}%" if tot_spost > 0 else '-'
        pct_s = f"{spostamenti_sbagliati / tot_spost * 100:.1f}%" if tot_spost > 0 else '-'
        pct_n = f"{spostamenti_neutri / tot_spost * 100:.1f}%" if tot_spost > 0 else '-'
        out(f"    Spostamenti GIUSTI (CUSTOM più vicino alla realtà):    {spostamenti_giusti:>5} / {tot_spost}  ({pct_g})")
        out(f"    Spostamenti SBAGLIATI (CUSTOM più lontano):            {spostamenti_sbagliati:>5} / {tot_spost}  ({pct_s})")
        out(f"    Spostamenti NEUTRI (stessa distanza):                  {spostamenti_neutri:>5} / {tot_spost}  ({pct_n})")
        out()

        if spostamenti_giusti > spostamenti_sbagliati:
            ratio = spostamenti_giusti / spostamenti_sbagliati if spostamenti_sbagliati > 0 else float('inf')
            if ratio > 2:
                out(f"  → Il CUSTOM quando cambia nota, lo fa BENE: {ratio:.1f}x più spostamenti giusti che sbagliati.")
            else:
                out(f"  → Il CUSTOM cambia nota con un leggero vantaggio: {ratio:.1f}x giusti vs sbagliati.")
        elif spostamenti_sbagliati > spostamenti_giusti:
            ratio = spostamenti_sbagliati / spostamenti_giusti if spostamenti_giusti > 0 else float('inf')
            if ratio > 2:
                out(f"  → Il CUSTOM quando cambia nota, lo fa MALE: {ratio:.1f}x più spostamenti sbagliati che giusti.")
            else:
                out(f"  → Il CUSTOM cambia nota con un leggero svantaggio: {ratio:.1f}x sbagliati vs giusti.")
        else:
            out(f"  → Gli spostamenti sono equamente distribuiti tra giusti e sbagliati.")
        out()

        if esempi_giusti:
            out(f"  Esempi di spostamenti GIUSTI:")
            for es in esempi_giusti:
                out(f"    ✓ {es}")
            out()
        if esempi_sbagliati:
            out(f"  Esempi di spostamenti SBAGLIATI:")
            for es in esempi_sbagliati:
                out(f"    ✗ {es}")
            out()

    # 6. Giudizio finale
    out(f"  {'─' * 60}")
    if total > 0:
        hr_o_val = dir_match_orig / total * 100
        hr_c_val = dir_match_cust / total * 100
        delta_hr = hr_c_val - hr_o_val
        if delta_hr > 2:
            giudizio_dir = "POSITIVO"
        elif delta_hr > 0:
            giudizio_dir = "LEGGERMENTE POSITIVO"
        elif delta_hr > -2:
            giudizio_dir = "NEUTRO"
        else:
            giudizio_dir = "NEGATIVO"

        if note_diverse > 0 and (spostamenti_giusti + spostamenti_sbagliati) > 0:
            ratio_gs = spostamenti_giusti / (spostamenti_giusti + spostamenti_sbagliati) * 100
            if ratio_gs > 60:
                giudizio_qual = "POSITIVO"
            elif ratio_gs > 45:
                giudizio_qual = "NEUTRO"
            else:
                giudizio_qual = "NEGATIVO"
        else:
            giudizio_qual = "N/A"

        out(f"  GIUDIZIO DIREZIONE:         {giudizio_dir} ({delta_hr:+.1f}pp hit rate)")
        out(f"  GIUDIZIO QUALITÀ SPOSTAM.:  {giudizio_qual} ({spostamenti_giusti} giusti vs {spostamenti_sbagliati} sbagliati)")
    out()

    out_file.close()
    print(f"  ✅ Report salvato: {out_path}")
    print()


if __name__ == '__main__':
    main()
