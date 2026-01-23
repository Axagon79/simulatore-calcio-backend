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
        
        # Ordina per data
        matches_sorted = sorted(matches, key=lambda x: x.get('match_date', ''))
        
        return {
            "success": True,
            "competition": {
                "code": competition,
                "name": config["name"],
                "collection": collection_name
            },
            "matches": matches_sorted,
            "count": len(matches_sorted)
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