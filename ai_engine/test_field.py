from calculator_field_factor import calculate_field_factor

# Test con due squadre reali che ora hanno i dati
print("--- TEST FATTORE CAMPO ---")
print("Calcolo per Inter vs AC Milan (Serie A)...")
try:
    punti_casa, punti_trasferta = calculate_field_factor("Inter", "AC Milan", "Serie A")
    print(f"Punteggio Inter (Casa): {punti_casa} / 7")
    print(f"Punteggio Milan (Fuori): {punti_trasferta} / 7")
except Exception as e:
    print(f"Errore: {e}")
