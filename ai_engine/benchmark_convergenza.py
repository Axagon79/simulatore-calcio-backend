#!/usr/bin/env python3
"""
🎯 BENCHMARK CONVERGENZA MONTE CARLO
=====================================
Script interattivo per analizzare come la stabilità dei pronostici
varia al crescere dei cicli Monte Carlo, per ogni algoritmo.

Genera tabelle + grafici di convergenza.
"""

import os
import sys
import time
import re
import numpy as np
from collections import Counter
from datetime import datetime

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
for p in [project_root, current_dir, os.path.join(current_dir, 'engine')]:
    if p not in sys.path:
        sys.path.insert(0, p)

from config import db
from engine.engine_core import predict_match, preload_match_data
from engine.goals_converter import calculate_goals_from_engine

# --- IMPORT PRODUCTION (per Sistema C, identico alla pipeline notturna) ---
def _load_prod_module(filename, module_name):
    """Carica un modulo dalla versione PRODUCTION (functions_python/)."""
    import importlib.util
    prod_file = os.path.join(project_root, 'functions_python', 'ai_engine', 'engine', filename)
    spec = importlib.util.spec_from_file_location(module_name, prod_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_prod_gc = _load_prod_module('goals_converter.py', 'goals_converter_prod')
calculate_goals_PROD = _prod_gc.calculate_goals_from_engine
load_tuning_PROD = _prod_gc.load_tuning

_prod_ec = _load_prod_module('engine_core.py', 'engine_core_prod')
predict_match_PROD = _prod_ec.predict_match
preload_match_data_PROD = _prod_ec.preload_match_data

# Pre-carica settings ALGO_C in RAM (come fa run_daily_predictions_engine_c.py)
_ALGO_C_SETTINGS = load_tuning_PROD(6)  # mode=6 in produzione = ALGO_C
print("\n" + "=" * 60)
print("🔧 ALGO 7 (Sistema C) — Settings da MongoDB algo_c_config:")
print(f"   DIVISORE_MEDIA_GOL     = {_ALGO_C_SETTINGS.get('DIVISORE_MEDIA_GOL', 'MANCANTE')}")
print(f"   POTENZA_WINSHIFT       = {_ALGO_C_SETTINGS.get('POTENZA_FAVORITA_WINSHIFT', 'MANCANTE')}")
print(f"   IMPATTO_DIFESA_TATTICA = {_ALGO_C_SETTINGS.get('IMPATTO_DIFESA_TATTICA', 'MANCANTE')}")
print(f"   TETTO_MAX_GOL_ATTESI   = {_ALGO_C_SETTINGS.get('TETTO_MAX_GOL_ATTESI', 'MANCANTE')}")
print("=" * 60 + "\n")

# --- FLAG INTERRUZIONE (Ctrl+C) ---
_interrupted = False

# --- CONFIGURAZIONE ---
CYCLE_LEVELS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 150, 200, 250, 300, 500]
RIPETIZIONI = 5
ALGO_IDS = {
    1: "Statistico",
    2: "Dinamico",
    3: "Tattico",
    4: "Caos",
    5: "Master",
    6: "MonteCarlo",
    7: "Sistema C"
}

# Colori per i grafici (uno per algoritmo)
ALGO_COLORS = {1: '#e74c3c', 2: '#3498db', 3: '#2ecc71', 4: '#f39c12', 5: '#9b59b6', 6: '#1abc9c', 7: '#e67e22'}


def suppress_output():
    """Context manager per silenziare stdout."""
    import contextlib, io
    return contextlib.redirect_stdout(io.StringIO())


def get_round_number(round_name):
    try:
        num = re.search(r'\d+', str(round_name))
        return int(num.group()) if num else 0
    except:
        return 0


def scegli_campionato():
    """Mostra lista campionati e fa scegliere."""
    leagues = sorted(db.h2h_by_round.distinct("league"))
    if not leagues:
        print("❌ Nessun campionato trovato nel DB!")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("⚽ CAMPIONATI DISPONIBILI")
    print("=" * 60)
    for i, lg in enumerate(leagues, 1):
        print(f"  {i:2d}. {lg}")

    while True:
        try:
            scelta = int(input(f"\n👉 Scegli campionato (1-{len(leagues)}): "))
            if 1 <= scelta <= len(leagues):
                return leagues[scelta - 1]
        except (ValueError, KeyboardInterrupt):
            pass
        print("❌ Scelta non valida.")


