"""
Override locale nomi ClubElo per il Pattern Match Engine.

Usato SOLO da questo modulo. Non tocca il DB `teams`.
Motivazione: alcuni nomi ClubElo (es. 'Atletico') sono troppo generici per
finire come alias globali (matcherebbero Atletico Mineiro, Paranaense, ecc.).

Mappa: nome team Football-Data -> nome ClubElo per /api.clubelo.com/{name}.

Tutti i 36 mapping sono stati verificati manualmente:
- 13 risolti via ricerca DB filtrata per country/league
- 23 risolti via tentativi mirati su API ClubElo
- 6 risolti via traslitterazione tedesca (ü→ue, ö→oe)
- 4 risolti via lista globale ClubElo a date storiche

Squadre SENZA Elo (3, ClubElo non le traccia):
- Karabukspor (sciolto dopo 2017-18)
- Osmanlispor (retrocesso in 3a divisione turca)
- Fatih Karagumruk (mai in ClubElo, 2a divisione turca)
- Beerschot VA (non e' in db.teams ma trovato come 'BeerschotAC' su ClubElo)
"""
from __future__ import annotations


CLUBELO_OVERRIDES: dict[str, str] = {
    # Risolti via ricerca DB filtrata
    "AZ Alkmaar":           "Alkmaar",
    "Ad. Demirspor":        "Adana Demirspor",
    "Almere City":          "Almere",
    "Ath Bilbao":           "Bilbao",
    "Ath Madrid":           "Atletico",
    "For Sittard":          "Sittard",
    "Holstein Kiel":        "Holstein",
    "NAC Breda":            "Breda",
    "Nott'm Forest":        "Forest",
    "Sp Braga":             "Braga",
    "Sp Gijon":             "Gijon",
    "Vallecano":            "Rayo Vallecano",
    "Werder Bremen":        "Werder",

    # Risolti via tentativi mirati (forme abbreviate o standardizzate)
    "Akhisar Belediyespor": "Akhisar",
    "Bodrumspor":           "Bodrum",
    "Buyuksehyr":           "Bueyueksehir",
    "Kayserispor":          "Kayseri",
    "Yeni Malatyaspor":     "Malatyaspor",
    "Club Brugge":          "Brugge",
    "Mouscron-Peruwelz":    "Mouscron",
    "RWD Molenbeek":        "Molenbeek",
    "St. Gilloise":         "StGillis",
    "Waasland-Beveren":     "Beveren",
    "Waregem":              "ZulteWaregem",
    "FC Emmen":             "Emmen",
    "Graafschap":           "DeGraafschap",
    "VVV Venlo":            "Venlo",
    "Sp Lisbon":            "Sporting",
    "Espanol":              "Espanyol",
    "Ein Frankfurt":        "Frankfurt",
    "FC Koln":              "Koeln",
    "Fortuna Dusseldorf":   "Duesseldorf",
    "Greuther Furth":       "Fuerth",
    "M'gladbach":           "Gladbach",
    "Nurnberg":             "Nuernberg",
    "Inverness C":          "Inverness",

    # Risolti via traslitterazione tedesca su ClubElo
    "Ankaragucu":           "Ankaraguecue",
    "Goztep":               "Goeztepe",
    "Beerschot VA":         "BeerschotAC",

    # Risolti via lista globale ClubElo a date storiche
    "Mersin Idman Yurdu":   "MersinIdman",
    "Uniao Madeira":        "UMadeira",
    "Ajaccio GFCO":         "Gazelec",
    "La Coruna":            "Depor",
}


# Squadre note senza Elo (ClubElo non le traccia)
NO_ELO_TEAMS: set[str] = {
    "Karabukspor",
    "Osmanlispor",
    "Karagumruk",
}
