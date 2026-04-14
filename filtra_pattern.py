"""
Filtra i 188 pattern hybrid togliendo:
- I 14 genitori esatti
- Qualsiasi superset di un genitore (contiene tutte le condizioni di un genitore)
"""

# I 14 pattern genitori come set di condizioni
genitori = [
    {'conf50-59', 'src_C_screm'},           # P1
    {'conf50-59', 'q1.50-1.79'},            # P2
    {'pron_Goal', 'q1.30-1.49'},            # P3
    {'conf60-69', 'q1.30-1.49'},            # P4
    {'route_union'},                         # P5
    {'pron_1', 'st3.6-3.9'},               # P6
    {'conf70-79', 'q1.50-1.79'},            # P7
    {'src_C_screm', 'route_scrematura'},    # P8
    {'src_C', 'st3.6-3.9'},                # P9
    {'edge20-50', 'q1.50-1.79'},           # P10
    {'conf60-69', 'edge50+'},              # P11
    {'conf60-69', 'src_C'},                # P12
    {'q3.00-3.99', 'route_single'},        # P13
    {'edge50+', 'tipo_SEGNO'},             # P14
]

# Tutti i 188 pattern (name, v, p, hr, n, pl)
patterns = [
    ('conf60-69 + edge50+', 8, 2, 80.0, 10, 97.29),
    ('conf60-69 + src_C + edge50+', 7, 2, 77.8, 9, 95.19),
    ('conf60-69 + src_C + route_single', 23, 12, 65.7, 35, 92.29),
    ('conf60-69 + tipo_SEGNO + edge50+', 6, 2, 75.0, 8, 91.14),
    ('conf60-69 + src_C + tipo_SEGNO + edge50+', 6, 2, 75.0, 8, 91.14),
    ('conf50-59 + src_C_screm', 32, 9, 78.0, 41, 86.35),
    ('conf50-59 + route_scrematura', 32, 9, 78.0, 41, 86.35),
    ('conf50-59 + src_C_screm + route_scrematura', 32, 9, 78.0, 41, 86.35),
    ('src_C + pron_1 + edge20-50', 21, 10, 67.7, 31, 79.13),
    ('route_single + pron_1 + edge20-50', 21, 10, 67.7, 31, 79.13),
    ('src_C + route_single + pron_1 + edge20-50', 21, 10, 67.7, 31, 79.13),
    ('src_C + tipo_SEGNO + pron_1 + edge20-50', 21, 10, 67.7, 31, 79.13),
    ('route_single + tipo_SEGNO + pron_1 + edge20-50', 21, 10, 67.7, 31, 79.13),
    ('q1.50-1.79 + tipo_SEGNO + edge20-50', 16, 4, 80.0, 20, 76.67),
    ('q1.50-1.79 + src_C + tipo_SEGNO + edge20-50', 16, 4, 80.0, 20, 76.67),
    ('q1.50-1.79 + route_single + tipo_SEGNO + edge20-50', 16, 4, 80.0, 20, 76.67),
    ('q1.50-1.79 + src_C + pron_1', 31, 16, 66.0, 47, 72.62),
    ('q1.50-1.79 + route_single + pron_1', 31, 16, 66.0, 47, 72.62),
    ('q1.50-1.79 + src_C + route_single + pron_1', 31, 16, 66.0, 47, 72.62),
    ('q1.50-1.79 + src_C + tipo_SEGNO + pron_1', 31, 16, 66.0, 47, 72.62),
    ('q1.50-1.79 + route_single + tipo_SEGNO + pron_1', 31, 16, 66.0, 47, 72.62),
    ('q1.50-1.79 + route_single + edge20-50', 16, 5, 76.2, 21, 69.67),
    ('q1.50-1.79 + src_C + route_single + edge20-50', 16, 5, 76.2, 21, 69.67),
    ('q1.50-1.79 + src_C + edge20-50', 20, 9, 69.0, 29, 67.27),
    ('conf60-69 + st3.6-3.9', 46, 24, 65.7, 70, 64.52),
    ('conf60-69 + src_C + st3.6-3.9', 32, 17, 65.3, 49, 63.57),
    ('conf60-69 + route_single + st3.6-3.9', 13, 5, 72.2, 18, 61.21),
    ('conf60-69 + src_C + route_single + st3.6-3.9', 13, 5, 72.2, 18, 61.21),
    ('q1.50-1.79 + pron_1 + edge20-50', 12, 2, 85.7, 14, 60.35),
    ('q1.50-1.79 + src_C + pron_1 + edge20-50', 12, 2, 85.7, 14, 60.35),
    ('q1.50-1.79 + route_single + pron_1 + edge20-50', 12, 2, 85.7, 14, 60.35),
    ('q1.50-1.79 + tipo_SEGNO + pron_1 + edge20-50', 12, 2, 85.7, 14, 60.35),
    ('conf60-69 + src_C + pron_1', 12, 3, 80.0, 15, 57.07),
    ('conf60-69 + route_single + pron_1', 12, 3, 80.0, 15, 57.07),
    ('conf60-69 + src_C + route_single + pron_1', 12, 3, 80.0, 15, 57.07),
    ('conf60-69 + src_C + tipo_SEGNO + pron_1', 12, 3, 80.0, 15, 57.07),
    ('conf60-69 + route_single + tipo_SEGNO + pron_1', 12, 3, 80.0, 15, 57.07),
    ('conf60-69 + tipo_SEGNO + st3.6-3.9', 10, 5, 66.7, 15, 53.86),
    ('conf60-69 + src_C + tipo_SEGNO + st3.6-3.9', 10, 5, 66.7, 15, 53.86),
    ('conf60-69 + route_single + tipo_SEGNO + st3.6-3.9', 10, 5, 66.7, 15, 53.86),
    ('conf70-79 + pron_1 + edge20-50', 9, 2, 81.8, 11, 52.11),
    ('conf70-79 + tipo_SEGNO + pron_1 + edge20-50', 9, 2, 81.8, 11, 52.11),
    ('conf50-59 + q1.50-1.79 + src_C_screm', 19, 4, 82.6, 23, 51.51),
    ('conf50-59 + q1.50-1.79 + route_scrematura', 19, 4, 82.6, 23, 51.51),
    ('conf50-59 + q1.50-1.79 + src_C_screm + route_scrematura', 19, 4, 82.6, 23, 51.51),
    ('conf70-79 + tipo_SEGNO + edge20-50', 11, 4, 73.3, 15, 49.23),
    ('conf70-79 + edge20-50', 20, 10, 66.7, 30, 47.16),
    ('q1.50-1.79 + src_C + pron_1 + st3.6-3.9', 10, 2, 83.3, 12, 43.28),
    ('q1.50-1.79 + route_single + pron_1 + st3.6-3.9', 10, 2, 83.3, 12, 43.28),
    ('src_C + pron_1 + st3.6-3.9', 14, 6, 70.0, 20, 42.98),
    ('route_single + pron_1 + st3.6-3.9', 14, 6, 70.0, 20, 42.98),
    ('src_C + route_single + pron_1 + st3.6-3.9', 14, 6, 70.0, 20, 42.98),
    ('src_C + tipo_SEGNO + pron_1 + st3.6-3.9', 14, 6, 70.0, 20, 42.98),
    ('route_single + tipo_SEGNO + pron_1 + st3.6-3.9', 14, 6, 70.0, 20, 42.98),
    ('pron_1 + st3.6-3.9', 18, 9, 66.7, 27, 42.60),
    ('tipo_SEGNO + pron_1 + st3.6-3.9', 18, 9, 66.7, 27, 42.60),
    ('q1.50-1.79 + src_C_screm + tipo_GOL', 18, 5, 78.3, 23, 42.43),
    ('conf70-79 + src_C + pron_1 + edge20-50', 8, 2, 80.0, 10, 40.51),
    ('conf70-79 + route_single + pron_1 + edge20-50', 8, 2, 80.0, 10, 40.51),
    ('q1.50-1.79 + route_scrematura + tipo_GOL', 17, 5, 77.3, 22, 39.47),
    ('q1.50-1.79 + src_C_screm + route_scrematura + tipo_GOL', 17, 5, 77.3, 22, 39.47),
    ('conf50-59 + q1.50-1.79 + tipo_GOL', 14, 4, 77.8, 18, 38.65),
    ('conf70-79 + pron_1', 15, 8, 65.2, 23, 38.25),
    ('conf70-79 + tipo_SEGNO + pron_1', 15, 8, 65.2, 23, 38.25),
    ('conf60-69 + pron_1', 13, 6, 68.4, 19, 37.87),
    ('conf60-69 + tipo_SEGNO + pron_1', 13, 6, 68.4, 19, 37.87),
    ('conf70-79 + src_C + tipo_SEGNO + edge20-50', 10, 4, 71.4, 14, 37.63),
    ('conf70-79 + route_single + tipo_SEGNO + edge20-50', 10, 4, 71.4, 14, 37.63),
    ('q1.30-1.49 + st3.6-3.9', 29, 7, 80.6, 36, 36.92),
    ('conf70-79 + tipo_SEGNO + st3.6-3.9 + edge20-50', 8, 3, 72.7, 11, 36.08),
    ('conf70-79 + pron_1 + st3.6-3.9 + edge20-50', 7, 2, 77.8, 9, 36.08),
    ('conf70-79 + route_single + edge20-50', 11, 5, 68.8, 16, 35.13),
    ('conf70-79 + src_C + route_single + edge20-50', 11, 5, 68.8, 16, 35.13),
    ('tipo_SEGNO + st3.6-3.9 + edge20-50', 10, 5, 66.7, 15, 34.63),
    ('conf70-79 + src_C + pron_1', 10, 4, 71.4, 14, 34.50),
    ('conf70-79 + route_single + pron_1', 10, 4, 71.4, 14, 34.50),
    ('conf70-79 + src_C + route_single + pron_1', 10, 4, 71.4, 14, 34.50),
    ('conf70-79 + src_C + tipo_SEGNO + pron_1', 10, 4, 71.4, 14, 34.50),
    ('conf70-79 + route_single + tipo_SEGNO + pron_1', 10, 4, 71.4, 14, 34.50),
    ('conf50-59 + q1.50-1.79 + src_C_screm + tipo_GOL', 9, 1, 90.0, 10, 32.45),
    ('conf50-59 + q1.50-1.79 + route_scrematura + tipo_GOL', 9, 1, 90.0, 10, 32.45),
    ('q1.50-1.79 + pron_1 + st3.6-3.9', 13, 5, 72.2, 18, 31.30),
    ('q1.50-1.79 + tipo_SEGNO + pron_1 + st3.6-3.9', 13, 5, 72.2, 18, 31.30),
    ('conf60-69 + q1.50-1.79 + pron_1', 7, 1, 87.5, 8, 30.33),
    ('conf60-69 + q1.50-1.79 + tipo_SEGNO + pron_1', 7, 1, 87.5, 8, 30.33),
    ('q1.50-1.79 + src_C + tipo_SEGNO + st3.6-3.9', 11, 4, 73.3, 15, 30.24),
    ('q1.50-1.79 + route_single + tipo_SEGNO + st3.6-3.9', 11, 4, 73.3, 15, 30.24),
    ('q1.30-1.49 + tipo_GOL + st3.6-3.9', 25, 6, 80.6, 31, 30.21),
    ('conf60-69 + q1.30-1.49', 49, 18, 73.1, 67, 29.28),
    ('conf60-69 + q1.50-1.79 + src_C + route_single', 8, 2, 80.0, 10, 28.59),
    ('conf60-69 + q1.50-1.79 + src_C + tipo_SEGNO', 8, 2, 80.0, 10, 28.59),
    ('conf60-69 + q1.50-1.79 + route_single + tipo_SEGNO', 8, 2, 80.0, 10, 28.59),
    ('pron_1 + st3.6-3.9 + edge20-50', 7, 3, 70.0, 10, 27.08),
    ('tipo_SEGNO + pron_1 + st3.6-3.9 + edge20-50', 7, 3, 70.0, 10, 27.08),
    ('conf60-69 + q1.50-1.79 + route_single', 10, 3, 76.9, 13, 25.19),
    ('conf60-69 + pron_1 + st3.6-3.9', 6, 2, 75.0, 8, 24.51),
    ('conf60-69 + src_C + pron_1 + st3.6-3.9', 6, 2, 75.0, 8, 24.51),
    ('conf60-69 + route_single + pron_1 + st3.6-3.9', 6, 2, 75.0, 8, 24.51),
    ('conf60-69 + tipo_SEGNO + pron_1 + st3.6-3.9', 6, 2, 75.0, 8, 24.51),
    ('q1.30-1.49 + pron_Goal', 24, 7, 77.4, 31, 24.19),
    ('q1.30-1.49 + tipo_GOL + pron_Goal', 24, 7, 77.4, 31, 24.19),
    ('q1.30-1.49 + src_C', 17, 3, 85.0, 20, 24.15),
    ('q1.30-1.49 + src_C + tipo_GOL', 17, 3, 85.0, 20, 24.15),
    ('q1.30-1.49 + src_C + pron_Goal', 17, 3, 85.0, 20, 24.15),
    ('q1.30-1.49 + src_C + tipo_GOL + pron_Goal', 17, 3, 85.0, 20, 24.15),
    ('q1.50-1.79 + src_C + route_single + st3.6-3.9', 11, 5, 68.8, 16, 23.24),
    ('conf50-59 + src_C_screm + tipo_GOL', 14, 4, 77.8, 18, 22.99),
    ('conf50-59 + route_scrematura + tipo_GOL', 14, 4, 77.8, 18, 22.99),
    ('conf50-59 + src_C_screm + route_scrematura + tipo_GOL', 14, 4, 77.8, 18, 22.99),
    ('q1.30-1.49 + src_C + st3.6-3.9', 13, 2, 86.7, 15, 22.85),
    ('q1.30-1.49 + pron_Goal + st3.6-3.9', 13, 2, 86.7, 15, 22.85),
    ('q1.30-1.49 + src_C + tipo_GOL + st3.6-3.9', 13, 2, 86.7, 15, 22.85),
    ('q1.30-1.49 + src_C + pron_Goal + st3.6-3.9', 13, 2, 86.7, 15, 22.85),
    ('q1.30-1.49 + tipo_GOL + pron_Goal + st3.6-3.9', 13, 2, 86.7, 15, 22.85),
    ('conf70-79 + q1.50-1.79 + src_C + tipo_SEGNO', 8, 3, 72.7, 11, 21.42),
    ('conf70-79 + q1.50-1.79 + route_single + tipo_SEGNO', 8, 3, 72.7, 11, 21.42),
    ('conf60-69 + q1.50-1.79 + src_C + st3.6-3.9', 15, 7, 68.2, 22, 20.62),
    ('conf60-69 + q1.50-1.79 + tipo_SEGNO', 8, 3, 72.7, 11, 19.59),
    ('conf70-79 + q1.50-1.79 + src_C + pron_1', 6, 2, 75.0, 8, 19.34),
    ('conf70-79 + q1.50-1.79 + route_single + pron_1', 6, 2, 75.0, 8, 19.34),
    ('conf70-79 + src_C + pron_1 + st3.6-3.9', 8, 4, 66.7, 12, 18.47),
    ('conf70-79 + route_single + pron_1 + st3.6-3.9', 8, 4, 66.7, 12, 18.47),
    ('q1.50-1.79 + tipo_SEGNO + st3.6-3.9', 14, 7, 66.7, 21, 18.26),
    ('conf70-79 + q1.30-1.49 + tipo_GOL + st3.6-3.9', 14, 3, 82.4, 17, 18.13),
    ('conf70-79 + src_C_screm', 7, 1, 87.5, 8, 18.12),
    ('conf70-79 + route_scrematura', 7, 1, 87.5, 8, 18.12),
    ('conf70-79 + src_C_screm + route_scrematura', 7, 1, 87.5, 8, 18.12),
    ('conf70-79 + q1.30-1.49 + src_C + st3.6-3.9', 8, 1, 88.9, 9, 17.35),
    ('conf70-79 + q1.30-1.49 + pron_Goal + st3.6-3.9', 8, 1, 88.9, 9, 17.35),
    ('conf60-69 + src_C_screm', 15, 5, 75.0, 20, 16.86),
    ('src_C + tipo_GOL + st3.6-3.9', 41, 22, 65.1, 63, 16.70),
    ('conf70-79 + q1.30-1.49 + st3.6-3.9', 16, 4, 80.0, 20, 16.70),
    ('src_C + pron_1 + st3.6-3.9 + edge20-50', 6, 3, 66.7, 9, 15.48),
    ('route_single + pron_1 + st3.6-3.9 + edge20-50', 6, 3, 66.7, 9, 15.48),
    ('conf70-79 + q1.30-1.49 + src_C', 10, 2, 83.3, 12, 15.05),
    ('conf70-79 + q1.30-1.49 + src_C + tipo_GOL', 10, 2, 83.3, 12, 15.05),
    ('conf70-79 + q1.30-1.49 + src_C + pron_Goal', 10, 2, 83.3, 12, 15.05),
    ('conf70-79 + q1.50-1.79 + tipo_SEGNO', 12, 6, 66.7, 18, 14.57),
    ('conf60-69 + q1.50-1.79 + st3.6-3.9', 20, 10, 66.7, 30, 14.48),
    ('conf70-79 + q1.50-1.79 + src_C + route_single', 8, 4, 66.7, 12, 14.42),
    ('conf70-79 + src_C + pron_Goal + st3.6-3.9', 19, 9, 67.9, 28, 13.99),
    ('conf60-69 + route_scrematura', 14, 5, 73.7, 19, 13.90),
    ('conf60-69 + src_C_screm + route_scrematura', 14, 5, 73.7, 19, 13.90),
    ('conf70-79 + pron_Goal + st3.6-3.9', 20, 10, 66.7, 30, 13.56),
    ('conf70-79 + tipo_GOL + pron_Goal + st3.6-3.9', 20, 10, 66.7, 30, 13.56),
    ('conf60-69 + q1.30-1.49 + st3.6-3.9', 11, 3, 78.6, 14, 13.42),
    ('conf70-79 + q1.30-1.49 + pron_Goal', 15, 6, 71.4, 21, 13.24),
    ('conf70-79 + q1.30-1.49 + tipo_GOL + pron_Goal', 15, 6, 71.4, 21, 13.24),
    ('conf70-79 + q1.50-1.79 + pron_1', 10, 5, 66.7, 15, 12.49),
    ('conf70-79 + q1.50-1.79 + tipo_SEGNO + pron_1', 10, 5, 66.7, 15, 12.49),
    ('src_C_screm + tipo_GOL', 32, 14, 69.6, 46, 12.13),
    ('conf60-69 + q1.30-1.49 + src_C_screm', 7, 1, 87.5, 8, 11.10),
    ('conf60-69 + q1.30-1.49 + route_scrematura', 7, 1, 87.5, 8, 11.10),
    ('conf60-69 + q1.30-1.49 + src_C_screm + route_scrematura', 7, 1, 87.5, 8, 11.10),
    ('conf60-69 + tipo_GOL + st3.6-3.9', 32, 17, 65.3, 49, 10.53),
    ('route_scrematura + tipo_GOL', 31, 14, 68.9, 45, 9.17),
    ('src_C_screm + route_scrematura + tipo_GOL', 31, 14, 68.9, 45, 9.17),
    ('conf70-79 + pron_Goal', 40, 21, 65.6, 61, 8.90),
    ('conf70-79 + tipo_GOL + pron_Goal', 40, 21, 65.6, 61, 8.90),
    ('q1.30-1.49 + route_union', 8, 1, 88.9, 9, 8.66),
    ('q1.30-1.49 + route_union + tipo_GOL', 8, 1, 88.9, 9, 8.66),
    ('conf60-69 + q1.30-1.49 + pron_Goal', 7, 1, 87.5, 8, 7.75),
    ('conf60-69 + q1.30-1.49 + tipo_GOL + pron_Goal', 7, 1, 87.5, 8, 7.75),
    ('conf60-69 + route_union', 8, 1, 88.9, 9, 7.57),
    ('conf60-69 + route_union + tipo_GOL', 8, 1, 88.9, 9, 7.57),
    ('src_C_screm + st3.6-3.9', 7, 2, 77.8, 9, 7.05),
    ('route_scrematura + st3.6-3.9', 7, 2, 77.8, 9, 7.05),
    ('src_C_screm + route_scrematura + st3.6-3.9', 7, 2, 77.8, 9, 7.05),
    ('conf70-79 + src_C + tipo_GOL + st3.6-3.9', 19, 10, 65.5, 29, 6.99),
    ('conf60-69 + q1.50-1.79 + src_C_screm', 7, 3, 70.0, 10, 6.62),
    ('conf60-69 + src_C_screm + tipo_GOL', 8, 2, 80.0, 10, 6.19),
    ('conf60-69 + q1.30-1.49 + route_union', 7, 1, 87.5, 8, 6.07),
    ('conf60-69 + q1.30-1.49 + route_union + tipo_GOL', 7, 1, 87.5, 8, 6.07),
    ('conf60-69 + q1.30-1.49 + tipo_GOL + st3.6-3.9', 9, 3, 75.0, 12, 5.28),
    ('conf60-69 + q1.50-1.79 + route_scrematura', 6, 3, 66.7, 9, 3.66),
    ('conf60-69 + q1.50-1.79 + src_C_screm + route_scrematura', 6, 3, 66.7, 9, 3.66),
    ('conf60-69 + route_scrematura + tipo_GOL', 7, 2, 77.8, 9, 3.23),
    ('conf60-69 + src_C_screm + route_scrematura + tipo_GOL', 7, 2, 77.8, 9, 3.23),
    ('route_union + tipo_GOL', 9, 2, 81.8, 11, 3.16),
    ('conf60-69 + q1.50-1.79 + tipo_GOL + st3.6-3.9', 13, 7, 65.0, 20, 1.52),
    ('conf60-69 + q1.30-1.49 + tipo_GOL', 31, 14, 68.9, 45, 0.42),
    ('conf60-69 + route_single + tipo_GOL', 7, 3, 70.0, 10, -3.04),
    ('conf50-59 + q1.30-1.49 + tipo_GOL', 8, 3, 72.7, 11, -7.86),
    ('q1.30-1.49 + src_C_screm', 29, 15, 65.9, 44, -10.70),
    ('q1.30-1.49 + route_scrematura', 29, 15, 65.9, 44, -10.70),
    ('q1.30-1.49 + src_C_screm + route_scrematura', 29, 15, 65.9, 44, -10.70),
    ('conf70-79 + q1.30-1.49', 48, 24, 66.7, 72, -26.45),
    ('q1.30-1.49 + tipo_GOL', 89, 43, 67.4, 132, -47.03),
]

def parse_conditions(name):
    return set(c.strip() for c in name.split(' + '))

kept = []
removed_genitori = 0
removed_superset = 0

for name, v, p, hr, n, pl in patterns:
    conds = parse_conditions(name)

    # E' un genitore esatto?
    if any(conds == g for g in genitori):
        removed_genitori += 1
        continue

    # E' un superset di un genitore? (contiene TUTTE le condizioni di un genitore)
    if any(g.issubset(conds) for g in genitori):
        removed_superset += 1
        continue

    kept.append((name, v, p, hr, n, pl))

print(f'Totale pattern: {len(patterns)}')
print(f'Rimossi (genitori esatti): {removed_genitori}')
print(f'Rimossi (superset di genitore): {removed_superset}')
print(f'RESTANTI UNICI: {len(kept)}')
print()
print(f'{"#":>3s} | {"Pattern":60s} | {"V":>3s}/{"P":>3s} | {"HR":>6s} | {"N":>3s} | {"P/L":>9s}')
print(f'{"-"*93}')
for i, (name, v, p, hr, n, pl) in enumerate(kept, 1):
    print(f'{i:3d} | {name:60s} | {v:3d}/{p:3d} | {hr:5.1f}% | {n:3d} | {pl:+8.2f}u')