def scegli_giornata(league):
    """Mostra giornate del campionato e fa scegliere."""
    rounds = list(db.h2h_by_round.find({"league": league}))
    rounds.sort(key=lambda x: get_round_number(x.get('round_name', '0')))

    if not rounds:
        print(f"❌ Nessuna giornata trovata per {league}!")
        return None

    print(f"\n{'=' * 60}")
    print(f"📅 GIORNATE — {league}")
    print("=" * 60)
    for i, r in enumerate(rounds, 1):
        n_matches = len(r.get('matches', []))
        print(f"  {i:2d}. {r.get('round_name', '?')}  ({n_matches} partite)")

    while True:
        try:
            scelta = int(input(f"\n👉 Scegli giornata (1-{len(rounds)}): "))
            if 1 <= scelta <= len(rounds):
                return rounds[scelta - 1]
        except (ValueError, KeyboardInterrupt):
            pass
        print("❌ Scelta non valida.")


def scegli_partita(round_doc):
    """Mostra partite della giornata e fa scegliere."""
    matches = round_doc.get('matches', [])
    if not matches:
        print("❌ Nessuna partita in questa giornata!")
        return None

    print(f"\n{'=' * 60}")
    print(f"🏟️  PARTITE — {round_doc.get('round_name', '?')}")
    print("=" * 60)
    for i, m in enumerate(matches, 1):
        home = m.get('home', '?')
        away = m.get('away', '?')
        real = m.get('real_score', '')
        extra = f"  [{real}]" if real and real != 'null' else ""
        print(f"  {i:2d}. {home} vs {away}{extra}")

    while True:
        try:
            scelta = int(input(f"\n👉 Scegli partita (1-{len(matches)}): "))
            if 1 <= scelta <= len(matches):
                return matches[scelta - 1]
        except (ValueError, KeyboardInterrupt):
            pass
        print("❌ Scelta non valida.")


def run_cicli(algo_id, preloaded, home, away, cycles):
    """Esegue N cicli Monte Carlo per un singolo algoritmo. Ritorna (lista '1'/'X'/'2', lista scores 'gh-ga')."""
    # Algo 7 = Sistema C: usa predict_match mode=6 + goals_converter PRODUCTION con settings_cache
    is_sistema_c = (algo_id == 7)
    engine_mode = 6 if is_sistema_c else algo_id
    results_1x2 = []
    scores = []
    for _ in range(cycles):
        if _interrupted:
            break
        try:
            with suppress_output():
                if is_sistema_c:
                    s_h, s_a, r_h, r_a = predict_match_PROD(home, away, mode=6, preloaded_data=preloaded)
                else:
                    s_h, s_a, r_h, r_a = predict_match(home, away, mode=engine_mode, preloaded_data=preloaded)
            if s_h is None:
                continue
            with suppress_output():
                if is_sistema_c:
                    # IDENTICO alla produzione: goals_converter PROD + settings_cache + algo_mode=6
                    gh, ga, *_ = calculate_goals_PROD(
                        s_h, s_a, r_h, r_a, algo_mode=6,
                        home_name=home, away_name=away, debug_mode=False,
                        settings_cache=_ALGO_C_SETTINGS
                    )
                else:
                    gh, ga, *_ = calculate_goals_from_engine(
                        s_h, s_a, r_h, r_a, algo_mode=engine_mode,
                        home_name=home, away_name=away, debug_mode=False
                    )
            scores.append(f"{gh}-{ga}")
            if gh > ga:
                results_1x2.append('1')
            elif ga > gh:
                results_1x2.append('2')
            else:
                results_1x2.append('X')
        except:
            continue
    return results_1x2, scores


def calcola_prob(results_1x2):
    """Da lista di '1'/'X'/'2' calcola probabilità percentuali."""
    n = len(results_1x2)
    if n == 0:
        return {'1': 0, 'X': 0, '2': 0}
    c = Counter(results_1x2)
    return {
        '1': c.get('1', 0) / n * 100,
        'X': c.get('X', 0) / n * 100,
        '2': c.get('2', 0) / n * 100
    }


def risultato_esatto(scores):
    """Dato una lista di scores '2-1', '0-0', ... ritorna il più frequente."""
    if not scores:
        return "N/A"
    return Counter(scores).most_common(1)[0][0]


