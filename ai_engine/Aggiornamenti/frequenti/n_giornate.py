import os
import sys
from dotenv import load_dotenv

# Fix percorsi
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path: break
    current_path = parent
sys.path.append(current_path)

from config import db

aliases_da_aggiungere = [
    ("Atl. Tucumán", "Atl. Tucuman"),
    ("Barracas C.", "Barracas Central"),
    ("Defensa", "Defensa y Justicia"),
    ("Estudiantes LP", "Estudiantes L.P."),
    ("Estudiantes RC", "Estudiantes Rio Cuarto"),
    ("Gimnasia", "Gimnasia L.P."),
    ("Gimnasia (M)", "Gimnasia Mendoza"),
    ("Newell's", "Newells Old Boys"),
    ("CA Talleres", "Talleres Cordoba"),
    ("Unión Santa Fe", "Union de Santa Fe"),
]

for nome_db, nuovo_alias in aliases_da_aggiungere:
    result = db["teams"].update_one(
        {"name": nome_db},
        {"$addToSet": {"aliases": nuovo_alias}}
    )
    if result.modified_count:
        print(f"✅ Aggiunto '{nuovo_alias}' a {nome_db}")
    else:
        print(f"⚠️ {nome_db} non trovato o alias già presente")