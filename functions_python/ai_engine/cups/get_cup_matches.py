#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GET CUP MATCHES - Recupera lista partite da Champions/Europa League

Usage:
    python get_cup_matches.py <competition>
    
Example:
    python get_cup_matches.py UEL
"""

import os
import sys
import json

# Fix percorsi
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
AI_ENGINE_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, AI_ENGINE_DIR)

from config import db

COMPETITIONS_MAP = {
    "UCL": {
        "name": "Champions League",
        "collection": "matches_champions_league"
    },
    "UEL": {
        "name": "Europa League",
        "collection": "matches_europa_league"
    }
}


def get_cup_matches(competition):
    """Recupera lista partite per una competizione"""
    
    if competition not in COMPETITIONS_MAP:
        return {
            "success": False,
            "error": f"Competizione non valida: {competition}. Usa UCL o UEL."
        }
    
    config = COMPETITIONS_MAP[competition]
    collection_name = config["collection"]
    
    try:
        # Recupera tutte le partite della stagione corrente
        matches_cursor = db[collection_name].find(
            {"season": "2025-2026"},
            {"_id": 0}
        )
        matches_raw = list(matches_cursor)
        
        # ✅ CONVERTI datetime in stringhe
        def convert_dates(obj):
            """Converte datetime in stringhe ISO"""
            if isinstance(obj, dict):
                return {k: convert_dates(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_dates(item) for item in obj]
            elif hasattr(obj, 'isoformat'):  # datetime objects
                return obj.isoformat()
            else:
                return obj
        
        matches = convert_dates(matches_raw)
        
        # ✅ SEPARA PARTITE GIOCATE E DA GIOCARE
        played_matches = [m for m in matches if m.get('status') == 'finished']
        upcoming_matches = [m for m in matches if m.get('status') == 'scheduled']
        
        # ✅ FILTRA: Ultima giocata e prossima per ogni squadra
        from datetime import datetime
        from collections import defaultdict
        
        def parse_date(date_str):
            """Converte stringa data in datetime per ordinamento"""
            try:
                return datetime.strptime(date_str, '%d-%m-%Y %H:%M')
            except:
                return datetime.min
        
        # Set per tracciare squadre già viste
        teams_with_played = set()
        teams_with_upcoming = set()

        # Ordina partite giocate per data (più recente prima)
        played_sorted = sorted(played_matches, key=lambda x: parse_date(x.get('match_date', '')), reverse=True)

        # Ordina partite da giocare per data (più vicina prima)
        upcoming_sorted = sorted(upcoming_matches, key=lambda x: parse_date(x.get('match_date', '')))

        # Filtra partite giocate: prendi solo se ALMENO UNA delle due squadre non l'abbiamo già vista
        final_played = []
        for match in played_sorted:
            home = match.get('home_team')
            away = match.get('away_team')
            
            # Aggiungi partita se almeno una squadra non ha ancora una partita
            if home not in teams_with_played or away not in teams_with_played:
                final_played.append(match)
                teams_with_played.add(home)
                teams_with_played.add(away)

        # Filtra partite da giocare: prendi solo se ALMENO UNA delle due squadre non l'abbiamo già vista
        final_upcoming = []
        for match in upcoming_sorted:
            home = match.get('home_team')
            away = match.get('away_team')
            
            # Aggiungi partita se almeno una squadra non ha ancora una partita
            if home not in teams_with_upcoming or away not in teams_with_upcoming:
                final_upcoming.append(match)
                teams_with_upcoming.add(home)
                teams_with_upcoming.add(away)
        
        # Ordina per data
        final_played_sorted = sorted(final_played, key=lambda x: parse_date(x.get('match_date', '')), reverse=True)
        final_upcoming_sorted = sorted(final_upcoming, key=lambda x: parse_date(x.get('match_date', '')))
        
        # Combina con separatore
        matches_sorted = {
            'played': final_played_sorted,
            'upcoming': final_upcoming_sorted
        }
        
        return {
            "success": True,
            "competition": {
                "code": competition,
                "name": config["name"],
                "collection": collection_name
            },
            "matches": matches_sorted,
            "count": {
                "played": len(final_played_sorted),
                "upcoming": len(final_upcoming_sorted),
                "total": len(final_played_sorted) + len(final_upcoming_sorted)
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "competition": competition
        }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "Parametro mancante. Usage: python get_cup_matches.py <UCL|UEL>"
        }))
        return
    
    competition = sys.argv[1].upper()
    result = get_cup_matches(competition)
    
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()