def top4_risultati(scores):
    """Ritorna i top 4 risultati esatti con percentuale."""
    if not scores:
        return []
    n = len(scores)
    return [(s, c / n * 100) for s, c in Counter(scores).most_common(4)]


def calcola_stats_gol(scores):
    """Calcola statistiche gol da lista di scores 'gh-ga'."""
    if not scores:
        return {}
    gol_h = []
    gol_a = []
    for s in scores:
        parts = s.split('-')
        gh, ga = int(parts[0]), int(parts[1])
        gol_h.append(gh)
        gol_a.append(ga)
    gol_tot = [h + a for h, a in zip(gol_h, gol_a)]
    n = len(scores)
    return {
        'avg_gol_casa': np.mean(gol_h),
        'avg_gol_ospite': np.mean(gol_a),
        'avg_gol_totali': np.mean(gol_tot),
        'max_gol_casa': max(gol_h),
        'max_gol_ospite': max(gol_a),
        'over_1_5': sum(1 for t in gol_tot if t > 1.5) / n * 100,
        'under_1_5': sum(1 for t in gol_tot if t < 1.5) / n * 100,
        'over_2_5': sum(1 for t in gol_tot if t > 2.5) / n * 100,
        'under_2_5': sum(1 for t in gol_tot if t < 2.5) / n * 100,
        'over_3_5': sum(1 for t in gol_tot if t > 3.5) / n * 100,
        'under_3_5': sum(1 for t in gol_tot if t < 3.5) / n * 100,
        'gg': sum(1 for h, a in zip(gol_h, gol_a) if h > 0 and a > 0) / n * 100,
        'ng': sum(1 for h, a in zip(gol_h, gol_a) if h == 0 or a == 0) / n * 100,
        're_top': Counter(scores).most_common(1)[0],
    }


def benchmark_partita(home, away, preloaded):
    """Esegue il benchmark completo per una partita: tutti gli algo x tutti i livelli cicli x RIPETIZIONI ripetizioni."""

    # results[algo_id][cycle_level] = lista di 20 dict {1: %, X: %, 2: %}
    # details[algo_id][cycle_level] = lista di 20 tuple (prob_dict, score_esatto)
    results = {}
    details = {}

    total_tests = len(ALGO_IDS) * len(CYCLE_LEVELS) * RIPETIZIONI
    done = 0
    t_start = time.time()

    for algo_id, algo_name in ALGO_IDS.items():
        if _interrupted:
            print("\n⛔ Interrotto dall'utente.")
            break
        results[algo_id] = {}
        details[algo_id] = {}
        print(f"\n{'─' * 60}")
        print(f"🔬 ALGORITMO {algo_id}: {algo_name}")
        print(f"{'─' * 60}")

        for cycles in CYCLE_LEVELS:
            if _interrupted:
                break
            reps = []
            dets = []
            print(f"  ⏳ {cycles:>6,} cicli x {RIPETIZIONI} ripetizioni... ", end="", flush=True)
            t0 = time.time()

            for r in range(RIPETIZIONI):
                if _interrupted:
                    break
                r1x2, scores = run_cicli(algo_id, preloaded, home, away, cycles)
                prob = calcola_prob(r1x2)
                score_top = risultato_esatto(scores)
                top4 = top4_risultati(scores)
                reps.append(prob)
                dets.append((prob, score_top, top4, scores))
                done += 1

            elapsed = time.time() - t0
            remaining = (time.time() - t_start) / done * (total_tests - done) if done > 0 else 0
            print(f"✅ {elapsed:.1f}s (ETA: {remaining:.0f}s)")

            results[algo_id][cycles] = reps
            details[algo_id][cycles] = dets

    return results, details


