"""
🔬 CONFIDENCE ANALYZER - Calcolo Metriche di Affidabilità
════════════════════════════════════════════════════════════

Calcola tutte le metriche di confidence per le simulazioni Monte Carlo:
- Deviazione standard e confidence per gol
- Analisi segni 1X2 con detection anomalie
- GG/NG, Under/Over, Multigol
- Metriche statistiche avanzate (correlazione, skewness, kurtosis)
- Confidence globale per categorie di mercato

USAGE:
    from confidence_analyzer import ConfidenceCalculator
    
    calculator = ConfidenceCalculator()
    confidence_data = calculator.calculate_all_metrics(
        results=[(1,2), (0,1), (2,0), ...],  # Lista tuple (gh, ga)
        real_gh=2,  # Gol casa reali (opzionale)
        real_ga=0   # Gol ospite reali (opzionale)
    )
"""

import numpy as np
from scipy import stats as scipy_stats
from collections import Counter


class ConfidenceCalculator:
    """Calcolatore di metriche confidence per simulazioni"""
    
    def __init__(self):
        pass
    
    def calculate_all_metrics(self, results, real_gh=None, real_ga=None):
        """
        Calcola TUTTE le metriche confidence dai risultati delle simulazioni.
        
        Args:
            results: Lista di tuple (home_goals, away_goals)
            real_gh: Gol casa reali (opzionale, per accuracy)
            real_ga: Gol ospite reali (opzionale, per accuracy)
        
        Returns:
            dict: Dizionario completo con tutte le metriche confidence
        """
        
        total = len(results)
        if total == 0:
            return self._empty_confidence()
        
        # Liste base
        home_goals_list = [gh for gh, ga in results]
        away_goals_list = [ga for gh, ga in results]
        total_goals_list = [gh + ga for gh, ga in results]
        
        # ═══════════════════════════════════════════════════════════
        # 🎯 CATEGORIA GOL
        # ═══════════════════════════════════════════════════════════
        gol_metrics = self._calculate_gol_metrics(home_goals_list, away_goals_list, total_goals_list)
        
        # ═══════════════════════════════════════════════════════════
        # 🏆 CATEGORIA SEGNI 1X2
        # ═══════════════════════════════════════════════════════════
        segni_metrics = self._calculate_segni_metrics(results)
        
        # ═══════════════════════════════════════════════════════════
        # ⚽ CATEGORIA GG/NOGOL
        # ═══════════════════════════════════════════════════════════
        gg_ng_metrics = self._calculate_gg_ng_metrics(results)
        
        # ═══════════════════════════════════════════════════════════
        # 📊 CATEGORIA UNDER/OVER
        # ═══════════════════════════════════════════════════════════
        uo_metrics = self._calculate_under_over_metrics(total_goals_list)
        
        # ═══════════════════════════════════════════════════════════
        # 🎲 CATEGORIA MULTIGOL
        # ═══════════════════════════════════════════════════════════
        multigol_metrics = self._calculate_multigol_metrics(home_goals_list, away_goals_list, total)
        
        # ═══════════════════════════════════════════════════════════
        # 🏅 RISULTATI ESATTI
        # ═══════════════════════════════════════════════════════════
        exact_scores = Counter([f"{gh}-{ga}" for gh, ga in results])
        exact_metrics = self._calculate_exact_scores_metrics(exact_scores, total)
        
        # ═══════════════════════════════════════════════════════════
        # 🎰 MERCATI ESOTICI
        # ═══════════════════════════════════════════════════════════
        exotic_metrics = self._calculate_exotic_metrics(results, total)
        
        # ═══════════════════════════════════════════════════════════
        # 🔬 METRICHE STATISTICHE AVANZATE
        # ═══════════════════════════════════════════════════════════
        advanced_metrics = self._calculate_advanced_metrics(home_goals_list, away_goals_list)
        
        # ═══════════════════════════════════════════════════════════
        # 🌍 CONFIDENCE GLOBALE PER CATEGORIE
        # ═══════════════════════════════════════════════════════════
        categories = {
            'gol': gol_metrics['category_confidence'],
            'segni': segni_metrics['category_confidence'],
            'gg_ng': gg_ng_metrics['confidence'],
            'under_over': uo_metrics['category_confidence'],
            'multigol': multigol_metrics['category_confidence']
        }
        
        global_confidence = np.mean(list(categories.values()))
        
        most_reliable = max(categories.items(), key=lambda x: x[1])
        least_reliable = min(categories.items(), key=lambda x: x[1])
        
        # ═══════════════════════════════════════════════════════════
        # 🎯 RETURN COMPLETO
        # ═══════════════════════════════════════════════════════════
        return {
            'gol': gol_metrics,
            'segni': segni_metrics,
            'gg_ng': gg_ng_metrics,
            'under_over': uo_metrics['details'],
            'most_reliable_uo': uo_metrics['most_reliable'],
            'multigol': multigol_metrics,
            'exact_scores_analysis': exact_metrics,
            'exotic': exotic_metrics,
            'advanced': advanced_metrics,
            'categories': categories,
            'global_confidence': round(global_confidence, 1),
            'most_reliable_market': {
                'name': most_reliable[0].upper(),
                'confidence': round(most_reliable[1], 1)
            },
            'least_reliable_market': {
                'name': least_reliable[0].upper(),
                'confidence': round(least_reliable[1], 1)
            }
        }
    
    def _calculate_gol_metrics(self, home_goals_list, away_goals_list, total_goals_list):
        """Calcola metriche confidence per i gol"""
        
        # STD DEV (SAFE - evita warning su liste vuote)
        std_home = np.std(home_goals_list) if len(home_goals_list) > 1 else 0.0
        std_away = np.std(away_goals_list) if len(away_goals_list) > 1 else 0.0  
        std_total = np.std(total_goals_list) if len(total_goals_list) > 1 else 0.0

        
        # Confidence (inverso della std normalizzata)
        confidence_home = max(0, min(100, 100 - (std_home * 25)))
        confidence_away = max(0, min(100, 100 - (std_away * 25)))
        confidence_total = max(0, min(100, 100 - (std_total * 15)))
        
        # Varianza
        var_home = np.var(home_goals_list)
        var_away = np.var(away_goals_list)
        var_ratio = var_home / var_away if var_away > 0 else 0
        
        # Confidence categoria
        category_confidence = (confidence_home + confidence_away + confidence_total) / 3
        
        return {
            'home': {
                'std': round(std_home, 3),
                'confidence': round(confidence_home, 1)
            },
            'away': {
                'std': round(std_away, 3),
                'confidence': round(confidence_away, 1)
            },
            'total': {
                'std': round(std_total, 3),
                'confidence': round(confidence_total, 1)
            },
            'variance_ratio': round(var_ratio, 2),
            'variance_comparison': 'Casa > Ospite' if var_home > var_away else 'Ospite > Casa',
            'category_confidence': round(category_confidence, 1)
        }
    
    def _calculate_segni_metrics(self, results):
        """Calcola metriche confidence per i segni 1X2"""
        
        total = len(results)
        
        # Calcola segni
        signs_list = []
        for gh, ga in results:
            if gh > ga:
                signs_list.append('1')
            elif gh == ga:
                signs_list.append('X')
            else:
                signs_list.append('2')
        
        sign_counter = Counter(signs_list)
        
        # Percentuali
        pct_1 = (sign_counter.get('1', 0) / total * 100)
        pct_x = (sign_counter.get('X', 0) / total * 100)
        pct_2 = (sign_counter.get('2', 0) / total * 100)
        
        # Confidence per ogni segno
        confidence_sign_1 = max(0, 100 - abs(50 - pct_1))
        confidence_sign_x = max(0, 100 - abs(50 - pct_x))
        confidence_sign_2 = max(0, 100 - abs(50 - pct_2))
        
        # Segno più probabile
        most_probable_sign = max([('1', pct_1), ('X', pct_x), ('2', pct_2)], key=lambda x: x[1])
        sign_confidence_winner = most_probable_sign[1]
        
        # Margini vittoria
        home_wins = [(gh - ga) for gh, ga in results if gh > ga]
        away_wins = [(ga - gh) for gh, ga in results if ga > gh]
        
        avg_home_margin = np.mean(home_wins) if home_wins else 0
        avg_away_margin = np.mean(away_wins) if away_wins else 0
        
        # Analisi TOP 10 risultati esatti
        exact_scores = Counter([f"{gh}-{ga}" for gh, ga in results])
        top_10 = exact_scores.most_common(10)
        
        top10_signs = {'1': [], 'X': [], '2': []}
        for rank, (score, count) in enumerate(top_10, 1):
            gh, ga = map(int, score.split('-'))
            if gh > ga:
                sign = '1'
            elif gh == ga:
                sign = 'X'
            else:
                sign = '2'
            top10_signs[sign].append(rank)
        
        count_1_in_top10 = len(top10_signs['1'])
        count_x_in_top10 = len(top10_signs['X'])
        count_2_in_top10 = len(top10_signs['2'])
        
        # Detection anomalie
        anomaly_detected = False
        anomaly_message = ""
        
        least_probable_sign = min([('1', pct_1), ('X', pct_x), ('2', pct_2)], key=lambda x: x[1])[0]
        if least_probable_sign in top10_signs and any(pos <= 5 for pos in top10_signs[least_probable_sign]):
            anomaly_detected = True
            first_pos = min(top10_signs[least_probable_sign])
            anomaly_message = f"Risultato '{least_probable_sign}' in posizione #{first_pos} nonostante bassa probabilità generale ({min(pct_1, pct_x, pct_2):.1f}%)"
            sign_confidence_winner *= 0.92  # Penalità -8%
        
        dominance_pct = max(count_1_in_top10, count_x_in_top10, count_2_in_top10) / 10 * 100
        
        # Confidence categoria
        category_confidence = (confidence_sign_1 + confidence_sign_x + confidence_sign_2) / 3
        
        return {
            'sign_1': {
                'percentage': round(pct_1, 1),
                'confidence': round(confidence_sign_1, 1)
            },
            'sign_x': {
                'percentage': round(pct_x, 1),
                'confidence': round(confidence_sign_x, 1)
            },
            'sign_2': {
                'percentage': round(pct_2, 1),
                'confidence': round(confidence_sign_2, 1)
            },
            'most_probable': most_probable_sign[0],
            'most_probable_confidence': round(sign_confidence_winner, 1),
            'margins': {
                'home_wins_avg': round(avg_home_margin, 2),
                'away_wins_avg': round(avg_away_margin, 2)
            },
            'top10_distribution': {
                'sign_1_count': count_1_in_top10,
                'sign_x_count': count_x_in_top10,
                'sign_2_count': count_2_in_top10,
                'sign_1_positions': top10_signs['1'],
                'sign_x_positions': top10_signs['X'],
                'sign_2_positions': top10_signs['2'],
                'dominance_pct': round(dominance_pct, 1)
            },
            'anomaly': {
                'detected': anomaly_detected,
                'message': anomaly_message
            },
            'category_confidence': round(category_confidence, 1)
        }
    
    def _calculate_gg_ng_metrics(self, results):
        """Calcola metriche confidence per GG/NoGol"""
        
        gg_list = [1 if (gh > 0 and ga > 0) else 0 for gh, ga in results]
        std_gg = np.std(gg_list)
        confidence_gg = max(0, min(100, 100 - (std_gg * 100)))
        prob_gg = sum(gg_list) / len(gg_list) * 100
        
        return {
            'confidence': round(confidence_gg, 1),
            'std': round(std_gg, 3),
            'prob_gg': round(prob_gg, 1)
        }
    
    def _calculate_under_over_metrics(self, total_goals_list):
        """Calcola metriche confidence per Under/Over"""
        
        uo_confidence = {}
        for threshold in [0.5, 1.5, 2.5, 3.5]:
            over_list = [1 if tg > threshold else 0 for tg in total_goals_list]
            std_uo = np.std(over_list)
            conf = max(0, min(100, 100 - (std_uo * 100)))
            uo_confidence[f"U/O{threshold}"] = {
                'confidence': round(conf, 1),
                'std': round(std_uo, 3)
            }
        
        most_reliable_uo = max(uo_confidence.items(), key=lambda x: x[1]['confidence'])
        category_confidence = np.mean([v['confidence'] for v in uo_confidence.values()])
        
        return {
            'details': uo_confidence,
            'most_reliable': {
                'threshold': most_reliable_uo[0],
                'confidence': most_reliable_uo[1]['confidence']
            },
            'category_confidence': round(category_confidence, 1)
        }
    
    def _calculate_multigol_metrics(self, home_goals_list, away_goals_list, total):
        """Calcola metriche confidence per Multigol"""
        
        # Range casa
        home_ranges = {
            '0-1': sum(1 for gh in home_goals_list if 0 <= gh <= 1),
            '0-2': sum(1 for gh in home_goals_list if 0 <= gh <= 2),
            '1-2': sum(1 for gh in home_goals_list if 1 <= gh <= 2),
            '1-3': sum(1 for gh in home_goals_list if 1 <= gh <= 3),
            '2-3': sum(1 for gh in home_goals_list if 2 <= gh <= 3),
        }
        most_probable_home_range = max(home_ranges.items(), key=lambda x: x[1])
        
        # Range ospite
        away_ranges = {
            '0-1': sum(1 for ga in away_goals_list if 0 <= ga <= 1),
            '0-2': sum(1 for ga in away_goals_list if 0 <= ga <= 2),
            '1-2': sum(1 for ga in away_goals_list if 1 <= ga <= 2),
            '1-3': sum(1 for ga in away_goals_list if 1 <= ga <= 3),
            '2-3': sum(1 for ga in away_goals_list if 2 <= ga <= 3),
        }
        most_probable_away_range = max(away_ranges.items(), key=lambda x: x[1])
        
        multigol_home_conf = (most_probable_home_range[1] / total) * 100
        multigol_away_conf = (most_probable_away_range[1] / total) * 100
        category_confidence = (multigol_home_conf + multigol_away_conf) / 2
        
        return {
            'home': {
                'range': most_probable_home_range[0],
                'occurrences': most_probable_home_range[1],
                'confidence': round(multigol_home_conf, 1)
            },
            'away': {
                'range': most_probable_away_range[0],
                'occurrences': most_probable_away_range[1],
                'confidence': round(multigol_away_conf, 1)
            },
            'category_confidence': round(category_confidence, 1)
        }
    
    def _calculate_exact_scores_metrics(self, exact_scores, total):
        """Calcola metriche per risultati esatti"""
        
        # Concentrazione top 3
        top3_total = sum(count for score, count in exact_scores.most_common(3))
        concentration_top3 = (top3_total / total) * 100
        
        # Entropia
        probs = [count / total for count in exact_scores.values()]
        entropy = -sum(p * np.log2(p) for p in probs if p > 0)
        
        return {
            'concentration_top3': round(concentration_top3, 1),
            'entropy': round(entropy, 2)
        }
    
    def _calculate_exotic_metrics(self, results, total):
        """Calcola metriche per mercati esotici"""
        
        # Pari/Dispari
        pari_list = [1 if (gh + ga) % 2 == 0 else 0 for gh, ga in results]
        std_pari = np.std(pari_list)
        confidence_pari_dispari = max(0, min(100, 100 - (std_pari * 100)))
        pct_dispari = (len([x for x in pari_list if x == 0]) / len(pari_list)) * 100
        
        # Clean Sheet
        home_cs = sum(1 for gh, ga in results if gh > ga and ga == 0)
        away_cs = sum(1 for gh, ga in results if ga > gh and gh == 0)
        pct_home_cs = (home_cs / total) * 100
        pct_away_cs = (away_cs / total) * 100
        
        cs_list_home = [1 if ga == 0 else 0 for gh, ga in results]
        std_cs = np.std(cs_list_home)
        confidence_cs = max(0, min(100, 100 - (std_cs * 100)))
        
        return {
            'pari_dispari': {
                'confidence': round(confidence_pari_dispari, 1),
                'std': round(std_pari, 3),
                'pct_dispari': round(pct_dispari, 1)
            },
            'clean_sheet': {
                'confidence': round(confidence_cs, 1),
                'home_pct': round(pct_home_cs, 1),
                'away_pct': round(pct_away_cs, 1)
            }
        }
    
    def _calculate_advanced_metrics(self, home_goals_list, away_goals_list):
        """Calcola metriche statistiche avanzate (VERSIONE SICURA ANTI-CRASH)"""
        
        # 1. Calcolo preventivo delle deviazioni standard
        # Usiamo ddof=1 per la deviazione campionaria, o 0 per la popolazione (default numpy)
        std_h = np.std(home_goals_list)
        std_a = np.std(away_goals_list)
        epsilon = 1e-9 # Soglia minima per considerare la varianza valida

        # 2. Correlazione Sicura
        # Se una delle due squadre ha varianza 0 (ha fatto sempre gli stessi gol), la correlazione è 0
        if std_h > epsilon and std_a > epsilon and len(home_goals_list) > 1:
            try:
                correlation = np.corrcoef(home_goals_list, away_goals_list)[0, 1]
                if np.isnan(correlation): correlation = 0.0
            except:
                correlation = 0.0
        else:
            correlation = 0.0

        # 3. Skewness Sicura (Asimmetria)
        if std_h > epsilon:
            try:
                skew_home = float(scipy_stats.skew(home_goals_list))
                if np.isnan(skew_home): skew_home = 0.0
            except: skew_home = 0.0
        else:
            skew_home = 0.0

        if std_a > epsilon:
            try:
                skew_away = float(scipy_stats.skew(away_goals_list))
                if np.isnan(skew_away): skew_away = 0.0
            except: skew_away = 0.0
        else:
            skew_away = 0.0
        
        # 4. Kurtosis Sicura (Appiattimento)
        if std_h > epsilon:
            try:
                kurt_home = float(scipy_stats.kurtosis(home_goals_list))
                if np.isnan(kurt_home): kurt_home = 0.0
            except: kurt_home = 0.0
        else:
            kurt_home = 0.0

        if std_a > epsilon:
            try:
                kurt_away = float(scipy_stats.kurtosis(away_goals_list))
                if np.isnan(kurt_away): kurt_away = 0.0
            except: kurt_away = 0.0
        else:
            kurt_away = 0.0
        
        # 5. Varianza (Calcolo standard, non crasha mai ma gestiamo ratio)
        var_home = np.var(home_goals_list)
        var_away = np.var(away_goals_list)
        
        # Ratio sicuro
        if var_away > epsilon:
            var_ratio = var_home / var_away
        else:
            # Se away ha varianza 0, se home ha varianza > 0 il ratio è alto, altrimenti 1
            var_ratio = 10.0 if var_home > epsilon else 1.0
        
        return {
            'correlation_home_away': round(correlation, 3),
            'skewness': {
                'home': round(skew_home, 2),
                'away': round(skew_away, 2)
            },
            'kurtosis': {
                'home': round(kurt_home, 2),
                'away': round(kurt_away, 2)
            },
            'variance': {
                'home': round(var_home, 3),
                'away': round(var_away, 3),
                'ratio': round(var_ratio, 2)
            }
        }
    
    def _empty_confidence(self):
        """Ritorna struttura vuota se non ci sono dati"""
        return {
            'gol': {},
            'segni': {},
            'gg_ng': {},
            'under_over': {},
            'multigol': {},
            'exact_scores_analysis': {},
            'exotic': {},
            'advanced': {},
            'categories': {},
            'global_confidence': 0,
            'most_reliable_market': {'name': 'N/A', 'confidence': 0},
            'least_reliable_market': {'name': 'N/A', 'confidence': 0}
        }