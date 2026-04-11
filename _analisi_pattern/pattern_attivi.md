# Pattern Attivi — Riepilogo Completo

Ultimo aggiornamento: 2026-04-11
File sorgente: `tag_elite.py` (Elite) + `orchestrate_experts.py` (Diamante)

---

## PATTERN ELITE (16) — tag_elite.py

Taggano `elite: true` sui pronostici GIA emessi dall'orchestratore.
Scoperti con `elite_pattern_analysis.py`.

### Originali (1-8) — 22/03/2026

| # | Tipo | Condizioni | HR storico | N |
|---|------|-----------|------------|---|
| P1 | SEGNO | quota 1.50-1.79 + stelle 3.0-3.5 | ~78% | 37 |
| P2 | SEGNO | quota 1.50-1.79 + conf 50-59 | ~74% | 38 |
| P3 | DOPPIA_CHANCE | source C_screm + quota 2.00-2.49 | ~81% | 16 |
| P4 | GOL | quota 1.30-1.49 + conf 70-79 | ~76% | 97 |
| P5 | DOPPIA_CHANCE | quota 2.00-2.49 | ~73% | 22 |
| P6 | SEGNO | conf >= 80 | ~77% | 35 |
| P7 | DOPPIA_CHANCE | quota 1.30-1.49 + conf 60-69 | 80.6% | 31 |
| P8 | GOL | source A+S + quota 1.30-1.49 | ~75% | 72 |

### Nuovi (9-16) — 22/03/2026

| # | Tipo | Condizioni | HR storico | N |
|---|------|-----------|------------|---|
| P9 | DOPPIA_CHANCE | quota 1.40-1.49 + conf >= 60 | 92.6% | 27 |
| P10 | GOL | MG 2-4 (qualsiasi) | 88.2% | 17 |
| P11 | GOL | quota 1.30-1.39 + conf >= 70 | 86.4% | 22 |
| P12 | DOPPIA_CHANCE | quota 1.40-1.49 + stelle >= 3.0 | 85.3% | 34 |
| P13 | GOL | quota 1.30-1.39 + source A+S | 85.2% | 27 |
| P14 | GOL | quota 1.50-1.59 + source C_screm | 84.2% | 19 |
| P15 | SEGNO | quota 1.80-1.99 + conf >= 80 | 100% | 8 |
| P16 | DOPPIA_CHANCE | quota 1.30-1.49 + conf 70-79 | 81.8% | 11 |

---

## PATTERN DIAMANTE (8) — orchestrate_experts.py

Recuperano pronostici SCARTATI (non emessi dai filtri normali).
Si attivano SOLO su mercati non coperti (GOL o SEGNO mancante).
Scoperti con `explore_bizarre_patterns.py`, implementati il 29/03/2026.
Flag: `diamond: true`

| # | Tipo | Pronostico | Sistema | Condizioni | HR storico |
|---|------|-----------|---------|-----------|------------|
| P1/2 | GOL | Under 3.5 | A o S | conf >= 60, quota >= 1.35 | 88-90% |
| P4 | GOL | Over 1.5 | A | conf >= 65, quota >= 1.35 | 89% |
| P5 | GOL | Over 1.5 | C | conf >= 75, spread <= 1.0 + q >= 1.45 OPPURE conf >= 80 + q >= 1.50 | 75-85% |
| P10 | SEGNO | 1 | C | conf 70-79, quota >= 1.50 | 69% |
| P14 | GOL | Goal/GG | C | conf >= 65, quota >= 1.35 | 83% |
| P18 | GOL | Over 2.5 | A+S+C (3/3) | avg conf >= 65, q >= 1.35, 3 livelli gerarchici | 70-88% |
| P23 | GOL | Under 3.5 | A+C concordano | entrambi conf >= 65, q >= 1.35 | 82% |
| P24 | GOL | Under 3.5 | A+S concordano | entrambi conf >= 65, q >= 1.35 | 85% |

---

## NOTE

- I pattern Elite taggano pronostici gia emessi -> mostrati nella sezione "Elite" del frontend
- I pattern Diamante RECUPERANO pronostici scartati -> li aggiungono alla produzione
- HR storici calcolati al 22/03/2026 (Elite) e 29/03/2026 (Diamante) — DA RICALCOLARE
- Sovrapposizioni: P3 e P5 Elite (DC q2.00-2.49) sono lo stesso pattern con/senza source
- Sovrapposizioni: P9 e P12 Elite (DC q1.40-1.49) si sovrappongono quasi completamente
- P15 Elite ha campione troppo piccolo (N=8), da monitorare