def salva_dettagli_txt(details, home, away, match_label):
    """Salva file .txt con tutti i singoli risultati di ogni ripetizione."""
    os.makedirs(os.path.join(current_dir, 'benchmark_output'), exist_ok=True)
    fname = f"dettagli_{match_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    fpath = os.path.join(current_dir, 'benchmark_output', fname)

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(f"{'=' * 95}\n")
        f.write(f"  BENCHMARK DETTAGLIATO — {home} vs {away}\n")
        f.write(f"  Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  Livelli cicli: {CYCLE_LEVELS}\n")
        f.write(f"  Ripetizioni: {RIPETIZIONI}\n")
        f.write(f"{'=' * 95}\n\n")

        for algo_id, algo_name in ALGO_IDS.items():
            f.write(f"{'═' * 95}\n")
            f.write(f"  ALGORITMO {algo_id}: {algo_name}\n")
            f.write(f"{'═' * 95}\n\n")

            for cycles in CYCLE_LEVELS:
                f.write(f"  ┌─ {cycles:,} cicli {'─' * 90}\n")
                f.write(f"  │ {'#':>4}  {'Prob 1':>8}  {'Prob X':>8}  {'Prob 2':>8}  {'RE':>6}  {'Top 4 Risultati Esatti'}\n")
                f.write(f"  │ {'─' * 4}  {'─' * 8}  {'─' * 8}  {'─' * 8}  {'─' * 6}  {'─' * 40}\n")

                dets = details[algo_id][cycles]
                all_scores = []
                for i, (prob, score, top4, scores_raw) in enumerate(dets, 1):
                    top4_str = "  ".join(f"{s}({p:.0f}%)" for s, p in top4)
                    f.write(f"  │ {i:>4}  {prob['1']:>7.1f}%  {prob['X']:>7.1f}%  {prob['2']:>7.1f}%  {score:>6}  {top4_str}\n")
                    all_scores.extend(scores_raw)

                # Riga riepilogativa probabilità
                probs_1 = [d[0]['1'] for d in dets]
                probs_x = [d[0]['X'] for d in dets]
                probs_2 = [d[0]['2'] for d in dets]
                f.write(f"  │ {'─' * 4}  {'─' * 8}  {'─' * 8}  {'─' * 8}  {'─' * 6}  {'─' * 40}\n")
                f.write(f"  │ {'AVG':>4}  {np.mean(probs_1):>7.1f}%  {np.mean(probs_x):>7.1f}%  {np.mean(probs_2):>7.1f}%\n")
                f.write(f"  │ {'σ':>4}  {np.std(probs_1):>7.2f}   {np.std(probs_x):>7.2f}   {np.std(probs_2):>7.2f}\n")

                # Statistiche gol aggregate su tutte le ripetizioni
                st = calcola_stats_gol(all_scores)
                if st:
                    f.write(f"  │\n")
                    f.write(f"  │  📊 STATISTICHE GOL (aggregate su {len(all_scores)} simulazioni)\n")
                    f.write(f"  │  ├─ Media gol casa: {st['avg_gol_casa']:.2f}    Media gol ospite: {st['avg_gol_ospite']:.2f}    Media totale: {st['avg_gol_totali']:.2f}\n")
                    f.write(f"  │  ├─ Max gol casa: {st['max_gol_casa']}           Max gol ospite: {st['max_gol_ospite']}\n")
                    f.write(f"  │  ├─ Over 1.5: {st['over_1_5']:.1f}%    Under 1.5: {st['under_1_5']:.1f}%\n")
                    f.write(f"  │  ├─ Over 2.5: {st['over_2_5']:.1f}%    Under 2.5: {st['under_2_5']:.1f}%\n")
                    f.write(f"  │  ├─ Over 3.5: {st['over_3_5']:.1f}%    Under 3.5: {st['under_3_5']:.1f}%\n")
                    f.write(f"  │  ├─ GG: {st['gg']:.1f}%          NG: {st['ng']:.1f}%\n")
                    re_score, re_count = st['re_top']
                    re_pct = re_count / len(all_scores) * 100
                    f.write(f"  │  └─ RE più frequente: {re_score} ({re_pct:.1f}% — {re_count}/{len(all_scores)} volte)\n")

                f.write(f"  └{'─' * 100}\n\n")

            f.write("\n")

    print(f"\n📄 Dettagli salvati: {fpath}")
    return fpath


