#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GET CUP TEAMS - Recupera lista squadre da Champions/Europa League

Usage:
    python get_cup_teams.py <competition>
    
Example:
    python get_cup_teams.py UCL
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
        "collection": "teams_champions_league"
    },
    "UEL": {
        "name": "Europa League",
        "collection": "teams_europa_league"
    }
}


def get_cup_teams(competition):
    """Recupera lista squadre per una competizione"""
    
    if competition not in COMPETITIONS_MAP:
        return {
            "success": False,
            "error": f"Competizione non valida: {competition}. Usa UCL o UEL."
        }
    
    config = COMPETITIONS_MAP[competition]
    collection_name = config["collection"]
    
    try:
        # Recupera tutte le squadre
        teams_cursor = db[collection_name].find({}, {"_id": 0})
        teams = list(teams_cursor)
        
        # Ordina per nome
        teams_sorted = sorted(teams, key=lambda x: x.get('name', ''))
        
        return {
            "success": True,
            "competition": {
                "code": competition,
                "name": config["name"],
                "collection": collection_name
            },
            "teams": teams_sorted,
            "count": len(teams_sorted)
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
            "error": "Parametro mancante. Usage: python get_cup_teams.py <UCL|UEL>"
        }))
        return
    
    competition = sys.argv[1].upper()
    result = get_cup_teams(competition)
    
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()