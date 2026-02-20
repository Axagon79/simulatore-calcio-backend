"""
ANALISI DEL MATCH — Generatore Free
=====================================
Analizza i documenti unified per trovare contraddizioni tra algoritmi.
Genera testo in italiano, tono da analista professionista.
22 checker con severity DINAMICA — ogni contraddizione ha gravita
proporzionale all'entita del disaccordo tra i sistemi.

Uso standalone:
  python generate_match_analysis.py                    # oggi
  python generate_match_analysis.py 2026-02-20         # data specifica
  python generate_match_analysis.py --dry-run           # senza scrivere
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import db


# =====================================================
# HELPERS
# =====================================================

def _clamp(val, lo, hi):
    """Limita val tra lo e hi."""
    return max(lo, min(hi, val))


def _has_over(pronostici):
    return any(p.get('tipo') == 'GOL' and 'Over' in p.get('pronostico', '') for p in pronostici)


def _has_under(pronostici):
    return any(p.get('tipo') == 'GOL' and 'Under' in p.get('pronostico', '') for p in pronostici)


def _has_goal(pronostici):
    return any(p.get('tipo') == 'GOL' and p.get('pronostico') == 'Goal' for p in pronostici)


def _has_nogoal(pronostici):
    return any(p.get('tipo') == 'GOL' and p.get('pronostico') == 'NoGoal' for p in pronostici)


def _has_segno(pronostici):
    return any(p.get('tipo') == 'SEGNO' for p in pronostici)


def _get_segno_pred(pronostici):
    return next((p for p in pronostici if p.get('tipo') == 'SEGNO'), None)


def _get_over_pred(pronostici):
    return next((p for p in pronostici if p.get('tipo') == 'GOL' and 'Over' in p.get('pronostico', '')), None)


def _get_under_pred(pronostici):
    return next((p for p in pronostici if p.get('tipo') == 'GOL' and 'Under' in p.get('pronostico', '')), None)


# =====================================================
# CATEGORIA 1: CONTRADDIZIONI INTERNE PRONOSTICI (1-2)
# =====================================================

def check_over_nogoal(doc):
    """1. Over X.5 + NoGoal nella stessa partita.
    Severity: 75-95 — scala con la confidence media dei due pronostici contraddittori.
    Over 2.5 con conf 80 + NoGoal conf 75 → severity ~88
    Over 2.5 con conf 55 + NoGoal conf 55 → severity ~75
    """
    pronostici = doc.get('pronostici', [])
    if not (_has_over(pronostici) and _has_nogoal(pronostici)):
        return None

    over_p = _get_over_pred(pronostici)
    nogoal_p = next((p for p in pronostici if p.get('pronostico') == 'NoGoal'), None)
    conf_over = over_p.get('confidence', 60) if over_p else 60
    conf_ng = nogoal_p.get('confidence', 60) if nogoal_p else 60
    avg_conf = (conf_over + conf_ng) / 2
    # Piu entrambi sono convinti, piu e grave la contraddizione
    severity = _clamp(int(55 + avg_conf * 0.45), 6, 95)

    return {
        'id': 'over_nogoal',
        'severity': severity,
        'text': f"I nostri sistemi suggeriscono contemporaneamente {over_p['pronostico']} e NoGoal: "
                f"una contraddizione diretta. L'analisi dei gol prevede molte reti, "
                f"ma il modello difensivo indica il contrario."
    }


def check_under_goal(doc):
    """2. Under X.5 + Goal nella stessa partita.
    Severity: 70-90 — scala con confidence media.
    """
    pronostici = doc.get('pronostici', [])
    if not (_has_under(pronostici) and _has_goal(pronostici)):
        return None

    under_p = _get_under_pred(pronostici)
    goal_p = next((p for p in pronostici if p.get('pronostico') == 'Goal'), None)
    conf_under = under_p.get('confidence', 60) if under_p else 60
    conf_goal = goal_p.get('confidence', 60) if goal_p else 60
    avg_conf = (conf_under + conf_goal) / 2
    severity = _clamp(int(50 + avg_conf * 0.45), 6, 90)

    return {
        'id': 'under_goal',
        'severity': severity,
        'text': f"Segnali contrastanti: il pronostico indica {under_p['pronostico']} ma anche Goal. "
                f"L'analisi difensiva suggerisce pochi gol, mentre le tendenze offensive puntano "
                f"verso entrambe le squadre a segno."
    }


# =====================================================
# CATEGORIA 2: MONTE CARLO VS PRONOSTICI (3-7)
# =====================================================

def check_mc_vs_gol(doc):
    """3. MC Over/Under% vs pronostico GOL.
    Severity: 55-90 — scala con distanza della % dal 50%.
    MC 84% Under + Over emesso → severity ~84
    MC 62% Under + Over emesso → severity ~62
    """
    pronostici = doc.get('pronostici', [])
    sim = doc.get('simulation_data')
    if not sim:
        return None

    over_25_pct = sim.get('over_25_pct', 50)
    under_25_pct = sim.get('under_25_pct', 50)

    if any(p.get('pronostico') == 'Over 2.5' for p in pronostici if p.get('tipo') == 'GOL'):
        if under_25_pct > 55:
            severity = _clamp(int(under_25_pct), 6, 90)
            return {
                'id': 'mc_vs_over',
                'severity': severity,
                'text': f"Il modello di simulazione indica una probabilita del {under_25_pct:.0f}% "
                        f"che si verifichino meno di 3 gol, in contrasto con il pronostico Over 2.5. "
                        f"I due sistemi non concordano: valutare il rischio di questa scommessa."
            }

    if any(p.get('pronostico') == 'Under 2.5' for p in pronostici if p.get('tipo') == 'GOL'):
        if over_25_pct > 55:
            severity = _clamp(int(over_25_pct), 6, 90)
            return {
                'id': 'mc_vs_under',
                'severity': severity,
                'text': f"Il modello di simulazione indica una probabilita del {over_25_pct:.0f}% "
                        f"di almeno 3 gol, in contrasto con il pronostico Under 2.5. "
                        f"I due sistemi non concordano: valutare il rischio di questa scommessa."
            }

    return None


def check_mc_vs_segno(doc):
    """4. MC home/away% vs pronostico SEGNO.
    Severity: 45-85 — piu bassa la % MC per il pronostico, piu grave.
    Pronostico 1 con MC 30% casa → severity ~80
    Pronostico 1 con MC 42% casa → severity ~58
    """
    sim = doc.get('simulation_data')
    if not sim:
        return None

    segno_pred = _get_segno_pred(doc.get('pronostici', []))
    if not segno_pred:
        return None

    pron = segno_pred.get('pronostico', '')
    home_pct = sim.get('home_win_pct', 33)
    draw_pct = sim.get('draw_pct', 33)
    away_pct = sim.get('away_win_pct', 33)

    if pron == '1' and home_pct < 45 and (away_pct > 30 or draw_pct > 30):
        # 20% → sev 85, 30% → sev 72, 40% → sev 58, 44% → sev 52
        severity = _clamp(int(110 - home_pct * 1.5), 6, 85)
        return {
            'id': 'mc_vs_segno_home',
            'severity': severity,
            'text': f"Il pronostico indica vittoria casalinga, ma le simulazioni assegnano solo "
                    f"il {home_pct:.0f}% di probabilita a questo esito. "
                    f"C'e disaccordo tra i sistemi: il pronostico e le simulazioni puntano in direzioni diverse."
        }

    if pron == '2' and away_pct < 45 and (home_pct > 30 or draw_pct > 30):
        severity = _clamp(int(110 - away_pct * 1.5), 6, 85)
        return {
            'id': 'mc_vs_segno_away',
            'severity': severity,
            'text': f"Il pronostico indica vittoria ospite, ma le simulazioni assegnano solo "
                    f"il {away_pct:.0f}% di probabilita a questo esito. "
                    f"C'e disaccordo tra i sistemi: il pronostico e le simulazioni puntano in direzioni diverse."
        }

    return None


def check_mc_ggng(doc):
    """5. MC GG/NG% vs pronostico GG/NG.
    Severity: 50-85 — scala con distanza dal 50%.
    MC ng 80% + Goal → severity ~80
    MC ng 62% + Goal → severity ~62
    """
    sim = doc.get('simulation_data')
    if not sim:
        return None

    pronostici = doc.get('pronostici', [])
    gg_pct = sim.get('gg_pct', 50)
    ng_pct = sim.get('ng_pct', 50)

    if _has_goal(pronostici) and ng_pct > 55:
        severity = _clamp(int(ng_pct), 6, 85)
        return {
            'id': 'mc_vs_goal',
            'severity': severity,
            'text': f"Le simulazioni indicano una probabilita del {ng_pct:.0f}% che almeno una "
                    f"squadra non segni, in contrasto con il pronostico Goal. "
                    f"I due approcci danno indicazioni opposte su questo mercato."
        }

    if _has_nogoal(pronostici) and gg_pct > 55:
        severity = _clamp(int(gg_pct), 6, 85)
        return {
            'id': 'mc_vs_nogoal',
            'severity': severity,
            'text': f"Le simulazioni indicano una probabilita del {gg_pct:.0f}% che entrambe "
                    f"le squadre segnino, in contrasto con il pronostico NoGoal. "
                    f"I due approcci danno indicazioni opposte su questo mercato."
        }

    return None


def check_mc_draw_vs_segno(doc):
    """6. MC draw% alto + SEGNO 1 o 2 emesso.
    Severity: 45-75 — scala con draw%.
    Draw 50% → severity ~70, Draw 39% → severity ~49
    """
    sim = doc.get('simulation_data')
    if not sim:
        return None

    segno_pred = _get_segno_pred(doc.get('pronostici', []))
    if not segno_pred:
        return None

    draw_pct = sim.get('draw_pct', 33)
    pron = segno_pred.get('pronostico', '')

    if draw_pct > 35 and pron in ('1', '2'):
        # 36% → sev 46, 40% → sev 54, 45% → sev 64, 50% → sev 74
        severity = _clamp(int(draw_pct * 2 - 26), 6, 75)
        esito = 'vittoria casalinga' if pron == '1' else 'vittoria ospite'
        return {
            'id': 'mc_draw_high',
            'severity': severity,
            'text': f"Le simulazioni assegnano un {draw_pct:.0f}% di probabilita al pareggio, "
                    f"un valore significativo che contrasta con il pronostico di {esito}. "
                    f"Pronostico e simulazioni non sono allineati sul risultato finale."
        }

    return None


def check_mc_topscores_vs_over(doc):
    """7. MC top scores tutti low-scoring + Over 2.5 emesso.
    Severity: 60-80 — scala con quanti top score sono low-scoring.
    Top 3 tutti <3 gol → severity ~78. Top 2 su 3 → severity ~65.
    """
    sim = doc.get('simulation_data')
    if not sim:
        return None

    pronostici = doc.get('pronostici', [])
    if not any(p.get('pronostico') == 'Over 2.5' for p in pronostici if p.get('tipo') == 'GOL'):
        return None

    top_scores = sim.get('top_scores', [])
    if not top_scores or len(top_scores) < 2:
        return None

    def _get_score_str(ts):
        """Estrae la stringa score sia da tuple [score, count] che da dict {score, pct}."""
        if isinstance(ts, (list, tuple)):
            return str(ts[0]) if ts else '0-0'
        if isinstance(ts, dict):
            return ts.get('score', '0-0')
        return str(ts)

    low_count = 0
    for ts in top_scores[:3]:
        score_str = _get_score_str(ts)
        try:
            parts = score_str.split('-')
            total_goals = int(parts[0]) + int(parts[1])
            if total_goals < 3:
                low_count += 1
        except (ValueError, IndexError):
            pass

    if low_count >= 2:
        # 2 su 3 → sev 65, 3 su 3 → sev 78
        severity = _clamp(50 + low_count * 10, 6, 80)
        scores_text = ', '.join(_get_score_str(ts) for ts in top_scores[:3])
        return {
            'id': 'mc_topscores_vs_over',
            'severity': severity,
            'text': f"I risultati piu probabili secondo le simulazioni sono {scores_text}, "
                    f"quasi tutti con meno di 3 gol. Questo contrasta con il pronostico Over 2.5: "
                    f"simulazioni e pronostico non concordano sul numero di gol atteso."
        }

    return None


# =====================================================
# CATEGORIA 3: QUOTE MERCATO VS PRONOSTICI (8-12)
# =====================================================

def check_quota_gg_vs_nogoal(doc):
    """8. Quota GG bassa (mercato dice Goal) + NoGoal emesso.
    Severity: 50-80 — piu bassa la quota, piu il mercato e convinto → piu grave.
    Quota GG 1.25 → severity ~78. Quota GG 1.50 → severity ~58.
    """
    odds = doc.get('odds', {})
    pronostici = doc.get('pronostici', [])
    quota_gg = odds.get('gg')

    if not quota_gg or not isinstance(quota_gg, (int, float)):
        return None

    if _has_nogoal(pronostici) and quota_gg < 1.60:
        # 1.20 → sev 80, 1.35 → sev 68, 1.50 → sev 56, 1.58 → sev 50
        severity = _clamp(int(120 - quota_gg * 50), 6, 80)
        return {
            'id': 'quota_gg_vs_nogoal',
            'severity': severity,
            'text': f"Il mercato delle quote offre Goal a {quota_gg:.2f}, un valore basso che indica "
                    f"forte aspettativa di entrambe le squadre a segno. Il nostro pronostico NoGoal "
                    f"va controcorrente rispetto al mercato."
        }

    return None


def check_quota_ng_vs_goal(doc):
    """9. Quota NG bassa (mercato dice NoGoal) + Goal emesso.
    Severity: 50-80 — come sopra, inversione.
    """
    odds = doc.get('odds', {})
    pronostici = doc.get('pronostici', [])
    quota_ng = odds.get('ng')

    if not quota_ng or not isinstance(quota_ng, (int, float)):
        return None

    if _has_goal(pronostici) and quota_ng < 1.60:
        severity = _clamp(int(120 - quota_ng * 50), 6, 80)
        return {
            'id': 'quota_ng_vs_goal',
            'severity': severity,
            'text': f"Il mercato delle quote offre NoGoal a {quota_ng:.2f}, suggerendo che "
                    f"almeno una squadra potrebbe non segnare. Il nostro pronostico Goal "
                    f"contrasta con l'opinione del mercato."
        }

    return None


def check_quota_over_vs_under(doc):
    """10. Quota Over bassa + Under emesso, o viceversa.
    Severity: 50-75 — scala con quanto bassa e la quota contraria.
    """
    odds = doc.get('odds', {})
    pronostici = doc.get('pronostici', [])

    quota_over25 = odds.get('over_25')
    quota_under25 = odds.get('under_25')

    if quota_over25 and isinstance(quota_over25, (int, float)):
        if _has_under(pronostici) and quota_over25 < 1.60:
            under_p = _get_under_pred(pronostici)
            if under_p and 'Under 2.5' in under_p.get('pronostico', ''):
                severity = _clamp(int(110 - quota_over25 * 45), 6, 75)
                return {
                    'id': 'quota_over_vs_under',
                    'severity': severity,
                    'text': f"Le quote di mercato offrono Over 2.5 a {quota_over25:.2f}, indicando "
                            f"aspettativa di almeno 3 gol. Il nostro pronostico Under 2.5 "
                            f"si oppone alla tendenza del mercato."
                }

    if quota_under25 and isinstance(quota_under25, (int, float)):
        if _has_over(pronostici) and quota_under25 < 1.60:
            over_p = _get_over_pred(pronostici)
            if over_p and 'Over 2.5' in over_p.get('pronostico', ''):
                severity = _clamp(int(110 - quota_under25 * 45), 6, 75)
                return {
                    'id': 'quota_under_vs_over',
                    'severity': severity,
                    'text': f"Le quote di mercato offrono Under 2.5 a {quota_under25:.2f}, indicando "
                            f"aspettativa di meno di 3 gol. Il nostro pronostico Over 2.5 "
                            f"si oppone alla tendenza del mercato."
                }

    return None


def check_quota_segno_divergente(doc):
    """11. Quota favorita molto bassa ma pronostico diverge.
    Severity: 50-80 — piu bassa la quota del favorito, piu grave andare contro.
    Quota 1.15 + pronostico X → severity ~78. Quota 1.40 → severity ~55.
    """
    odds = doc.get('odds', {})
    pronostici = doc.get('pronostici', [])
    segno_pred = _get_segno_pred(pronostici)
    if not segno_pred:
        return None

    pron = segno_pred.get('pronostico', '')
    quota_1 = odds.get('1')
    quota_2 = odds.get('2')

    if not quota_1 or not quota_2:
        return None

    if isinstance(quota_1, (int, float)) and quota_1 < 1.50 and pron in ('X', '2'):
        # 1.10 → sev 79, 1.25 → sev 69, 1.40 → sev 59, 1.48 → sev 53
        severity = _clamp(int(92 - quota_1 * 30), 6, 80)
        return {
            'id': 'quota_segno_home_fav',
            'severity': severity,
            'text': f"La squadra di casa e nettamente favorita con quota {quota_1:.2f}, "
                    f"ma il nostro pronostico indica {'pareggio' if pron == 'X' else 'vittoria ospite'}. "
                    f"Andare contro un favorito cosi netto comporta un rischio aggiuntivo."
        }

    if isinstance(quota_2, (int, float)) and quota_2 < 1.50 and pron in ('X', '1'):
        severity = _clamp(int(92 - quota_2 * 30), 6, 80)
        return {
            'id': 'quota_segno_away_fav',
            'severity': severity,
            'text': f"La squadra ospite e nettamente favorita con quota {quota_2:.2f}, "
                    f"ma il nostro pronostico indica {'pareggio' if pron == 'X' else 'vittoria casalinga'}. "
                    f"Andare contro un favorito cosi netto comporta un rischio aggiuntivo."
        }

    return None


def check_quota_bassa_confidence_bassa(doc):
    """12. Quota favorita < 1.40 ma confidence bassa < 55.
    Severity: 40-65 — scala con quanto bassa e la confidence.
    Conf 30 → severity ~62. Conf 50 → severity ~45.
    """
    odds = doc.get('odds', {})
    confidence = doc.get('confidence_segno')

    if confidence is None or confidence >= 55:
        return None

    segno_pred = _get_segno_pred(doc.get('pronostici', []))
    if not segno_pred:
        return None

    pron = segno_pred.get('pronostico', '')
    quota_fav = None
    if pron == '1':
        quota_fav = odds.get('1')
    elif pron == '2':
        quota_fav = odds.get('2')

    if quota_fav and isinstance(quota_fav, (int, float)) and quota_fav < 1.40:
        # Conf 30 → sev 62, Conf 40 → sev 55, Conf 50 → sev 48, Conf 54 → sev 45
        severity = _clamp(int(82 - confidence * 0.7), 6, 65)
        return {
            'id': 'quota_bassa_conf_bassa',
            'severity': severity,
            'text': f"La quota del pronostico e molto bassa ({quota_fav:.2f}), ma il nostro livello "
                    f"di fiducia e solo {confidence:.0f}/100. Il mercato e convinto, "
                    f"ma i nostri algoritmi sono meno sicuri del risultato."
        }

    return None


# =====================================================
# CATEGORIA 4: STRISCE VS PRONOSTICI (13-16)
# =====================================================

def check_strisce_over_vs_over(doc):
    """13. Strisce over25/gg alte + Over/Goal emesso.
    Logica CONTRARIAN: striscia over25 lunga → si interrompe → prossima Under.
    Se il pronostico dice Over, contrasta con la tendenza contrarian.
    Severity: 50-80 — scala con lunghezza striscia.
    """
    pronostici = doc.get('pronostici', [])
    if not _has_over(pronostici):
        return None

    streak_home = doc.get('streak_home') or {}
    streak_away = doc.get('streak_away') or {}

    home_over = streak_home.get('over25', 0)
    away_over = streak_away.get('over25', 0)
    home_gg = streak_home.get('gg', 0)
    away_gg = streak_away.get('gg', 0)

    best_streak = max(home_over, away_over, home_gg, away_gg)

    if best_streak >= 4:
        severity = _clamp(int(43 + best_streak * 6), 6, 80)
        team = 'casa' if max(home_over, home_gg) >= max(away_over, away_gg) else 'ospite'
        return {
            'id': 'strisce_over_vs_over',
            'severity': severity,
            'text': f"La squadra di {team} arriva da {best_streak} partite consecutive ricche di gol. "
                    f"Per statistica, una striscia cosi lunga tende a interrompersi: "
                    f"il pronostico Over potrebbe non essere in linea con questa tendenza."
        }

    return None


def check_strisce_under_vs_under(doc):
    """14. Strisce under25/clean_sheet alte + Under/NoGoal emesso.
    Logica CONTRARIAN: striscia under lunga → si interrompe → prossima Over.
    Se il pronostico dice Under/NoGoal, contrasta con la tendenza contrarian.
    Severity: 50-80 — scala con lunghezza striscia.
    """
    pronostici = doc.get('pronostici', [])
    if not (_has_under(pronostici) or _has_nogoal(pronostici)):
        return None

    streak_home = doc.get('streak_home') or {}
    streak_away = doc.get('streak_away') or {}

    home_under = streak_home.get('under25', 0)
    away_under = streak_away.get('under25', 0)
    home_cs = streak_home.get('clean_sheet', 0)
    away_cs = streak_away.get('clean_sheet', 0)

    best_streak = max(home_under, away_under, home_cs, away_cs)

    if best_streak >= 4:
        severity = _clamp(int(43 + best_streak * 6), 6, 80)
        team = 'casa' if max(home_under, home_cs) >= max(away_under, away_cs) else 'ospite'
        return {
            'id': 'strisce_under_vs_under',
            'severity': severity,
            'text': f"La squadra di {team} arriva da {best_streak} partite consecutive con pochi gol. "
                    f"Per statistica, una striscia cosi lunga tende a interrompersi: "
                    f"il pronostico di pochi gol potrebbe non essere in linea con questa tendenza."
        }

    return None


def check_striscia_senza_segnare_vs_nogoal(doc):
    """15. Striscia senza_segnare alta + NoGoal emesso.
    Logica CONTRARIAN: squadra non segna da N partite → si interrompe → segnera.
    Se il pronostico dice NoGoal, la tendenza contrarian dice il contrario.
    Severity: 55-85 — piu lunga la striscia, piu grave.
    """
    pronostici = doc.get('pronostici', [])
    if not _has_nogoal(pronostici):
        return None

    streak_home = doc.get('streak_home') or {}
    streak_away = doc.get('streak_away') or {}

    home_no_gol = streak_home.get('senza_segnare', 0)
    away_no_gol = streak_away.get('senza_segnare', 0)
    best = max(home_no_gol, away_no_gol)

    if best >= 3:
        severity = _clamp(int(40 + best * 7), 6, 85)
        team = 'casa' if home_no_gol >= away_no_gol else 'ospite'
        return {
            'id': 'striscia_no_gol_vs_nogoal',
            'severity': severity,
            'text': f"La squadra di {team} non segna da {best} partite consecutive. "
                    f"Per statistica, questa striscia tende a interrompersi. Il pronostico NoGoal "
                    f"e in contrasto con la tendenza contrarian che prevede la fine della serie negativa."
        }

    return None


def check_striscia_gol_subiti_vs_over(doc):
    """16. Striscia gol_subiti alta + Over/Goal emesso.
    Logica CONTRARIAN: squadra subisce da N partite → si interrompe → non subira.
    Se il pronostico dice Over/Goal, la tendenza contrarian dice il contrario.
    Severity: 50-80 — scala con lunghezza striscia.
    """
    pronostici = doc.get('pronostici', [])
    if not (_has_over(pronostici) or _has_goal(pronostici)):
        return None

    streak_home = doc.get('streak_home') or {}
    streak_away = doc.get('streak_away') or {}

    home_gs = streak_home.get('gol_subiti', 0)
    away_gs = streak_away.get('gol_subiti', 0)
    best = max(home_gs, away_gs)

    if best >= 4:
        severity = _clamp(int(38 + best * 6), 6, 80)
        team = 'casa' if home_gs >= away_gs else 'ospite'
        return {
            'id': 'striscia_gol_subiti_vs_over',
            'severity': severity,
            'text': f"La squadra di {team} subisce gol da {best} partite consecutive. "
                    f"Per statistica, questa striscia tende a interrompersi. Il pronostico di molti gol "
                    f"e in contrasto con la tendenza contrarian che prevede la fine della serie negativa."
        }

    return None


# =====================================================
# CATEGORIA 5: DETTAGLIO SEGNALI VS PRONOSTICI (17-20)
# =====================================================

def check_gol_directions_discordant(doc):
    """17. Maggioranza gol_directions vs pronostico Over/Under.
    Severity: 50-80 — scala con rapporto indicatori contrari.
    6/7 contrari → sev ~75. 4/6 → sev ~58.
    """
    pronostici = doc.get('pronostici', [])
    gol_directions = doc.get('gol_directions')
    if not gol_directions:
        return None

    over_count = sum(1 for v in gol_directions.values() if v == 'over')
    under_count = sum(1 for v in gol_directions.values() if v == 'under')
    total = len(gol_directions)
    if total == 0:
        return None

    if _has_over(pronostici) and under_count > over_count and under_count >= total * 0.5:
        ratio = under_count / total
        # ratio 0.5 → sev 50, 0.7 → sev 64, 0.85 → sev 75, 1.0 → sev 80
        severity = _clamp(int(ratio * 70 + 15), 6, 80)
        return {
            'id': 'directions_vs_over',
            'severity': severity,
            'text': f"La maggior parte dei nostri indicatori di gol ({under_count} su {total}) "
                    f"punta verso una partita con pochi gol, in contrasto con il pronostico Over. "
                    f"L'analisi statistica consiglia cautela."
        }

    if _has_under(pronostici) and over_count > under_count and over_count >= total * 0.5:
        ratio = over_count / total
        severity = _clamp(int(ratio * 70 + 15), 6, 80)
        return {
            'id': 'directions_vs_under',
            'severity': severity,
            'text': f"La maggior parte dei nostri indicatori di gol ({over_count} su {total}) "
                    f"suggerisce una partita ricca di reti, ma il pronostico indica Under. "
                    f"I segnali sono contrastanti: valutare con attenzione."
        }

    return None


def check_segno_equilibrato(doc):
    """18. Tutti i segnali segno_dettaglio ~50 + SEGNO deciso.
    Severity: 45-65 — scala con % segnali nella zona grigia.
    8/9 nella zona → sev ~65. 6/9 → sev ~52.
    """
    pronostici = doc.get('pronostici', [])
    segno_det = doc.get('segno_dettaglio')
    if not segno_det:
        return None

    segno_pred = _get_segno_pred(pronostici)
    if not segno_pred or segno_pred.get('pronostico') not in ('1', '2'):
        return None

    values = [v for v in segno_det.values() if isinstance(v, (int, float))]
    if not values or len(values) < 4:
        return None

    zona_grigia = sum(1 for v in values if 40 <= v <= 60)
    ratio = zona_grigia / len(values)

    if ratio >= 0.6:
        severity = _clamp(int(ratio * 50 + 20), 6, 65)
        esito = 'vittoria casalinga' if segno_pred['pronostico'] == '1' else 'vittoria ospite'
        return {
            'id': 'segno_equilibrato',
            'severity': severity,
            'text': f"La maggior parte degli indicatori sul risultato finale ({zona_grigia} su {len(values)}) "
                    f"e nella zona di incertezza. Il pronostico indica {esito}, ma i nostri "
                    f"algoritmi mostrano un quadro molto equilibrato tra le due squadre."
        }

    return None


def check_gol_dettaglio_basso_vs_over(doc):
    """19. Gol dettaglio valori bassi + Over.
    Severity: 45-75 — scala con quanto bassi sono i valori medi.
    Media segnali 20 → sev ~73. Media 30 → sev ~60. Media 34 → sev ~53.
    """
    pronostici = doc.get('pronostici', [])
    if not _has_over(pronostici):
        return None

    gol_det = doc.get('gol_dettaglio')
    if not gol_det:
        return None

    values = [v for v in gol_det.values() if isinstance(v, (int, float))]
    if not values:
        return None

    avg = sum(values) / len(values)

    if avg < 35:
        # avg 15 → sev 75, avg 25 → sev 63, avg 34 → sev 52
        severity = _clamp(int(93 - avg * 1.2), 6, 75)
        return {
            'id': 'gol_det_basso_vs_over',
            'severity': severity,
            'text': f"I nostri indicatori di gol hanno un punteggio medio di {avg:.0f}/100, "
                    f"un valore basso che suggerisce una partita con poche reti. "
                    f"Questo contrasta con il pronostico Over emesso."
        }

    return None


def check_bvs_vs_quote_divergenti(doc):
    """20. Segno dettaglio: BVS e Quote puntano in direzioni opposte.
    Severity: 45-70 — scala con ampiezza della divergenza.
    BVS 80 vs Quote 20 → sev ~70. BVS 68 vs Quote 33 → sev ~52.
    """
    segno_det = doc.get('segno_dettaglio')
    if not segno_det:
        return None

    bvs = segno_det.get('bvs')
    quote = segno_det.get('quote')

    if bvs is None or quote is None:
        return None

    divergenza = abs(bvs - quote)

    if bvs > 60 and quote < 40 and divergenza > 25:
        severity = _clamp(int(30 + divergenza * 0.7), 6, 70)
        return {
            'id': 'bvs_vs_quote',
            'severity': severity,
            'text': f"Il valore delle squadre indica un chiaro vantaggio casalingo, "
                    f"ma le quote del mercato suggeriscono il contrario. "
                    f"Questa divergenza tra valore intrinseco e opinione del mercato merita attenzione."
        }

    if bvs < 40 and quote > 60 and divergenza > 25:
        severity = _clamp(int(30 + divergenza * 0.7), 6, 70)
        return {
            'id': 'bvs_vs_quote_inv',
            'severity': severity,
            'text': f"Le quote del mercato favoriscono nettamente la squadra di casa, "
                    f"ma il valore intrinseco delle squadre non lo conferma. "
                    f"Questa divergenza suggerisce cautela nel seguire ciecamente le quote."
        }

    return None


# =====================================================
# CATEGORIA 6: CROSS-CHECK GLOBALI (21-22)
# =====================================================

def check_confidence_bassa_segno(doc):
    """21. Confidence segno bassa + SEGNO emesso.
    Severity: 40-65 — scala con quanto bassa e la confidence.
    Conf 35 → sev ~62. Conf 45 → sev ~55. Conf 54 → sev ~49.
    """
    confidence = doc.get('confidence_segno')
    if confidence is None or confidence >= 55:
        return None

    pronostici = doc.get('pronostici', [])
    if not _has_segno(pronostici):
        return None

    # 30 → sev 65, 40 → sev 58, 50 → sev 51, 54 → sev 48
    severity = _clamp(int(86 - confidence * 0.7), 6, 65)

    return {
        'id': 'low_confidence_segno',
        'severity': severity,
        'text': f"Il pronostico sul risultato finale presenta un livello di affidabilita "
                f"inferiore alla media ({confidence:.0f}/100). "
                f"La partita e incerta e il margine di sicurezza e ridotto."
    }


def check_expected_goals_vs_pronostico(doc):
    """22. Expected goals vs Over/Under.
    Severity: 50-80 — scala con distanza dal threshold 2.5.
    xG 1.2 + Over 2.5 → sev ~76. xG 1.8 + Over 2.5 → sev ~58.
    xG 3.8 + Under 2.5 → sev ~76. xG 3.1 + Under 2.5 → sev ~55.
    """
    etg = doc.get('expected_total_goals')
    if etg is None:
        return None

    pronostici = doc.get('pronostici', [])

    if any(p.get('pronostico') == 'Over 2.5' for p in pronostici if p.get('tipo') == 'GOL'):
        if etg < 2.2:
            # Distanza da 2.5: piu lontano = piu grave
            dist = 2.5 - etg  # 0.3 a 2.5
            severity = _clamp(int(45 + dist * 25), 6, 80)
            return {
                'id': 'xg_vs_over',
                'severity': severity,
                'text': f"I modelli prevedono in media {etg:.1f} gol totali, un valore basso "
                        f"che contrasta con il pronostico Over 2.5. "
                        f"Statistiche e pronostico non sono allineati sul numero di gol atteso."
            }

    if any(p.get('pronostico') == 'Under 2.5' for p in pronostici if p.get('tipo') == 'GOL'):
        if etg > 2.8:
            dist = etg - 2.5
            severity = _clamp(int(45 + dist * 25), 6, 80)
            return {
                'id': 'xg_vs_under',
                'severity': severity,
                'text': f"I modelli prevedono in media {etg:.1f} gol totali, un valore alto "
                        f"che contrasta con il pronostico Under 2.5. "
                        f"Statistiche e pronostico non sono allineati sul numero di gol atteso."
            }

    return None


# =====================================================
# LISTA COMPLETA CHECKER (22 totali)
# =====================================================

ALL_CHECKERS = [
    # Cat. 1: Contraddizioni interne
    check_over_nogoal,
    check_under_goal,
    # Cat. 2: Monte Carlo
    check_mc_vs_gol,
    check_mc_vs_segno,
    check_mc_ggng,
    check_mc_draw_vs_segno,
    check_mc_topscores_vs_over,
    # Cat. 3: Quote mercato
    check_quota_gg_vs_nogoal,
    check_quota_ng_vs_goal,
    check_quota_over_vs_under,
    check_quota_segno_divergente,
    check_quota_bassa_confidence_bassa,
    # Cat. 4: Strisce
    check_strisce_over_vs_over,
    check_strisce_under_vs_under,
    check_striscia_senza_segnare_vs_nogoal,
    check_striscia_gol_subiti_vs_over,
    # Cat. 5: Dettaglio segnali
    check_gol_directions_discordant,
    check_segno_equilibrato,
    check_gol_dettaglio_basso_vs_over,
    check_bvs_vs_quote_divergenti,
    # Cat. 6: Cross-check
    check_confidence_bassa_segno,
    check_expected_goals_vs_pronostico,
]


# =====================================================
# GENERATORE ANALISI
# =====================================================

def _build_positive_analysis(doc):
    """Genera testo positivo quando non ci sono contraddizioni (o pochissime)."""
    home = doc.get('home', '?')
    away = doc.get('away', '?')
    pronostici = doc.get('pronostici', [])
    sim = doc.get('simulation_data', {})

    lines = []
    lines.append(f"Nella partita {home} - {away} i nostri algoritmi mostrano "
                 f"un quadro coerente e concordante.")

    # Commento mercato SEGNO
    segno_p = next((p for p in pronostici if p.get('tipo') == 'SEGNO'), None)
    dc_p = next((p for p in pronostici if p.get('tipo') == 'DOPPIA_CHANCE'), None)
    conf_segno = doc.get('confidence_segno', 0)

    if segno_p:
        label = segno_p.get('pronostico', '?')
        stars = segno_p.get('stars', 0)
        quota = segno_p.get('quota', '')
        q_str = f" a quota {quota}" if quota else ""
        if conf_segno >= 70:
            lines.append(f"▸ Mercato Segno: forte convergenza su {label}{q_str} "
                         f"({stars} stelle, confidence {conf_segno}%). I modelli sono allineati.")
        else:
            lines.append(f"▸ Mercato Segno: indicazione su {label}{q_str} "
                         f"({stars} stelle, confidence {conf_segno}%).")
    elif dc_p:
        label = dc_p.get('pronostico', '?')
        lines.append(f"▸ Mercato Segno: emessa una Doppia Chance {label} — partita equilibrata "
                     f"ma con direzione chiara.")

    # Commento mercato GOL
    gol_pronostici = [p for p in pronostici if p.get('tipo') == 'GOL']
    conf_gol = doc.get('confidence_gol', 0)

    for gp in gol_pronostici[:2]:
        label = gp.get('pronostico', '?')
        stars = gp.get('stars', 0)
        quota = gp.get('quota', '')
        q_str = f" a quota {quota}" if quota else ""

        # Arricchisci con MC se disponibile
        mc_note = ""
        if 'over' in label.lower() and sim.get('over_25_pct'):
            mc_note = f" La simulazione Monte Carlo conferma con {sim['over_25_pct']:.0f}%."
        elif 'under' in label.lower() and sim.get('over_25_pct'):
            under_pct = 100 - sim['over_25_pct']
            mc_note = f" La simulazione Monte Carlo conferma con {under_pct:.0f}%."

        if conf_gol >= 70:
            lines.append(f"▸ Mercato Gol: solida indicazione su {label}{q_str} "
                         f"({stars} stelle).{mc_note}")
        else:
            lines.append(f"▸ Mercato Gol: indicazione su {label}{q_str} "
                         f"({stars} stelle).{mc_note}")

    if not gol_pronostici:
        lines.append("▸ Mercato Gol: nessun pronostico emesso — segnali insufficienti "
                     "per esprimere una direzione chiara.")

    # Chiusura positiva
    lines.append("Tutti i segnali convergono nella stessa direzione: "
                 "un buon indicatore di affidabilità per questa partita.")

    return '\n\n'.join(lines)


def generate_free_analysis(doc):
    """
    Analizza un documento unified e genera analisi per OGNI partita.
    - 0 contraddizioni → testo positivo con commenti per mercato
    - 1+ contraddizioni → testo con alert e commenti critici

    Args:
        doc: documento da daily_predictions_unified

    Returns:
        tuple: (analysis_free: str, analysis_alerts: list[str], analysis_score: int)
    """
    pronostici = doc.get('pronostici', [])
    if not pronostici:
        return ('', [], 100)

    # Esegui tutti i 22 checker — firma unificata: checker(doc)
    alerts = []
    for checker in ALL_CHECKERS:
        try:
            result = checker(doc)
            if result:
                alerts.append(result)
        except Exception as e:
            print(f"  [WARN] Checker {checker.__name__} error: {e}")
            continue

    # === Caso POSITIVO: nessuna contraddizione ===
    if not alerts:
        positive_text = _build_positive_analysis(doc)
        return (positive_text, [], 100)

    # === Caso con contraddizioni ===
    # Riscala severity: da range 6-95 a 1-19 per checker
    # Formula lineare pura: ogni +1 severity = -1 score. Copre ogni intero 0-100.
    for a in alerts:
        a['severity'] = max(1, round(a['severity'] / 5))
    total_severity = sum(a['severity'] for a in alerts)
    score = max(0, 100 - total_severity)

    # Ordina per severity decrescente
    alerts.sort(key=lambda a: a['severity'], reverse=True)

    # Costruisci testo
    home = doc.get('home', '?')
    away = doc.get('away', '?')

    lines = []
    lines.append(f"Nella partita {home} - {away} i nostri algoritmi hanno individuato "
                 f"alcuni segnali contrastanti che meritano attenzione.")

    # Aggiungi i top 3-4 alert (i piu gravi) con bullet ▸
    max_alerts = 4 if len(alerts) >= 5 else 3
    for alert in alerts[:max_alerts]:
        lines.append(f"▸ {alert['text']}")

    # Chiusura basata su score
    if score < 25:
        lines.append("Consigliamo particolare prudenza: i segnali sono fortemente discordanti "
                      "e il rischio di errore è elevato.")
    elif score < 50:
        lines.append("Suggeriamo di valutare con attenzione prima di puntare su questa partita.")
    elif score < 75:
        lines.append("Nel complesso, le incongruenze sono moderate: tenerne conto nella valutazione.")
    else:
        lines.append("Le incongruenze sono limitate ma vale la pena tenerle in considerazione.")

    analysis_text = '\n\n'.join(lines)
    alert_ids = [a['id'] for a in alerts]

    return (analysis_text, alert_ids, score)


# =====================================================
# INTEGRAZIONE PIPELINE
# =====================================================

def run_analysis_for_date(date_str, dry_run=False):
    """
    Genera analisi per tutti i documenti unified di una data.
    Aggiorna i documenti con analysis_free, analysis_alerts, analysis_score.

    Returns:
        tuple: (total_analyzed, total_with_alerts)
    """
    coll = db['daily_predictions_unified']
    docs = list(coll.find({'date': date_str}))

    if not docs:
        return (0, 0)

    total = 0
    with_alerts = 0

    for doc in docs:
        analysis_free, analysis_alerts, analysis_score = generate_free_analysis(doc)
        total += 1

        if analysis_alerts:
            with_alerts += 1

        if not dry_run:
            coll.update_one(
                {'_id': doc['_id']},
                {'$set': {
                    'analysis_free': analysis_free,
                    'analysis_alerts': analysis_alerts,
                    'analysis_score': analysis_score,
                }}
            )

    return (total, with_alerts)


# =====================================================
# MAIN (standalone)
# =====================================================

def main():
    parser = argparse.ArgumentParser(description='Analisi del Match — Generatore Free (22 checker)')
    parser.add_argument('date', nargs='?', help='Data YYYY-MM-DD (default: ultimi 7 giorni)')
    parser.add_argument('--dry-run', action='store_true', help='Simula senza scrivere')
    parser.add_argument('--days', type=int, default=7, help='Quanti giorni analizzare (default: 7)')
    args = parser.parse_args()

    if args.date:
        # Data specifica → solo quella
        dates = [args.date]
    else:
        # Ultimi N giorni (oggi + N-1 precedenti)
        today = datetime.now()
        dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(args.days)]

    print(f"\n  Analisi del Match — {len(dates)} giorni da analizzare")
    if args.dry_run:
        print("  [DRY RUN — nessuna scrittura]")

    grand_total = 0
    grand_alerts = 0

    for date_str in dates:
        total, with_alerts = run_analysis_for_date(date_str, dry_run=args.dry_run)
        if total > 0:
            print(f"  📅 {date_str}: {total} partite, {with_alerts} con contraddizioni")
        grand_total += total
        grand_alerts += with_alerts

    print(f"\n  ═══ TOTALE: {grand_total} partite analizzate, {grand_alerts} con contraddizioni ═══")

    if args.dry_run and grand_total > 0:
        coll = db['daily_predictions_unified']
        # Mostra sample dall'ultimo giorno con dati
        for date_str in dates:
            docs = list(coll.find({'date': date_str}))
            shown = 0
            for doc in docs:
                text, alerts, score = generate_free_analysis(doc)
                if alerts:
                    print(f"\n  --- {doc.get('home')} vs {doc.get('away')} ({date_str}) ---")
                    print(f"  Score coerenza: {score}/100")
                    print(f"  Alert ({len(alerts)}): {', '.join(alerts)}")
                    print(f"  Testo: {text[:300]}...")
                    shown += 1
                    if shown >= 3:
                        break
            if shown >= 3:
                break

    print()


if __name__ == '__main__':
    main()
