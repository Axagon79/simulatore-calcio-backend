import os
from pathlib import Path

FILES_TO_PATCH = [
    "utils/analyze_complete_database.py",
    "utils/analyze_formations.py",
    "utils/check_availability.py",
    "utils/check_database_structure.py",
    "utils/check_data_health.py",
    "utils/check_missing_points.py",
    "utils/check_serie_c_data.py",
    "utils/check_serie_c_strength.py",
    "utils/check_status.py",
    "utils/check_team_names.py",
    "utils/scan_database.py",
    "utils/scan_full_database.py",
    "calculators/calculate_all_scores.py",
    "calculators/calculate_motivation.py",
    "calculators/calculate_serie_c_rating.py",
    "calculators/calculate_team_rating.py",
    "calculators/calculator_bvs.py",
    "calculators/calculator_field_factor.py",
    "calculators/calculator_lucifero.py",
    "calculators/calculator_reliability.py",
    "scrapers/fbref_scraper_att.py",
    "scrapers/fbref_scraper_def.py",
    "scrapers/fbref_scraper_mid.py",
    "scrapers/scraper_betexplorer_selenium.py",
    "scrapers/scraper_final_v3.py",
    "scrapers/scraper_fixtures.py",
    "scrapers/scraper_gk_fbref.py",
    "scrapers/scraper_odds_oddsmath.py",
    "scrapers/scraper_rankings_points.py",
    "scrapers/scraper_results_fbref.py",
    "scrapers/scraper_tm_multi_campionato.py",
    "scrapers/scraper_transfermarkt_complete.py",
]



BASE_DIR = Path(__file__).resolve().parent

def needs_sys_path_header(path):
    return path.parent != BASE_DIR

def build_header(path):
    lines = []
    if needs_sys_path_header(path):
        lines.append("import os")
        lines.append("import sys")
        lines.append("sys.path.append(os.path.dirname(os.path.dirname(__file__)))")
        lines.append("from config import db")
    else:
        lines.append("from config import db")
    return "\n".join(lines) + "\n\n"

def refactor_content(text, path):
    lines = text.splitlines()
    new_lines = []
    have_config_import = "from config import db" in text

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("from pymongo import MongoClient"):
            continue
        if stripped.startswith("import pymongo"):
            continue
        if "MONGO_URI" in stripped and "mongodb" in stripped:
            continue
        if "MongoClient(" in stripped and "client" in stripped:
            continue
        if "db = client" in stripped:
            continue

        new_lines.append(line)

    new_text = "\n".join(new_lines).lstrip("\n")

    if not have_config_import:
        header = build_header(path)
        new_text = header + new_text

    return new_text

def process_file(rel_path):
    path = BASE_DIR / rel_path
    if not path.exists():
        print("File non trovato:", rel_path)
        return

    original = path.read_text(encoding="utf-8")
    updated = refactor_content(original, path)

    if original == updated:
        print("Nessuna modifica necessaria:", rel_path)
        return

    backup_path = path.with_suffix(path.suffix + ".bak")
    backup_path.write_text(original, encoding="utf-8")
    print("Backup creato:", backup_path)

    path.write_text(updated, encoding="utf-8")
    print("File modificato:", rel_path)

def main():
    print("=== AUTO-REFACTOR CONNESSIONI MONGO ===")
    for rel in FILES_TO_PATCH:
        print("")
        print("Processing:", rel)
        process_file(rel)

if __name__ == "__main__":
    main()
