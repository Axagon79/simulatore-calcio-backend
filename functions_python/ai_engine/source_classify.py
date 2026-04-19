"""Classificazione del campo `source` dei pronostici in gruppi di calibrazione.

Usato da:
- `stake_kelly.py` per lookup nella tabella di calibrazione
- Diagnostiche (stessa logica)

Gruppi mutuamente esclusivi:
- 'A'           : source == 'A' puro
- 'S'           : source == 'S' puro
- 'C'           : source == 'C' puro
- 'A+S'         : source == 'A+S' o varianti che iniziano con 'A+S_'
- 'C-derivati'  : source che inizia con 'C_' o 'MC_'
- 'Altro'       : resto (fallback, source null, o stringhe non riconosciute)
"""
from __future__ import annotations


GROUP_A = 'A'
GROUP_S = 'S'
GROUP_C = 'C'
GROUP_AS = 'A+S'
GROUP_C_DERIVATI = 'C-derivati'
GROUP_ALTRO = 'Altro'

ALL_GROUPS = [GROUP_A, GROUP_S, GROUP_C, GROUP_AS, GROUP_C_DERIVATI, GROUP_ALTRO]


def classify(source) -> str:
    """Mappa la stringa `source` di un pronostico al gruppo di calibrazione.

    Accetta None/NaN e restituisce 'Altro'. Non ha dipendenze esterne.
    """
    if source is None:
        return GROUP_ALTRO
    try:
        s = str(source)
    except Exception:
        return GROUP_ALTRO
    if s == '' or s.lower() == 'nan':
        return GROUP_ALTRO
    if s == 'A':
        return GROUP_A
    if s == 'S':
        return GROUP_S
    if s == 'C':
        return GROUP_C
    if s == 'A+S' or s.startswith('A+S_'):
        return GROUP_AS
    if s.startswith('C_') or s.startswith('MC_'):
        return GROUP_C_DERIVATI
    return GROUP_ALTRO
