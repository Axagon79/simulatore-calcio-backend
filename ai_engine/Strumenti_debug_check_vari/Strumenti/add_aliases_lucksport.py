"""
Aggiunge alias LuckSport nella collection db.teams.
Ogni entry: (hint_regex_per_trovare_team, [alias_da_aggiungere])
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from config import db

# (regex hint per trovare il team in db.teams, [alias lucksport da aggiungere])
ALIASES = [
    # Brasileirão
    ("Botafogo",        ["Botafogo de Futebol e Regatas"]),
    ("Coritiba",        ["Coritiba (PR)"]),
    ("Cruzeiro",        ["Cruzeiro (MG)"]),
    ("EC Bahia",        ["Esporte Clube Bahia"]),
    ("EC Vitória",      ["Esporte Clube Vitoria"]),
    ("Fluminense",      ["Fluminense FC"]),
    ("Mirassol",        ["Mirassol FC"]),
    ("Internacional",   ["SC Internacional"]),
    ("São Paulo",       ["Sao Paulo FC"]),
    ("Corinthians",     ["Sport Club Corinthians Paulista"]),
    # LaLiga 2
    ("Castellón",       ["CD Castellon"]),
    ("Leganés",         ["CD Leganes"]),
    ("UD Almería",      ["UD Almeria"]),
    # League One
    ("Leyton Orient",   ["Leyton Orient F.C."]),
    ("Wigan",           ["Wigan Athletic F.C."]),
    # League Two
    ("Cambridge",       ["Cambridge United F.C."]),
    ("Swindon",         ["Swindon Town F.C."]),
    ("Grimsby",         ["Grimsby Town F.C."]),
    ("Harrogate",       ["Harrogate Town F.C."]),
    # Primera División Argentina
    ("Lanús",           ["Club Atletico Lanus"]),
    ("Platense",        ["Club Atletico Platense"]),
]

ok = 0
skip = 0
fail = 0

for hint, aliases in ALIASES:
    team = db.teams.find_one({"name": {"$regex": f"^{hint}", "$options": "i"}})
    if not team:
        print(f"❌ Team non trovato: '{hint}'")
        fail += 1
        continue

    res = db.teams.update_one(
        {"_id": team["_id"]},
        {"$addToSet": {"aliases": {"$each": aliases}}}
    )
    if res.modified_count > 0:
        print(f"✅ {team['name']}: +{len(aliases)} alias ({', '.join(aliases)})")
        ok += 1
    else:
        print(f"⏭️  {team['name']}: alias già presenti")
        skip += 1

print(f"\n{'='*40}")
print(f"✅ Aggiunti: {ok} | ⏭️ Già presenti: {skip} | ❌ Non trovati: {fail}")