def stampa_tabella(results, home, away):
    """Stampa tabella riepilogativa per ogni algoritmo."""
    for algo_id, algo_name in ALGO_IDS.items():
        print(f"\n{'=' * 90}")
        print(f"📊 ALGORITMO {algo_id}: {algo_name}  —  {home} vs {away}")
        print(f"{'=' * 90}")
        print(f"{'Cicli':>8} │ {'Prob 1':>8} {'±σ':>6} {'[min-max]':>13} │ {'Prob X':>8} {'±σ':>6} {'[min-max]':>13} │ {'Prob 2':>8} {'±σ':>6} {'[min-max]':>13}")
        print(f"{'─' * 8}─┼─{'─' * 30}─┼─{'─' * 30}─┼─{'─' * 30}")

        for cycles in CYCLE_LEVELS:
            reps = results[algo_id][cycles]
            row = f"{cycles:>8,} │"
            for sign in ['1', 'X', '2']:
                vals = [r[sign] for r in reps]
                avg = np.mean(vals)
                std = np.std(vals)
                mn, mx = np.min(vals), np.max(vals)
                row += f" {avg:>7.1f}% {std:>5.1f} [{mn:>5.1f}-{mx:>5.1f}] │"
            print(row)


def genera_grafico_convergenza(results, details, home, away, match_label):
    """Genera grafico convergenza: 1X2 + statistiche gol."""
    import matplotlib.pyplot as plt

    config_str = f"Cicli: {CYCLE_LEVELS}  |  Ripetizioni: {RIPETIZIONI}  |  Algoritmi: {', '.join(f'{k}-{v}' for k, v in ALGO_IDS.items())}"

    # --- GRAFICO 1: Convergenza 1X2 (deviazione standard) ---
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    signs = ['1', 'X', '2']
    sign_labels = ['Prob 1 (Casa)', 'Prob X (Pareggio)', 'Prob 2 (Ospite)']

    for idx, (sign, label) in enumerate(zip(signs, sign_labels)):
        ax = axes[idx]
        for algo_id, algo_name in ALGO_IDS.items():
            stds = []
            for cycles in CYCLE_LEVELS:
                vals = [r[sign] for r in results[algo_id][cycles]]
                stds.append(np.std(vals))
            ax.plot(CYCLE_LEVELS, stds, 'o-', color=ALGO_COLORS[algo_id],
                    label=f"{algo_id}-{algo_name}", linewidth=2, markersize=5)
        ax.set_xlabel('Cicli Monte Carlo')
        ax.set_ylabel('Deviazione Standard (%)')
        ax.set_title(label)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.suptitle(f"Convergenza 1X2 — {home} vs {away}", fontsize=14, fontweight='bold', y=1.02)
    fig.text(0.5, 0.98, config_str, ha='center', fontsize=8, color='gray')
    plt.tight_layout()

    os.makedirs(os.path.join(current_dir, 'benchmark_output'), exist_ok=True)
    fname = f"convergenza_1x2_{match_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    fpath = os.path.join(current_dir, 'benchmark_output', fname)
    plt.savefig(fpath, dpi=150, bbox_inches='tight')
    print(f"\n📈 Grafico 1X2 salvato: {fpath}")
    plt.close()

    # --- GRAFICO 2: Convergenza GOL ---
    fig2, axes2 = plt.subplots(2, 3, figsize=(20, 12))
    gol_metrics = [
        ('avg_gol_casa', 'Media Gol Casa'),
        ('avg_gol_ospite', 'Media Gol Ospite'),
        ('avg_gol_totali', 'Media Gol Totali'),
        ('over_2_5', 'Over 2.5 %'),
        ('gg', 'GG %'),
        ('over_3_5', 'Over 3.5 %'),
    ]

    for idx, (metric_key, metric_label) in enumerate(gol_metrics):
        ax = axes2.flatten()[idx]
        for algo_id, algo_name in ALGO_IDS.items():
            vals_per_cycle = []
            for cycles in CYCLE_LEVELS:
                # Calcola la metrica per ogni ripetizione, poi media e std
                rep_vals = []
                for (prob, score, top4, scores_raw) in details[algo_id][cycles]:
                    st = calcola_stats_gol(scores_raw)
                    if st:
                        rep_vals.append(st[metric_key])
                vals_per_cycle.append((np.mean(rep_vals) if rep_vals else 0, np.std(rep_vals) if rep_vals else 0))

            means = [v[0] for v in vals_per_cycle]
            stds = [v[1] for v in vals_per_cycle]
            ax.errorbar(CYCLE_LEVELS, means, yerr=stds, fmt='o-', color=ALGO_COLORS[algo_id],
                        label=f"{algo_id}-{algo_name}", linewidth=2, markersize=4, capsize=3)

        ax.set_xlabel('Cicli Monte Carlo')
        ax.set_ylabel(metric_label)
        ax.set_title(metric_label)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    fig2.suptitle(f"Convergenza Gol — {home} vs {away}", fontsize=14, fontweight='bold', y=1.02)
    fig2.text(0.5, 0.98, config_str, ha='center', fontsize=8, color='gray')
    plt.tight_layout()

    fname2 = f"convergenza_gol_{match_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    fpath2 = os.path.join(current_dir, 'benchmark_output', fname2)
    plt.savefig(fpath2, dpi=150, bbox_inches='tight')
    print(f"📈 Grafico GOL salvato: {fpath2}")
    plt.close()

    return fpath, fpath2


