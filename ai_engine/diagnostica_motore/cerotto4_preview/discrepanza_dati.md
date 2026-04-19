# Discrepanza dati: "AR def B = +4u" vs "frontend AR = +180u"

Verifica della discrepanza segnalata prima di procedere con Cerotto 4.

## Risposta rapida

**Il frontend ha ragione.** I miei numeri del Cerotto 4 preview erano errati per
tre motivi sommati:

1. Ho **dedupato** il dataset (priorità MIXER>ELITE>AR>PRONOSTICI) — il backend NO.
2. Ho reso le scatole **mutualmente esclusive** — nel backend non lo sono.
3. Ho calcolato il PL a **stake 1u** — il backend usa lo **stake reale**.

Risultato: AR def B frontend = **+246.62u** (yield +40.6%), mentre io scrivevo ~+4u.
Differenza del ~98%.

## Numeri affiancati (finestra 2026-02-19 → 2026-04-18)

### Metodo 1 — Frontend (fonte di verità, da `pl_storico`)

| Sezione | bets | wins | HR | PL (u) | staked (u) | YIELD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| tutti | 1514 | 887 | 58.6% | **+256.23** | 7848 | **+3.3%** |
| pronostici | 1372 | 832 | 60.6% | +9.61 | 7240 | +0.1% |
| elite | 235 | 153 | 65.1% | +40.46 | 1656 | +2.4% |
| **alto_rendimento** | **142** | **55** | **38.7%** | **+246.62** | **608** | **+40.6%** |

Il tuo `+180.28u` mostrato nello screenshot è il PL mese in corso, non la
finestra 19/02-18/04. Quello che qui risulta **+246u su 58 giorni** è
coerente con una media mensile ~+120-180u a seconda della distribuzione
giornaliera. I dati sono **genuini**, non c'è un errore nel frontend.

### Metodo 2 — Il mio calcolo sbagliato (Cerotto 4 preview)

| Scatola | N | HR | PL 1u | ROI/unit |
| --- | ---: | ---: | ---: | ---: |
| MIXER | 569 | 59.93% | +16.68u | +2.93% |
| ELITE | 60 | 60.00% | -7.68u | -12.81% |
| ALTO_RENDIMENTO | 73 | 36.99% | +5.57u | +7.63% |
| PRONOSTICI | 799 | 60.45% | -4.39u | -0.55% |

Totale dedupato: 1501 righe. 1514 bets backend - 1501 dedupati = 13 differenza
(1501 è dopo dedup, 1514 è senza dedup). Confermo che il dedup di per sé
toglie solo una manciata di righe; **il grosso della discrepanza è lo
stake**.

### Metodo 3 — Stake pesato ma su dedupato (per isolare gli effetti)

| Scatola | N | HR | PL pesato | staked | YIELD |
| --- | ---: | ---: | ---: | ---: | ---: |
| MIXER | 569 | 59.93% | **+210.19u** | 3171 | +6.6% |
| ELITE | 60 | 60.00% | -25.34u | 476 | -5.3% |
| ALTO_RENDIMENTO | 73 | 36.99% | +4.00u | 334 | +1.2% |
| PRONOSTICI | 799 | 60.45% | -53.12u | 3874 | -1.4% |

**Confronto con frontend**: AR Metodo 3 fa +4u vs frontend +246u. Qui lo stake
è pesato ma le scatole restano esclusive. La differenza si spiega perché nel
backend:

- Un pronostico `mixer=True AND elite=True AND quota≥2.51` viene contato in
  `tutti`, `elite`, e `alto_rendimento` tre volte, con lo stesso stake e lo
  stesso esito. Se vincente, contribuisce +stake×(q-1) ad ognuna di queste.
- I pronostici più belli (alta quota + mixer + elite) finiscono nella mia
  categoria "MIXER" dedupata, ma nel backend contribuiscono anche a AR.

## Cosa fa esattamente il backend (`popola_pl_storico.py::calcola_pl_giorno`)

