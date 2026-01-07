"""
🔬 DEEP ANALYSIS MODULE - Analisi Dettagliata Simulazioni Monte Carlo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Raccoglie OGNI SINGOLO DETTAGLIO delle simulazioni e genera:
- CSV ultra-dettagliato per Excel
- HTML interattivo con tabelle espandibili
- JSON completo per elaborazioni esterne

USAGE:
    from deep_analysis import DeepAnalyzer
    
    analyzer = DeepAnalyzer()
    analyzer.start_match("Roma", "Como", real_result="2-0")
    
    # Durante le simulazioni
    for cycle in range(500):
        gh, ga = simulate()
        analyzer.add_result(algo_id=2, home_goals=gh, away_goals=ga)
    
    analyzer.end_match()
    analyzer.save_report("report.csv", "report.html", "report.json")
"""

import json
import csv
import numpy as np
from collections import Counter
from datetime import datetime
from .confidence_analyzer import ConfidenceCalculator
from .confidence_html_builder import ConfidenceHTMLBuilder

class DeepAnalyzer:
    """Analizzatore profondo per simulazioni Monte Carlo"""
    
    def __init__(self):
        self.matches = []  # Lista di tutte le partite analizzate
        self.current_match = None  # Partita in analisi
        
    def start_match(self, home_team, away_team, real_result=None, league="Unknown", date_str=None):
        """Inizia l'analisi di una nuova partita"""
        
        # Parse risultato reale
        real_gh, real_ga = None, None
        if real_result and isinstance(real_result, str) and "-" in real_result:
            try:
                real_gh, real_ga = map(int, real_result.split("-"))
            except:
                pass
        
        self.current_match = {
            'home_team': home_team,
            'away_team': away_team,
            'league': league,
            'date': date_str or datetime.now().strftime("%Y-%m-%d"),
            'real_result': real_result,
            'real_gh': real_gh,
            'real_ga': real_ga,
            'algorithms': {}  # {algo_id: {results: [...], stats: {...}}}
        }
    
    def add_result(self, algo_id, home_goals, away_goals, lambda_h=None, lambda_a=None, 
               odds_real=None, odds_qt=None, team_scores=None, h2h_stats=None):

        if self.current_match is None:
            raise ValueError("Devi chiamare start_match() prima!")
        
        # Inizializza algoritmo se non esiste
        if algo_id not in self.current_match['algorithms']:
            self.current_match['algorithms'][algo_id] = {
                'results': [],      # Lista gol casuali (retrocompatibilità)
                'lambdas': [],      # Lista lambda teorici (NUOVO)
                'total_simulations': 0
            }
        
        # ✅ SE HAI I LAMBDA, salvali (Modalità Teorica)
        if lambda_h is not None and lambda_a is not None:
            self.current_match['algorithms'][algo_id]['lambdas'].append((lambda_h, lambda_a))
        
        # ✅ ALTRIMENTI salva i gol (Modalità Empirica - retrocompatibilità)
        else:
            self.current_match['algorithms'][algo_id]['results'].append((home_goals, away_goals))
        
        self.current_match['algorithms'][algo_id]['total_simulations'] += 1
    
    def end_match(self):
        """Finalizza l'analisi della partita corrente e calcola le statistiche"""
        if self.current_match is None:
            return
        
        # Calcola statistiche per ogni algoritmo
        for algo_id, data in self.current_match['algorithms'].items():
            # ✅ Passa l'intero oggetto data invece di solo results
            data['stats'] = self._calculate_stats(
                data,
                self.current_match['real_gh'],
                self.current_match['real_ga']
            )
        
        # Salva partita
        self.matches.append(self.current_match)
        self.current_match = None
    
    def _calculate_stats(self, algo_data, real_gh=None, real_ga=None):
        """Calcola statistiche usando lambda teorici O risultati empirici"""
        
        # ✅ PRIORITÀ 1: Se hai lambda, usa quelli (Teorico)
        if 'lambdas' in algo_data and algo_data['lambdas']:
            return self._calculate_stats_theoretical(algo_data['lambdas'], real_gh, real_ga)
        
        # ✅ PRIORITÀ 2: Altrimenti usa results (Empirico - retrocompatibilità)
        elif 'results' in algo_data and algo_data['results']:
            return self._calculate_stats_empirical(algo_data['results'], real_gh, real_ga)
        
        return {}
    
    def _calculate_stats_empirical(self, results, real_gh=None, real_ga=None):
        """Calcola statistiche da risultati empirici (VECCHIO METODO)"""
        
        total = len(results)
        if total == 0:
            return {}
        
    def _calculate_stats_theoretical(self, lambdas_list, real_gh=None, real_ga=None, 
                                    odds_real=None, odds_qt=None, team_scores=None, h2h_stats=None):
        """
        Calcola probabilità teoriche usando Poisson dai lambda medi
        + BLENDING con quote reali, quote teoriche, power e storico H2H
        """
        from scipy.stats import poisson
        import numpy as np
        
        total_simulations = len(lambdas_list)
        if total_simulations == 0:
            return {}
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1️⃣ CALCOLA LAMBDA MEDI (da N lambda con fluttuazione ±15%)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        lambda_h_list = [lh for lh, la in lambdas_list]
        lambda_a_list = [la for lh, la in lambdas_list]
        
        lambda_h_medio = np.mean(lambda_h_list)
        lambda_a_medio = np.mean(lambda_a_list)
        
        # Deviazione standard dei lambda (misura fluttuazione)
        std_lambda_h = np.std(lambda_h_list) if len(lambda_h_list) > 1 else 0.0
        std_lambda_a = np.std(lambda_a_list) if len(lambda_a_list) > 1 else 0.0
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2️⃣ GENERA MATRICE POISSON TEORICA (7x7 = 49 risultati possibili)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        prob_matrix = {}
        for gh in range(7):
            for ga in range(7):
                p_home = poisson.pmf(gh, lambda_h_medio)
                p_away = poisson.pmf(ga, lambda_a_medio)
                prob_matrix[f"{gh}-{ga}"] = p_home * p_away
        
        # Normalizza (somma = 100%)
        total_prob = sum(prob_matrix.values())
        prob_matrix = {k: v/total_prob for k, v in prob_matrix.items()}
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3️⃣ CALCOLA SEGNI 1X2 DA MONTE CARLO (Poisson puro)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        sign_1_mc = sum(prob for score, prob in prob_matrix.items() 
                        if int(score.split('-')[0]) > int(score.split('-')[1]))
        sign_x_mc = sum(prob for score, prob in prob_matrix.items() 
                        if int(score.split('-')[0]) == int(score.split('-')[1]))
        sign_2_mc = sum(prob for score, prob in prob_matrix.items() 
                        if int(score.split('-')[0]) < int(score.split('-')[1]))
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔥 BLENDING 1X2: Monte Carlo + Quote Reali + Quote Teoriche
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        sources_1x2 = []
        weights_1x2 = []
        
        # Monte Carlo: SEMPRE presente
        sources_1x2.append((sign_1_mc, sign_x_mc, sign_2_mc))
        weights_1x2.append(0.40)  # 40% peso base
        
        # Quote Reali: Se disponibili
        if odds_real and '1' in odds_real and 'X' in odds_real and '2' in odds_real:
            try:
                prob_1_real = 1 / float(odds_real['1']) if float(odds_real['1']) > 0 else 0
                prob_x_real = 1 / float(odds_real['X']) if float(odds_real['X']) > 0 else 0
                prob_2_real = 1 / float(odds_real['2']) if float(odds_real['2']) > 0 else 0
                
                total_real = prob_1_real + prob_x_real + prob_2_real
                if total_real > 0:
                    prob_1_real /= total_real
                    prob_x_real /= total_real
                    prob_2_real /= total_real
                    
                    sources_1x2.append((prob_1_real, prob_x_real, prob_2_real))
                    weights_1x2.append(0.35)  # 35% peso
            except:
                pass
        
        # Quote Teoriche: Se disponibili
        if odds_qt and '1' in odds_qt and 'X' in odds_qt and '2' in odds_qt:
            try:
                prob_1_qt = 1 / float(odds_qt['1']) if float(odds_qt['1']) > 0 else 0
                prob_x_qt = 1 / float(odds_qt['X']) if float(odds_qt['X']) > 0 else 0
                prob_2_qt = 1 / float(odds_qt['2']) if float(odds_qt['2']) > 0 else 0
                
                total_qt = prob_1_qt + prob_x_qt + prob_2_qt
                if total_qt > 0:
                    prob_1_qt /= total_qt
                    prob_x_qt /= total_qt
                    prob_2_qt /= total_qt
                    
                    sources_1x2.append((prob_1_qt, prob_x_qt, prob_2_qt))
                    weights_1x2.append(0.25)  # 25% peso
            except:
                pass
        
        # Normalizza pesi (se mancano fonti, ridistribuisci)
        total_weight = sum(weights_1x2)
        weights_1x2 = [w / total_weight for w in weights_1x2]
        
        # MEDIA PESATA 1X2
        sign_1_final = sum(src[0] * w for src, w in zip(sources_1x2, weights_1x2))
        sign_x_final = sum(src[1] * w for src, w in zip(sources_1x2, weights_1x2))
        sign_2_final = sum(src[2] * w for src, w in zip(sources_1x2, weights_1x2))
        
        # Normalizza (sicurezza)
        total_1x2 = sign_1_final + sign_x_final + sign_2_final
        sign_1_final /= total_1x2
        sign_x_final /= total_1x2
        sign_2_final /= total_1x2
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 4️⃣ CALCOLA GG/NG DA MONTE CARLO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        gg_mc = sum(prob for score, prob in prob_matrix.items() 
                    if int(score.split('-')[0]) > 0 and int(score.split('-')[1]) > 0)
        ng_mc = 1 - gg_mc
        
        # 🔥 BLENDING GG/NG: Monte Carlo + Power + H2H
        sources_ggng = [(gg_mc, ng_mc)]
        weights_ggng = [0.40]
        
        # Power Attack/Defense
        if team_scores and 'home' in team_scores and 'away' in team_scores:
            try:
                h_scores = team_scores['home']
                a_scores = team_scores['away']
                
                att_h = h_scores.get('attack_home', 5.0)
                def_a = a_scores.get('defense_away', 5.0)
                att_a = a_scores.get('attack_away', 5.0)
                def_h = h_scores.get('defense_home', 5.0)
                
                # Probabilità che casa segni
                prob_h_score = min(0.95, (att_h + (10 - def_a)) / 20)
                # Probabilità che ospite segni
                prob_a_score = min(0.95, (att_a + (10 - def_h)) / 20)
                
                gg_power = prob_h_score * prob_a_score
                ng_power = 1 - gg_power
                
                sources_ggng.append((gg_power, ng_power))
                weights_ggng.append(0.30)
            except:
                pass
        
        # Storico H2H
        if h2h_stats and 'gg_pct' in h2h_stats:
            try:
                gg_h2h = h2h_stats['gg_pct'] / 100
                ng_h2h = 1 - gg_h2h
                
                sources_ggng.append((gg_h2h, ng_h2h))
                weights_ggng.append(0.30)
            except:
                pass
        
        # Normalizza e calcola media
        total_weight_gg = sum(weights_ggng)
        weights_ggng = [w / total_weight_gg for w in weights_ggng]
        
        gg_final = sum(src[0] * w for src, w in zip(sources_ggng, weights_ggng))
        ng_final = 1 - gg_final
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 5️⃣ CALCOLA UNDER/OVER DA MONTE CARLO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        thresholds = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5]
        under_over = {}
        
        for th in thresholds:
            under_mc = sum(prob for score, prob in prob_matrix.items() 
                        if sum(map(int, score.split('-'))) < th)
            over_mc = 1 - under_mc
            
            # 🔥 BLENDING U/O: Monte Carlo + Power + H2H
            sources_uo = [(under_mc, over_mc)]
            weights_uo = [0.40]
            
            # Power (solo per 2.5)
            if th == 2.5 and team_scores:
                try:
                    expected_total = (lambda_h_medio + lambda_a_medio)
                    if expected_total < 2.5:
                        under_power = 0.65
                    elif expected_total > 2.5:
                        under_power = 0.35
                    else:
                        under_power = 0.50
                    
                    over_power = 1 - under_power
                    sources_uo.append((under_power, over_power))
                    weights_uo.append(0.30)
                except:
                    pass
            
            # H2H (solo per 2.5)
            if th == 2.5 and h2h_stats and 'over25_pct' in h2h_stats:
                try:
                    over_h2h = h2h_stats['over25_pct'] / 100
                    under_h2h = 1 - over_h2h
                    
                    sources_uo.append((under_h2h, over_h2h))
                    weights_uo.append(0.30)
                except:
                    pass
            
            # Normalizza e calcola media
            total_weight_uo = sum(weights_uo)
            weights_uo = [w / total_weight_uo for w in weights_uo]
            
            under_final = sum(src[0] * w for src, w in zip(sources_uo, weights_uo))
            over_final = 1 - under_final
            
            under_over[f"U{th}"] = {
                'count': int(under_final * total_simulations),
                'pct': round(under_final * 100, 2)
            }
            under_over[f"O{th}"] = {
                'count': int(over_final * total_simulations),
                'pct': round(over_final * 100, 2)
            }
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 6️⃣ TOP 10 RISULTATI ESATTI
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        sorted_scores = sorted(prob_matrix.items(), key=lambda x: x[1], reverse=True)
        top_10_scores = [(score, int(prob * total_simulations)) for score, prob in sorted_scores[:10]]
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 7️⃣ DISTRIBUZIONE GOL (Casa e Trasferta)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        home_goals_dist = {}
        away_goals_dist = {}
        
        for gh in range(7):
            home_goals_dist[gh] = int(poisson.pmf(gh, lambda_h_medio) * total_simulations)
        
        for ga in range(7):
            away_goals_dist[ga] = int(poisson.pmf(ga, lambda_a_medio) * total_simulations)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 8️⃣ MEDIE GOL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        home_avg_goals = lambda_h_medio
        away_avg_goals = lambda_a_medio
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 9️⃣ STATISTICHE CASA/TRASFERTA (segna/non segna)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        home_scored_prob = 1 - poisson.pmf(0, lambda_h_medio)
        away_scored_prob = 1 - poisson.pmf(0, lambda_a_medio)
        
        home_scored = int(home_scored_prob * total_simulations)
        away_scored = int(away_scored_prob * total_simulations)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔟 CONFIDENCE (Basato su varianza dei lambda)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        confidence_home = max(0, min(100, 100 - (std_lambda_h * 25)))
        confidence_away = max(0, min(100, 100 - (std_lambda_a * 25)))
        
        total_std = np.std([lh + la for lh, la in lambdas_list]) if total_simulations > 1 else 0.0
        confidence_total = max(0, min(100, 100 - (total_std * 15)))
        
        global_confidence = (confidence_home + confidence_away + confidence_total) / 3
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1️⃣1️⃣ ACCURACY (se disponibile risultato reale)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        accuracy = None
        if real_gh is not None and real_ga is not None:
            real_score_str = f"{real_gh}-{real_ga}"
            real_score_prob = prob_matrix.get(real_score_str, 0)
            
            real_score_rank = None
            for rank, (score, _) in enumerate(sorted_scores, 1):
                if score == real_score_str:
                    real_score_rank = rank
                    break
            
            predicted_score = sorted_scores[0][0]
            pred_gh, pred_ga = map(int, predicted_score.split("-"))
            
            real_sign = "1" if real_gh > real_ga else ("X" if real_gh == real_ga else "2")
            pred_sign = "1" if pred_gh > pred_ga else ("X" if pred_gh == pred_ga else "2")
            
            real_gg = "GG" if (real_gh > 0 and real_ga > 0) else "NG"
            pred_gg = "GG" if (pred_gh > 0 and pred_ga > 0) else "NG"
            
            real_total = real_gh + real_ga
            pred_total = pred_gh + pred_ga
            
            accuracy = {
                'predicted_score': predicted_score,
                'real_score': real_score_str,
                'exact_match': (predicted_score == real_score_str),
                'sign_correct': (pred_sign == real_sign),
                'home_goals_correct': (pred_gh == real_gh),
                'away_goals_correct': (pred_ga == real_ga),
                'gg_ng_correct': (pred_gg == real_gg),
                'u25_correct': ((pred_total <= 2.5) == (real_total <= 2.5)),
                'real_score_count': int(real_score_prob * total_simulations),
                'real_score_pct': round(real_score_prob * 100, 2),
                'real_score_rank': real_score_rank or "N/A"
            }
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🎯 RITORNA TUTTO (con valori BLENDED)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        return {
            'total_simulations': total_simulations,
            
            # Distribuzione gol
            'home_goals_distribution': home_goals_dist,
            'away_goals_distribution': away_goals_dist,
            
            # Risultati esatti
            'exact_scores': {score: int(prob * total_simulations) for score, prob in prob_matrix.items()},
            'top_10_scores': top_10_scores,
            
            # Segni (BLENDED)
            'sign_1': {'count': int(sign_1_final * total_simulations), 'pct': round(sign_1_final * 100, 2)},
            'sign_x': {'count': int(sign_x_final * total_simulations), 'pct': round(sign_x_final * 100, 2)},
            'sign_2': {'count': int(sign_2_final * total_simulations), 'pct': round(sign_2_final * 100, 2)},
            
            # GG/NG (BLENDED)
            'gg': {'count': int(gg_final * total_simulations), 'pct': round(gg_final * 100, 2)},
            'ng': {'count': int(ng_final * total_simulations), 'pct': round(ng_final * 100, 2)},
            
            # Under/Over (BLENDED)
            'under_over': under_over,
            
            # Statistiche Casa
            'home_scored': {'count': home_scored, 'pct': round(home_scored_prob * 100, 2)},
            'home_not_scored': {'count': total_simulations - home_scored, 'pct': round((1 - home_scored_prob) * 100, 2)},
            'home_avg_goals': round(home_avg_goals, 3),
            
            # Statistiche Trasferta
            'away_scored': {'count': away_scored, 'pct': round(away_scored_prob * 100, 2)},
            'away_not_scored': {'count': total_simulations - away_scored, 'pct': round((1 - away_scored_prob) * 100, 2)},
            'away_avg_goals': round(away_avg_goals, 3),
            
            # Confidence
            'confidence': {
                'home_std': round(std_lambda_h, 3),
                'away_std': round(std_lambda_a, 3),
                'total_std': round(total_std, 3),
                'home_confidence': round(confidence_home, 1),
                'away_confidence': round(confidence_away, 1),
                'total_confidence': round(confidence_total, 1),
                'global_confidence': round(global_confidence, 1),
                'lambda_medio_casa': round(lambda_h_medio, 3),
                'lambda_medio_ospite': round(lambda_a_medio, 3)
            },
            
            # Accuracy
            'accuracy': accuracy
        }

        
        # ═══════════════════════════════════════════════════════════
        # 🔬 CALCOLO CONFIDENCE (usa il modulo separato)
        # ═══════════════════════════════════════════════════════════
        
        conf_calculator = ConfidenceCalculator()
        confidence_data = conf_calculator.calculate_all_metrics(results, real_gh, real_ga)
        
        # ═══════════════════════════════════════════════════════════
        # 🎲 DEVIAZIONE STANDARD E CONFIDENCE
        # ═══════════════════════════════════════════════════════════
        
        home_goals_list = [gh for gh, ga in results]
        away_goals_list = [ga for gh, ga in results]
        total_goals_list = [gh + ga for gh, ga in results]

        # SAFE NUMPY: evita warning su liste vuote (PRIMA PARTITA)
        std_home = np.std(home_goals_list) if len(home_goals_list) > 1 else 0.0
        std_away = np.std(away_goals_list) if len(away_goals_list) > 1 else 0.0
        std_total = np.std(total_goals_list) if len(total_goals_list) > 1 else 0.0

        # Confidence Score (0-100): più bassa la std, più alto il confidence
        confidence_home = max(0, min(100, 100 - (std_home * 25)))
        confidence_away = max(0, min(100, 100 - (std_away * 25)))
        confidence_total = max(0, min(100, 100 - (std_total * 15)))
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1️⃣ DISTRIBUZIONE GOL ASSOLUTA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        home_goals_count = Counter([gh for gh, ga in results])
        away_goals_count = Counter([ga for gh, ga in results])
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2️⃣ TUTTI I RISULTATI ESATTI (formato "GH-GA")
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        exact_scores = Counter([f"{gh}-{ga}" for gh, ga in results])
        top_10_scores = exact_scores.most_common(10)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3️⃣ SEGNI 1X2
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        sign_1 = sum(1 for gh, ga in results if gh > ga)
        sign_x = sum(1 for gh, ga in results if gh == ga)
        sign_2 = sum(1 for gh, ga in results if gh < ga)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 4️⃣ GOL/NOGOL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        gg = sum(1 for gh, ga in results if gh > 0 and ga > 0)
        ng = total - gg
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 5️⃣ UNDER/OVER (0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        thresholds = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5]
        under_over = {}
        
        for th in thresholds:
            total_goals = [(gh + ga) for gh, ga in results]
            under_count = sum(1 for t in total_goals if t < th)
            over_count = total - under_count
            
            under_over[f"U{th}"] = {
                'count': under_count,
                'pct': round(under_count / total * 100, 2)
            }
            under_over[f"O{th}"] = {
                'count': over_count,
                'pct': round(over_count / total * 100, 2)
            }
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 6️⃣ STATISTICHE GOL CASA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        home_scored = sum(1 for gh, ga in results if gh > 0)
        home_not_scored = total - home_scored
        home_avg = sum([gh for gh, ga in results]) / total
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 7️⃣ STATISTICHE GOL TRASFERTA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        away_scored = sum(1 for gh, ga in results if ga > 0)
        away_not_scored = total - away_scored
        away_avg = sum([ga for gh, ga in results]) / total
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 8️⃣ PARTITE CON TOTALE GOL = N (per N da 0 a 10+)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        total_goals_dist = Counter([gh + ga for gh, ga in results])
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 9️⃣ CONFRONTO CON RISULTATO REALE (se disponibile)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        accuracy = None
        if real_gh is not None and real_ga is not None:
            real_sign = "1" if real_gh > real_ga else ("X" if real_gh == real_ga else "2")
            real_gg = "GG" if (real_gh > 0 and real_ga > 0) else "NG"
            real_total = real_gh + real_ga
            
            # Risultato più probabile
            predicted_score = exact_scores.most_common(1)[0][0]
            pred_gh, pred_ga = map(int, predicted_score.split("-"))
            pred_sign = "1" if pred_gh > pred_ga else ("X" if pred_gh == pred_ga else "2")
            pred_gg = "GG" if (pred_gh > 0 and pred_ga > 0) else "NG"
            pred_total = pred_gh + pred_ga
            
            # Quante volte è uscito il risultato reale?
            real_score_str = f"{real_gh}-{real_ga}"
            real_score_count = exact_scores.get(real_score_str, 0)
            real_score_rank = None
            
            for rank, (score, count) in enumerate(exact_scores.most_common(), 1):
                if score == real_score_str:
                    real_score_rank = rank
                    break
            
            accuracy = {
                'predicted_score': predicted_score,
                'real_score': real_score_str,
                'exact_match': (predicted_score == real_score_str),
                'sign_correct': (pred_sign == real_sign),
                'home_goals_correct': (pred_gh == real_gh),
                'away_goals_correct': (pred_ga == real_ga),
                'gg_ng_correct': (pred_gg == real_gg),
                'u25_correct': ((pred_total <= 2.5) == (real_total <= 2.5)),
                'real_score_count': real_score_count,
                'real_score_pct': round(real_score_count / total * 100, 2),
                'real_score_rank': real_score_rank or "N/A"
            }
            
        # Merge confidence data con std
        confidence_data.update({
            'home_std': round(std_home, 3),
            'away_std': round(std_away, 3),
            'total_std': round(std_total, 3),
            'home_confidence': round(confidence_home, 1),
            'away_confidence': round(confidence_away, 1),
            'total_confidence': round(confidence_total, 1),
            'global_confidence': round((confidence_home + confidence_away + confidence_total) / 3, 1)
        })
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🎯 RITORNA TUTTO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        return {
            'total_simulations': total,
            
            # Distribuzione gol
            'home_goals_distribution': dict(sorted(home_goals_count.items())),
            'away_goals_distribution': dict(sorted(away_goals_count.items())),
            
            # Risultati esatti
            'exact_scores': dict(exact_scores),
            'top_10_scores': top_10_scores,
            
            # Segni
            'sign_1': {'count': sign_1, 'pct': round(sign_1/total*100, 2)},
            'sign_x': {'count': sign_x, 'pct': round(sign_x/total*100, 2)},
            'sign_2': {'count': sign_2, 'pct': round(sign_2/total*100, 2)},
            
            # GG/NG
            'gg': {'count': gg, 'pct': round(gg/total*100, 2)},
            'ng': {'count': ng, 'pct': round(ng/total*100, 2)},
            
            # Under/Over
            'under_over': under_over,
            
            # Statistiche Casa
            'home_scored': {'count': home_scored, 'pct': round(home_scored/total*100, 2)},
            'home_not_scored': {'count': home_not_scored, 'pct': round(home_not_scored/total*100, 2)},
            'home_avg_goals': round(home_avg, 3),
            
            # Statistiche Trasferta
            'away_scored': {'count': away_scored, 'pct': round(away_scored/total*100, 2)},
            'away_not_scored': {'count': away_not_scored, 'pct': round(away_not_scored/total*100, 2)},
            'away_avg_goals': round(away_avg, 3),
            
            # Confidence (calcolata dal modulo separato)
            'confidence': confidence_data,
            
            # Accuracy
            'accuracy': accuracy
        }
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 💾 EXPORT FUNCTIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def save_report(self, csv_path="deep_analysis.csv", html_path="deep_analysis.html", json_path="deep_analysis.json", confidence_path="confidence_report.html"):
        """Salva i report in tutti i formati (incluso Confidence HTML)"""
        
        if not self.matches:
            print("⚠️  Nessuna partita da analizzare!")
            return
        
        # JSON (completo)
        if json_path:
            self._save_json(json_path)
            print(f"✅ JSON salvato: {json_path}")
        
        # CSV (ultra-dettagliato)
        if csv_path:
            self._save_csv(csv_path)
            print(f"✅ CSV salvato: {csv_path}")
        
        # HTML (interattivo)
        if html_path:
            self._save_html(html_path)
            print(f"✅ HTML salvato: {html_path}")
            
        # Confidence HTML (NUOVO!)
        if confidence_path:
            builder = ConfidenceHTMLBuilder()
            builder.generate_report(self.matches, confidence_path)
            print(f"✅ CONFIDENCE HTML salvato: {confidence_path}")
    
    def _save_json(self, path):
        """Salva tutto in JSON (backup completo)"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                'generated_at': datetime.now().isoformat(),
                'total_matches': len(self.matches),
                'matches': self.matches
            }, f, indent=2, ensure_ascii=False)
    
    def _save_csv(self, path):
        """Salva CSV ultra-dettagliato per Excel"""
        
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            
            # Header globale
            writer.writerow(['DEEP ANALYSIS REPORT'])
            writer.writerow(['Generated:', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            writer.writerow(['Total Matches:', len(self.matches)])
            writer.writerow([])
            
            # Per ogni partita
            for match in self.matches:
                writer.writerow(['=' * 100])
                writer.writerow([f"⚽ {match['home_team']} vs {match['away_team']}"])
                writer.writerow(['League:', match['league'], 'Date:', match['date']])
                
                if match['real_result']:
                    writer.writerow(['Real Result:', match['real_result']])
                
                writer.writerow([])
                
                # Per ogni algoritmo
                for algo_id, data in match['algorithms'].items():
                    stats = data['stats']
                    
                    writer.writerow([f"🔹 ALGORITMO {algo_id}"])
                    writer.writerow(['Total Simulations:', stats['total_simulations']])
                    writer.writerow([])
                    
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # DISTRIBUZIONE GOL
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    writer.writerow(['📊 DISTRIBUZIONE GOL CASA'])
                    writer.writerow(['Gol', 'Occorrenze', 'Percentuale'])
                    for gol, count in stats['home_goals_distribution'].items():
                        pct = round(count / stats['total_simulations'] * 100, 2)
                        writer.writerow([gol, count, f"{pct}%"])
                    writer.writerow([])
                    
                    writer.writerow(['📊 DISTRIBUZIONE GOL TRASFERTA'])
                    writer.writerow(['Gol', 'Occorrenze', 'Percentuale'])
                    for gol, count in stats['away_goals_distribution'].items():
                        pct = round(count / stats['total_simulations'] * 100, 2)
                        writer.writerow([gol, count, f"{pct}%"])
                    writer.writerow([])
                    
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # TOP 10 RISULTATI ESATTI
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    writer.writerow(['🏆 TOP 10 RISULTATI ESATTI'])
                    writer.writerow(['Rank', 'Score', 'Occorrenze', 'Percentuale'])
                    for rank, (score, count) in enumerate(stats['top_10_scores'], 1):
                        pct = round(count / stats['total_simulations'] * 100, 2)
                        writer.writerow([rank, score, count, f"{pct}%"])
                    writer.writerow([])
                    
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # SEGNI 1X2
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    writer.writerow(['🎯 SEGNI 1X2'])
                    writer.writerow(['Segno', 'Occorrenze', 'Percentuale'])
                    writer.writerow(['1', stats['sign_1']['count'], f"{stats['sign_1']['pct']}%"])
                    writer.writerow(['X', stats['sign_x']['count'], f"{stats['sign_x']['pct']}%"])
                    writer.writerow(['2', stats['sign_2']['count'], f"{stats['sign_2']['pct']}%"])
                    writer.writerow([])
                    
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # GOL/NOGOL
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    writer.writerow(['⚽ GOL/NOGOL'])
                    writer.writerow(['Tipo', 'Occorrenze', 'Percentuale'])
                    writer.writerow(['GG', stats['gg']['count'], f"{stats['gg']['pct']}%"])
                    writer.writerow(['NG', stats['ng']['count'], f"{stats['ng']['pct']}%"])
                    writer.writerow([])
                    
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # UNDER/OVER
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    writer.writerow(['📊 UNDER/OVER'])
                    writer.writerow(['Soglia', 'Occorrenze', 'Percentuale'])
                    for key, val in stats['under_over'].items():
                        writer.writerow([key, val['count'], f"{val['pct']}%"])
                    writer.writerow([])
                    
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # STATISTICHE CASA/TRASFERTA
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    writer.writerow(['🏠 STATISTICHE CASA'])
                    writer.writerow(['Ha segnato:', stats['home_scored']['count'], f"{stats['home_scored']['pct']}%"])
                    writer.writerow(['Non ha segnato:', stats['home_not_scored']['count'], f"{stats['home_not_scored']['pct']}%"])
                    writer.writerow(['Media gol:', stats['home_avg_goals']])
                    writer.writerow([])
                    
                    writer.writerow(['✈️ STATISTICHE TRASFERTA'])
                    writer.writerow(['Ha segnato:', stats['away_scored']['count'], f"{stats['away_scored']['pct']}%"])
                    writer.writerow(['Non ha segnato:', stats['away_not_scored']['count'], f"{stats['away_not_scored']['pct']}%"])
                    writer.writerow(['Media gol:', stats['away_avg_goals']])
                    writer.writerow([])
                    
                    
                    # ═══════════════════════════════════════════════════════════
                    # 🎲 DEVIAZIONE STANDARD E CONFIDENCE
                    # ═══════════════════════════════════════════════════════════
                    
                    
                    writer.writerow([])
                    writer.writerow(['📊 CONFIDENCE & DEVIAZIONE STANDARD'])
                    writer.writerow(['Metrica', 'Valore', 'Confidence'])
                    writer.writerow(['Gol Casa (Std Dev)', stats['confidence']['home_std'], f"{stats['confidence']['home_confidence']}%"])
                    writer.writerow(['Gol Ospite (Std Dev)', stats['confidence']['away_std'], f"{stats['confidence']['away_confidence']}%"])
                    writer.writerow(['Totale Gol (Std Dev)', stats['confidence']['total_std'], f"{stats['confidence']['total_confidence']}%"])
                    writer.writerow(['Confidence Globale', '-', f"{stats['confidence']['global_confidence']}%"])
                    writer.writerow([])
                    
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # ACCURACY (se disponibile)
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    if stats['accuracy']:
                        acc = stats['accuracy']
                        writer.writerow(['✅ CONFRONTO CON RISULTATO REALE'])
                        writer.writerow(['Predetto:', acc['predicted_score']])
                        writer.writerow(['Reale:', acc['real_score']])
                        writer.writerow(['Match esatto:', '✅' if acc['exact_match'] else '❌'])
                        writer.writerow(['Segno corretto:', '✅' if acc['sign_correct'] else '❌'])
                        writer.writerow(['Gol casa corretti:', '✅' if acc['home_goals_correct'] else '❌'])
                        writer.writerow(['Gol trasferta corretti:', '✅' if acc['away_goals_correct'] else '❌'])
                        writer.writerow(['GG/NG corretto:', '✅' if acc['gg_ng_correct'] else '❌'])
                        writer.writerow(['U/O 2.5 corretto:', '✅' if acc['u25_correct'] else '❌'])
                        writer.writerow([])
                        writer.writerow(['📍 Posizione risultato reale nei top'])
                        writer.writerow(['Rank:', acc['real_score_rank']])
                        writer.writerow(['Occorrenze:', acc['real_score_count']])
                        writer.writerow(['Percentuale:', f"{acc['real_score_pct']}%"])
                    
                    writer.writerow([])
                    writer.writerow(['─' * 60])
                    writer.writerow([])
            
            writer.writerow([])
            writer.writerow(['=' * 100])
            writer.writerow(['END OF REPORT'])
    
    def _save_html(self, path):
        """Genera HTML interattivo con tabelle espandibili"""
        
        html_content = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔬 Deep Analysis Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header p {{
            opacity: 0.9;
            font-size: 1.1em;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .match-card {{
            background: #f8f9fa;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            border-left: 5px solid #667eea;
        }}
        
        .match-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 15px;
        }}
        
        .match-title {{
            font-size: 1.8em;
            font-weight: bold;
            color: #667eea;
        }}
        
        .match-info {{
            display: flex;
            gap: 20px;
            font-size: 0.9em;
            color: #666;
        }}
        
        .real-result {{
            background: #28a745;
            color: white;
            padding: 8px 16px;
            border-radius: 8px;
            font-weight: bold;
            font-size: 1.2em;
        }}
        
        .algo-section {{
            background: white;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
        }}
        
        .algo-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            padding: 15px;
            background: #667eea;
            color: white;
            border-radius: 8px;
            margin-bottom: 20px;
            transition: all 0.3s;
        }}
        
        .algo-header:hover {{
            background: #5568d3;
            transform: translateY(-2px);
        }}
        
        .algo-header h3 {{
            font-size: 1.3em;
        }}
        
        .toggle-icon {{
            font-size: 1.5em;
            transition: transform 0.3s;
        }}
        
        .algo-content {{
            display: none;
            animation: slideDown 0.3s ease;
        }}
        
        .algo-content.active {{
            display: block;
        }}
        
        @keyframes slideDown {{
            from {{
                opacity: 0;
                transform: translateY(-10px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }}
        
        .stat-box h4 {{
            font-size: 0.9em;
            opacity: 0.9;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .stat-box .value {{
            font-size: 2.5em;
            font-weight: bold;
        }}
        
        .stat-box .subvalue {{
            font-size: 1.1em;
            opacity: 0.8;
            margin-top: 5px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 25px;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        
        table caption {{
            font-size: 1.2em;
            font-weight: bold;
            padding: 15px;
            background: #f8f9fa;
            text-align: left;
            color: #667eea;
        }}
        
        th {{
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }}
        
        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #f0f0f0;
        }}
        
        tr:hover {{
            background: #f8f9fa;
        }}
        
        .rank-1 {{
            background: #ffd700;
            font-weight: bold;
        }}
        
        .rank-2 {{
            background: #c0c0c0;
            font-weight: bold;
        }}
        
        .rank-3 {{
            background: #cd7f32;
            font-weight: bold;
        }}
        
        .accuracy-section {{
            background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
            color: white;
            padding: 25px;
            border-radius: 12px;
            margin-top: 20px;
        }}
        
        .accuracy-section h4 {{
            font-size: 1.3em;
            margin-bottom: 15px;
        }}
        
        .accuracy-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}
        
        .accuracy-item {{
            background: rgba(255,255,255,0.2);
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}
        
        .accuracy-item .label {{
            font-size: 0.9em;
            opacity: 0.9;
            margin-bottom: 8px;
        }}
        
        .accuracy-item .result {{
            font-size: 1.5em;
            font-weight: bold;
        }}
        
        .footer {{
            background: #f8f9fa;
            padding: 30px;
            text-align: center;
            color: #666;
            border-top: 1px solid #e0e0e0;
        }}
        
        .progress-bar {{
            width: 100%;
            height: 8px;
            background: #e0e0e0;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
        }}
        
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            border-radius: 4px;
            transition: width 0.3s;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔬 Deep Analysis Report</h1>
            <p>Analisi dettagliata simulazioni Monte Carlo</p>
            <p style="opacity: 0.7; margin-top: 10px;">Generato: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</p>
        </div>
        
        <div style="background: linear-gradient(135deg, #20c997 0%, #17a2b8 100%); padding: 25px; text-align: center;">
            <a href="confidence_report.html" style="color: white; text-decoration: none; font-size: 1.3em; font-weight: bold; display: inline-block; padding: 15px 30px; background: rgba(255,255,255,0.2); border-radius: 12px; transition: all 0.3s;" onmouseover="this.style.background='rgba(255,255,255,0.3)'; this.style.transform='scale(1.05)';" onmouseout="this.style.background='rgba(255,255,255,0.2)'; this.style.transform='scale(1)';">
                📊 Vai al Report Confidence Dettagliato →
            </a>
        </div>
        
        <div class="content">
"""
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PER OGNI PARTITA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        for match_idx, match in enumerate(self.matches, 1):
            html_content += f"""
            <div class="match-card">
                <div class="match-header">
                    <div>
                        <div class="match-title">⚽ {match['home_team']} vs {match['away_team']}</div>
                        <div class="match-info">
                            <span>🏆 {match['league']}</span>
                            <span>📅 {match['date']}</span>
                        </div>
                    </div>
"""
            
            if match['real_result']:
                html_content += f"""
                    <div class="real-result">Risultato Reale: {match['real_result']}</div>
"""
            
            html_content += """
                </div>
"""
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # PER OGNI ALGORITMO
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            for algo_id, data in match['algorithms'].items():
                stats = data['stats']
                
                algo_names = {
                    1: "Statistico Puro",
                    2: "Dinamico",
                    3: "Tattico",
                    4: "Caos",
                    5: "Master"
                }
                
                algo_name = algo_names.get(algo_id, f"Algoritmo {algo_id}")
                
                html_content += f"""
                <div class="algo-section">
                    <div class="algo-header" onclick="toggleAlgo('algo_{match_idx}_{algo_id}')">
                        <h3>🔹 {algo_name}</h3>
                        <div>
                            <span style="margin-right: 15px;">{stats['total_simulations']} simulazioni</span>
                            <span class="toggle-icon" id="icon_{match_idx}_{algo_id}">▼</span>
                        </div>
                    </div>
                    
                    <div class="algo-content" id="algo_{match_idx}_{algo_id}">
"""
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # STATISTICHE PRINCIPALI (Cards)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                predicted_score = stats['top_10_scores'][0][0] if stats['top_10_scores'] else "N/A"
                predicted_count = stats['top_10_scores'][0][1] if stats['top_10_scores'] else 0
                predicted_pct = round(predicted_count / stats['total_simulations'] * 100, 1) if stats['total_simulations'] > 0 else 0
                
                html_content += f"""
                        <div class="stats-grid">
                            <div class="stat-box">
                                <h4>Risultato più probabile</h4>
                                <div class="value">{predicted_score}</div>
                                <div class="subvalue">{predicted_pct}% ({predicted_count}x)</div>
                            </div>
                            
                            <div class="stat-box">
                                <h4>Segno più probabile</h4>
                                <div class="value">{"1" if stats['sign_1']['pct'] > max(stats['sign_x']['pct'], stats['sign_2']['pct']) else ("X" if stats['sign_x']['pct'] > stats['sign_2']['pct'] else "2")}</div>
                                <div class="subvalue">{max(stats['sign_1']['pct'], stats['sign_x']['pct'], stats['sign_2']['pct'])}%</div>
                            </div>
                            
                            <div class="stat-box">
                                <h4>Media Gol</h4>
                                <div class="value">{stats['home_avg_goals']:.2f} - {stats['away_avg_goals']:.2f}</div>
                                <div class="subvalue">Casa - Trasferta</div>
                            </div>
                            
                            <div class="stat-box">
                                <h4>GG/NG</h4>
                                <div class="value">{"GG" if stats['gg']['pct'] > stats['ng']['pct'] else "NG"}</div>
                                <div class="subvalue">{max(stats['gg']['pct'], stats['ng']['pct'])}%</div>
                            </div>
                        </div>
"""
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # TOP 10 RISULTATI ESATTI
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                html_content += """
                        <table>
                            <caption>🏆 Top 10 Risultati Esatti</caption>
                            <thead>
                                <tr>
                                    <th>Rank</th>
                                    <th>Risultato</th>
                                    <th>Occorrenze</th>
                                    <th>Percentuale</th>
                                    <th>Distribuzione</th>
                                </tr>
                            </thead>
                            <tbody>
"""
                
                for rank, (score, count) in enumerate(stats['top_10_scores'], 1):
                    pct = round(count / stats['total_simulations'] * 100, 2)
                    row_class = f"rank-{rank}" if rank <= 3 else ""
                    
                    html_content += f"""
                                <tr class="{row_class}">
                                    <td><strong>{rank}</strong></td>
                                    <td><strong>{score}</strong></td>
                                    <td>{count}</td>
                                    <td>{pct}%</td>
                                    <td>
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: {pct}%"></div>
                                        </div>
                                    </td>
                                </tr>
"""
                
                html_content += """
                            </tbody>
                        </table>
"""
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # DISTRIBUZIONE GOL CASA
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                html_content += """
                        <table>
                            <caption>🏠 Distribuzione Gol Casa</caption>
                            <thead>
                                <tr>
                                    <th>Gol</th>
                                    <th>Occorrenze</th>
                                    <th>Percentuale</th>
                                    <th>Distribuzione</th>
                                </tr>
                            </thead>
                            <tbody>
"""
                
                for gol, count in sorted(stats['home_goals_distribution'].items()):
                    pct = round(count / stats['total_simulations'] * 100, 2)
                    html_content += f"""
                                <tr>
                                    <td><strong>{gol}</strong></td>
                                    <td>{count}</td>
                                    <td>{pct}%</td>
                                    <td>
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: {pct}%"></div>
                                        </div>
                                    </td>
                                </tr>
"""
                
                html_content += f"""
                            </tbody>
                        </table>
                        
                        <div style="margin-bottom: 20px;">
                            <strong>🏠 Ha segnato:</strong> {stats['home_scored']['count']}x ({stats['home_scored']['pct']}%) | 
                            <strong>Non ha segnato:</strong> {stats['home_not_scored']['count']}x ({stats['home_not_scored']['pct']}%)
                        </div>
"""
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # DISTRIBUZIONE GOL TRASFERTA
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                html_content += """
                        <table>
                            <caption>✈️ Distribuzione Gol Trasferta</caption>
                            <thead>
                                <tr>
                                    <th>Gol</th>
                                    <th>Occorrenze</th>
                                    <th>Percentuale</th>
                                    <th>Distribuzione</th>
                                </tr>
                            </thead>
                            <tbody>
"""
                
                for gol, count in sorted(stats['away_goals_distribution'].items()):
                    pct = round(count / stats['total_simulations'] * 100, 2)
                    html_content += f"""
                                <tr>
                                    <td><strong>{gol}</strong></td>
                                    <td>{count}</td>
                                    <td>{pct}%</td>
                                    <td>
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: {pct}%"></div>
                                        </div>
                                    </td>
                                </tr>
"""
                
                html_content += f"""
                            </tbody>
                        </table>
                        
                        <div style="margin-bottom: 20px;">
                            <strong>✈️ Ha segnato:</strong> {stats['away_scored']['count']}x ({stats['away_scored']['pct']}%) | 
                            <strong>Non ha segnato:</strong> {stats['away_not_scored']['count']}x ({stats['away_not_scored']['pct']}%)
                        </div>
"""
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # SEGNI 1X2
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                html_content += f"""
                        <table>
                            <caption>🎯 Segni 1X2</caption>
                            <thead>
                                <tr>
                                    <th>Segno</th>
                                    <th>Occorrenze</th>
                                    <th>Percentuale</th>
                                    <th>Distribuzione</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td><strong>1 (Casa)</strong></td>
                                    <td>{stats['sign_1']['count']}</td>
                                    <td>{stats['sign_1']['pct']}%</td>
                                    <td>
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: {stats['sign_1']['pct']}%"></div>
                                        </div>
                                    </td>
                                </tr>
                                <tr>
                                    <td><strong>X (Pareggio)</strong></td>
                                    <td>{stats['sign_x']['count']}</td>
                                    <td>{stats['sign_x']['pct']}%</td>
                                    <td>
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: {stats['sign_x']['pct']}%"></div>
                                        </div>
                                    </td>
                                </tr>
                                <tr>
                                    <td><strong>2 (Trasferta)</strong></td>
                                    <td>{stats['sign_2']['count']}</td>
                                    <td>{stats['sign_2']['pct']}%</td>
                                    <td>
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: {stats['sign_2']['pct']}%"></div>
                                        </div>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
"""
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # GOL/NOGOL
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                html_content += f"""
                        <table>
                            <caption>⚽ Gol/NoGol</caption>
                            <thead>
                                <tr>
                                    <th>Tipo</th>
                                    <th>Occorrenze</th>
                                    <th>Percentuale</th>
                                    <th>Distribuzione</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td><strong>GG (Entrambe segnano)</strong></td>
                                    <td>{stats['gg']['count']}</td>
                                    <td>{stats['gg']['pct']}%</td>
                                    <td>
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: {stats['gg']['pct']}%"></div>
                                        </div>
                                    </td>
                                </tr>
                                <tr>
                                    <td><strong>NG (Almeno una non segna)</strong></td>
                                    <td>{stats['ng']['count']}</td>
                                    <td>{stats['ng']['pct']}%</td>
                                    <td>
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: {stats['ng']['pct']}%"></div>
                                        </div>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
"""
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # UNDER/OVER
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                html_content += """
                        <table>
                            <caption>📊 Under/Over</caption>
                            <thead>
                                <tr>
                                    <th>Soglia</th>
                                    <th>Occorrenze</th>
                                    <th>Percentuale</th>
                                    <th>Distribuzione</th>
                                </tr>
                            </thead>
                            <tbody>
"""
                
                for key in ['U0.5', 'O0.5', 'U1.5', 'O1.5', 'U2.5', 'O2.5', 'U3.5', 'O3.5', 'U4.5', 'O4.5']:
                    if key in stats['under_over']:
                        val = stats['under_over'][key]
                        html_content += f"""
                                <tr>
                                    <td><strong>{key}</strong></td>
                                    <td>{val['count']}</td>
                                    <td>{val['pct']}%</td>
                                    <td>
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: {val['pct']}%"></div>
                                        </div>
                                    </td>
                                </tr>
"""
                
                html_content += """
                            </tbody>
                        </table>
"""


                html_content += f"""
                        <div style="background: linear-gradient(135deg, #20c997 0%, #17a2b8 100%); color: white; padding: 25px; border-radius: 12px; margin: 20px 0;">
                            <h4 style="margin-bottom: 15px; font-size: 1.3em;">📊 Confidence Analysis (Deviazione Standard)</h4>
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                                <div style="background: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px; text-align: center;">
                                    <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 8px;">Gol Casa</div>
                                    <div style="font-size: 1.8em; font-weight: bold;">{stats['confidence']['home_confidence']:.1f}%</div>
                                    <div style="font-size: 0.9em; opacity: 0.8; margin-top: 5px;">Std Dev: {stats['confidence']['home_std']:.3f}</div>
                                </div>
                                <div style="background: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px; text-align: center;">
                                    <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 8px;">Gol Ospite</div>
                                    <div style="font-size: 1.8em; font-weight: bold;">{stats['confidence']['away_confidence']:.1f}%</div>
                                    <div style="font-size: 0.9em; opacity: 0.8; margin-top: 5px;">Std Dev: {stats['confidence']['away_std']:.3f}</div>
                                </div>
                                <div style="background: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px; text-align: center;">
                                    <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 8px;">Totale Gol</div>
                                    <div style="font-size: 1.8em; font-weight: bold;">{stats['confidence']['total_confidence']:.1f}%</div>
                                    <div style="font-size: 0.9em; opacity: 0.8; margin-top: 5px;">Std Dev: {stats['confidence']['total_std']:.3f}</div>
                                </div>
                                <div style="background: rgba(255,255,255,0.3); padding: 15px; border-radius: 8px; text-align: center; border: 2px solid rgba(255,255,255,0.5);">
                                    <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 8px;">🎯 CONFIDENCE GLOBALE</div>
                                    <div style="font-size: 2.2em; font-weight: bold;">{stats['confidence']['global_confidence']:.1f}%</div>
                                </div>
                            </div>
                            <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid rgba(255,255,255,0.3); font-size: 0.9em; opacity: 0.9;">
                                💡 Più alta la confidence, più affidabile è la previsione | Più bassa la Std Dev, più coerenti sono i risultati
                            </div>
                        </div>
"""
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # ACCURACY (se disponibile)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                if stats['accuracy']:
                    acc = stats['accuracy']
                    html_content += f"""
                        <div class="accuracy-section">
                            <h4>✅ Confronto con Risultato Reale</h4>
                            
                            <div style="margin-bottom: 20px;">
                                <strong>Predetto:</strong> {acc['predicted_score']} | 
                                <strong>Reale:</strong> {acc['real_score']}
                            </div>
                            
                            <div class="accuracy-grid">
                                <div class="accuracy-item">
                                    <div class="label">Match Esatto</div>
                                    <div class="result">{'✅' if acc['exact_match'] else '❌'}</div>
                                </div>
                                
                                <div class="accuracy-item">
                                    <div class="label">Segno 1X2</div>
                                    <div class="result">{'✅' if acc['sign_correct'] else '❌'}</div>
                                </div>
                                
                                <div class="accuracy-item">
                                    <div class="label">Gol Casa</div>
                                    <div class="result">{'✅' if acc['home_goals_correct'] else '❌'}</div>
                                </div>
                                
                                <div class="accuracy-item">
                                    <div class="label">Gol Trasferta</div>
                                    <div class="result">{'✅' if acc['away_goals_correct'] else '❌'}</div>
                                </div>
                                
                                <div class="accuracy-item">
                                    <div class="label">GG/NG</div>
                                    <div class="result">{'✅' if acc['gg_ng_correct'] else '❌'}</div>
                                </div>
                                
                                <div class="accuracy-item">
                                    <div class="label">Under/Over 2.5</div>
                                    <div class="result">{'✅' if acc['u25_correct'] else '❌'}</div>
                                </div>
                            </div>
                            
                            <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.3);">
                                <strong>📍 Posizione risultato reale:</strong><br>
                                Rank #{acc['real_score_rank']} | 
                                {acc['real_score_count']} occorrenze ({acc['real_score_pct']}%)
                            </div>
                        </div>
"""
                
                html_content += """
                    </div>
                </div>
"""
            
            html_content += """
            </div>
"""
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FOOTER
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        html_content += f"""
        </div>
        
        <div class="footer">
            <p><strong>Deep Analysis Report</strong></p>
            <p>Generato il {datetime.now().strftime("%d/%m/%Y alle %H:%M:%S")}</p>
            <p style="margin-top: 10px; opacity: 0.7;">📊 {len(self.matches)} partite analizzate</p>
        </div>
    </div>
    
    <script>
        function toggleAlgo(id) {{
            const content = document.getElementById(id);
            const icon = document.getElementById('icon_' + id.split('_')[1] + '_' + id.split('_')[2]);
            
            if (content.classList.contains('active')) {{
                content.classList.remove('active');
                icon.textContent = '▼';
            }} else {{
                content.classList.add('active');
                icon.textContent = '▲';
            }}
        }}
    </script>
</body>
</html>
"""
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html_content)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🧪 ESEMPIO DI UTILIZZO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    print("🔬 Deep Analysis Module - Test")
    print("="*60)
    
    # Crea analyzer
    analyzer = DeepAnalyzer()
    
    # Simula una partita
    print("\n📊 Simulazione partita: Roma vs Como")
    analyzer.start_match(
        home_team="Roma",
        away_team="Como",
        real_result="2-0",
        league="Serie A",
        date_str="2024-12-16"
    )
    
    # Simula 500 cicli per algoritmo 2
    print("⏳ Simulazione 500 cicli (Algoritmo 2 - Dinamico)...")
    import random
    for i in range(500):
        # Simula risultati random (sostituire con i tuoi veri dati)
        gh = random.choices([0,1,2,3], weights=[20, 40, 30, 10])[0]
        ga = random.choices([0,1,2], weights=[50, 35, 15])[0]
        analyzer.add_result(algo_id=2, home_goals=gh, away_goals=ga)
    
    # Finalizza
    analyzer.end_match()
    
    # Salva report
    print("\n💾 Salvataggio report...")
    analyzer.save_report(
        csv_path="test_deep_analysis.csv",
        html_path="test_deep_analysis.html",
        json_path="test_deep_analysis.json"
    )
    
    print("\n✅ Test completato!")
    print("📂 File generati:")
    print("   - test_deep_analysis.csv")
    print("   - test_deep_analysis.html  (Apri nel browser!)")
    print("   - test_deep_analysis.json")