def genera_grafico_comparativo(all_results, all_labels):
    """Grafico finale comparativo: tutte le partite sovrapposte, divise per algoritmo."""
    import matplotlib.pyplot as plt

    if len(all_results) < 2:
        print("ℹ️  Serve almeno 2 partite per il grafico comparativo.")
        return

    n_algos = len(ALGO_IDS)
    fig, axes = plt.subplots(2, 3, figsize=(20, 12))
    axes = axes.flatten()

    # Stili linea per distinguere le partite
    line_styles = ['-', '--', '-.', ':', '-', '--', '-.', ':']
    markers = ['o', 's', '^', 'D', 'v', 'P', 'X', '*']

    for algo_idx, (algo_id, algo_name) in enumerate(ALGO_IDS.items()):
        ax = axes[algo_idx]

        for match_idx, (results, label) in enumerate(zip(all_results, all_labels)):
            # Deviazione standard media su 1X2
            avg_stds = []
            for cycles in CYCLE_LEVELS:
                std_per_sign = []
                for sign in ['1', 'X', '2']:
                    vals = [r[sign] for r in results[algo_id][cycles]]
                    std_per_sign.append(np.std(vals))
                avg_stds.append(np.mean(std_per_sign))

            ls = line_styles[match_idx % len(line_styles)]
            mk = markers[match_idx % len(markers)]
            ax.plot(CYCLE_LEVELS, avg_stds, f'{mk}{ls}', label=label, linewidth=2, markersize=5)

        ax.set_xscale('log')
        ax.set_xlabel('Cicli')
        ax.set_ylabel('σ media 1X2 (%)')
        ax.set_title(f"{algo_id}-{algo_name}")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    fig.suptitle("🏆 CONFRONTO CONVERGENZA — Tutte le partite per algoritmo", fontsize=14, fontweight='bold')
    plt.tight_layout()

    os.makedirs(os.path.join(current_dir, 'benchmark_output'), exist_ok=True)
    fname = f"comparativo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    fpath = os.path.join(current_dir, 'benchmark_output', fname)
    plt.savefig(fpath, dpi=150, bbox_inches='tight')
    print(f"\n🏆 Grafico comparativo salvato: {fpath}")
    plt.close()


# ═══════════════════════════════════════════════════
#                    MAIN
# ═══════════════════════════════════════════════════
def chiedi_configurazione():
    """Chiede livelli cicli e ripetizioni, con default se si preme invio."""
    global CYCLE_LEVELS, RIPETIZIONI

    print(f"\n{'=' * 60}")
    print("⚙️  CONFIGURAZIONE BENCHMARK")
    print("=" * 60)

    # Livelli cicli
    default_cycles = ", ".join(str(c) for c in CYCLE_LEVELS)
    print(f"\n   Default livelli cicli: [{default_cycles}]")
    inp = input("   Livelli cicli (separati da virgola, INVIO per default): ").strip()
    if inp:
        try:
            CYCLE_LEVELS = sorted([int(x.strip()) for x in inp.split(',') if x.strip()])
            if not CYCLE_LEVELS:
                raise ValueError
        except ValueError:
            print("   ⚠️  Input non valido, uso default.")

    # Ripetizioni
    print(f"\n   Default ripetizioni per livello: {RIPETIZIONI}")
    inp = input(f"   Ripetizioni (INVIO per {RIPETIZIONI}): ").strip()
    if inp:
        try:
            val = int(inp)
            if val < 1:
                raise ValueError
            RIPETIZIONI = val
        except ValueError:
            print("   ⚠️  Input non valido, uso default 20.")
            RIPETIZIONI = 20

    # Algoritmi
    print(f"\n   Algoritmi disponibili:")
    for k, v in ALGO_IDS.items():
        print(f"     {k} = {v}")
    print(f"   Default: tutti ({', '.join(str(k) for k in ALGO_IDS)})")
    inp = input("   Algoritmi da testare (es. 1,5,6 — INVIO per tutti): ").strip()
    if inp:
        try:
            selected = [int(x.strip()) for x in inp.split(',') if x.strip()]
            invalid = [s for s in selected if s not in ALGO_IDS]
            if invalid:
                print(f"   ⚠️  Algoritmi non validi: {invalid}, uso tutti.")
            else:
                # Rimuovi quelli non selezionati
                for k in list(ALGO_IDS.keys()):
                    if k not in selected:
                        del ALGO_IDS[k]
        except ValueError:
            print("   ⚠️  Input non valido, uso tutti.")

    print(f"\n   ✅ Cicli: {CYCLE_LEVELS}")
    print(f"   ✅ Ripetizioni: {RIPETIZIONI}")
    print(f"   ✅ Algoritmi: {', '.join(f'{k}-{v}' for k, v in ALGO_IDS.items())}")


