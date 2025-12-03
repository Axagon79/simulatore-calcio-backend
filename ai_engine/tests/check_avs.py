from config import db

# Cerchiamo quale giornata contiene questa coppia eretica
bad_match = db.h2h_by_round.find_one({
    "matches": {
        "$elemMatch": {
            "home": "AVS",
            "away": "Bra"
        }
    }
})

if bad_match:
    print(f"Trovato il colpevole! È nella lega: {bad_match.get('league')}")
    print(f"Giornata: {bad_match.get('round_name')}")
else:
    print("Nessuna partita AVS-Bra trovata nel calendario. Mistero fitto.")
