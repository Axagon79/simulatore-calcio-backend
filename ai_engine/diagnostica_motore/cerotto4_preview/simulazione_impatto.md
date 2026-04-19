# Cerotto 4 — Simulazione impatto azioni

Applicazione virtuale delle azioni `SCARTA` / `Dimezza` sul dataset storico.

Regole:
- Pronostico in almeno 1 combo SCARTA → PL = 0 (non giocato)
- Pronostico SOLO in combo Dimezza → PL / 2
- Pronostico in nessuna combo → PL invariato

Se un pronostico è in entrambe SCARTA e Dimezza, SCARTA prevale.

## Risultato simulazione

| Metrica | Originale | Simulato | Delta |
| --- | ---: | ---: | ---: |
| Volume | 1501 | 1428 attivi (73 scartati) | -73 |
| Volume pesato (dimezzati = 0.5) | 1501.0 | 1408.5 | -92.5 |
| HR | 59.09% | 60.78% (solo non scartati) | +1.69pp |
| PL totale | +135.73u | +82.86u | -52.88u |
| ROI per unità | +9.04% | +5.88% | — |

## Dettaglio per gruppo azione

| Gruppo | N | PL originale | PL simulato | Δ |
| --- | ---: | ---: | ---: | ---: |
| Pronostici in SCARTA | 73 | -54.24u | 0.00u | +54.24u |
| Pronostici solo in Dimezza | 39 | +214.23u | +107.12u | -107.12u |
| Pronostici intatti | 1389 | -24.26u | -24.26u | 0.00u |

## Contributo per combo (PL originale dei pronostici unicamente coperti da questa combo)

| ID | N esclusivi | PL originale esclusivi |
| --- | ---: | ---: |
| C1 | 0 | +0.00u |
| C2 | 5 | +2.80u |
| C3 | 2 | +20.12u |
| C4 | 0 | +0.00u |
| C5 | 0 | +0.00u |
| C6 | 0 | +0.00u |
| C7 | 3 | +24.85u |
| C8 | 0 | +0.00u |
| C9 | 1 | -3.00u |
| C10 | 2 | +1.50u |

## Warning metodologico

Questa simulazione è post-hoc sullo stesso dataset che ha generato le combo tossiche (nel report originale). Quindi l'impatto simulato è per costruzione favorevole: stiamo "togliendo" sullo stesso set dove abbiamo identificato l'overfit. Un test out-of-sample su dati futuri potrebbe dare risultati diversi. Valutare prima di applicare in produzione.