def main():
    print("\n" + "🎯" * 30)
    print("   BENCHMARK CONVERGENZA MONTE CARLO")
    print("🎯" * 30)

    chiedi_configurazione()

    print(f"\n   Livelli cicli: {CYCLE_LEVELS}")
    print(f"   Ripetizioni per livello: {RIPETIZIONI}")
    print(f"   Algoritmi: {', '.join(f'{k}-{v}' for k, v in ALGO_IDS.items())}")
    print(f"   Test totali per partita: {len(ALGO_IDS) * len(CYCLE_LEVELS) * RIPETIZIONI:,}")

    all_results = []
    all_labels = []

    while True:
        # 1. Scegli campionato
        league = scegli_campionato()
        print(f"\n✅ Campionato: {league}")

        # 2. Scegli giornata
        round_doc = scegli_giornata(league)
        if not round_doc:
            continue

        # 3. Scegli partita
        match = scegli_partita(round_doc)
        if not match:
            continue

        home = match['home']
        away = match['away']
        match_label = f"{home}_vs_{away}".replace(" ", "_")
        print(f"\n🏟️  Partita selezionata: {home} vs {away}")

        # 4. Preload dati
        print("\n📦 Caricamento dati dal DB...", end=" ", flush=True)
        t0 = time.time()
        try:
            preloaded = preload_match_data(home, away)
            print(f"✅ ({time.time() - t0:.1f}s)")
        except Exception as e:
            print(f"\n❌ Errore preload: {e}")
            continue

        # 5. Benchmark
        print(f"\n🚀 AVVIO BENCHMARK — {home} vs {away}")
        print(f"   Stima durata: dipende dalla macchina, ~5-15 minuti")
        t_bench = time.time()

        results, details = benchmark_partita(home, away, preloaded)

        elapsed_total = time.time() - t_bench
        print(f"\n⏱️  BENCHMARK COMPLETATO in {elapsed_total:.0f}s ({elapsed_total/60:.1f} minuti)")

        # 6. Tabella
        stampa_tabella(results, home, away)

        # 7. File dettagli .txt
        salva_dettagli_txt(details, home, away, match_label)

        # 8. Grafico singola partita
        genera_grafico_convergenza(results, details, home, away, match_label)

        # Salva per comparativo
        all_results.append(results)
        all_labels.append(f"{home} vs {away}")

        # 8. Altra partita?
        print(f"\n{'=' * 60}")
        risposta = input("🔄 Vuoi analizzare un'altra partita? [S/n]: ").strip().upper()
        if risposta not in ['', 'S', 'Y', 'SI', 'YES']:
            break

    # 9. Grafico comparativo finale
    if len(all_results) >= 2:
        genera_grafico_comparativo(all_results, all_labels)

    print("\n✅ Benchmark terminato. Arrivederci! 👋\n")


if __name__ == "__main__":
    import signal
    def _handle_interrupt(*_):
        global _interrupted
        _interrupted = True
        print("\n\n👋 Ctrl+C ricevuto — interrompo dopo il ciclo corrente...")
    signal.signal(signal.SIGINT, _handle_interrupt)
    main()