```python
# linee 163-192 semplificate:
soglia = 2.00 if tipo == 'DOPPIA_CHANCE' else 2.51
is_alto_rend = tipo == 'RISULTATO_ESATTO' or quota >= soglia
is_pronostici = not is_alto_rend and tipo != 'RISULTATO_ESATTO'

# CONTRIBUISCE A TUTTI (sempre)
sez['tutti']['bets'] += 1
sez['tutti']['staked'] += stake
sez['tutti']['pl'] += profit  # profit = (quota-1)*stake se vinto, -stake se perso

# CONTRIBUISCE A PRONOSTICI (se quota sotto soglia e non RE)
if is_pronostici:
    sez['pronostici'] += ...

# CONTRIBUISCE A ELITE (se flag elite=True)
if p.get('elite'):
    sez['elite'] += ...

# CONTRIBUISCE A ALTO_RENDIMENTO (se quota≥soglia o RE)
if is_alto_rend:
    sez['alto_rendimento'] += ...
```

Differenze rispetto al mio calcolo:

| Aspetto | Backend produzione | Mia query |
| --- | --- | --- |
| Dedup (date,home,away,tipo,pronostico) | **no** | sì |
| Scatole mutualmente esclusive | **no** | sì |
| `alto_rendimento` include `RISULTATO_ESATTO` | **sì** | no |
| PL pesato per stake | **sì** | no (a 1u) |
| ROI = PL / staked | **sì** | no (PL / N) |
| Considera scatole diverse come copie dello stesso pronostico | **sì** | no |

## Qual è la risposta corretta?

Dipende dalla domanda.

- Per **comunicazione al cliente (dashboard)**: il metodo backend è quello giusto.
  Riflette l'investimento reale (stake) e l'esperienza percepita: un pronostico
  che l'utente vede in 2 scatole "gli dà soddisfazione" due volte. **+246u su AR
  è un dato reale e difendibile**.
- Per **valutazione del motore dal punto di vista predittivo**: il dedup a 1u ha
  senso per isolare il segnale della classificazione senza contaminarlo da
  decisioni di money management (stake) e senza doppio-conteggio. In questa
  lettura il ROI del motore è molto più modesto.

**Nessuna delle due è "sbagliata" — misurano cose diverse.**

## Implicazioni per Cerotto 4

Il mio report del Cerotto 4 preview (`combo_verificate.md` e
`impatto_alto_rendimento.md`) usava il mio metodo: dataset dedupato, PL a 1u.

**Questo produceva numeri non comparabili con la dashboard del frontend.**

Quando nell'analisi incrociata scrivevo "AR def B prima: +4u, dopo: +76u,
delta +72u", stavo sottostimando brutalmente l'impact reale. Il **delta vero**
sul AR frontend potrebbe essere molto diverso (probabilmente più grande in
valore assoluto, visto che gli stake sono maggiori).

## Cosa serve prima di procedere col Cerotto 4

Rifare il calcolo del Cerotto 4 usando **la stessa formula del backend** (no
dedup + scatole non esclusive + stake pesato + include RE in AR). Solo così
posso dirti: "se applichi il Cerotto 4, AR frontend passa da +246u a X u".
Numeri confrontabili con quelli che l'utente vede.

Fermo qui come richiesto. Attendo tuo ok per rifare l'analisi impatto con la
formula backend.

## File di supporto

- `verifica_discrepanza.py` — script che ha prodotto i 3 metodi confrontati.
- `impatto_alto_rendimento.md` — report precedente, **da considerare non più
  valido** per AR def B (ma le stats globali e la classificazione delle combo
  tossiche/falsi allarmi restano valide perché usate su metodi coerenti
  internamente).
- `combo_verificate.md` — vale ancora: la classificazione di falsi allarmi vs
  tossiche è robusta (ROI a 1u o ROI pesato non cambia il segno del PL per
  combo piccole).
