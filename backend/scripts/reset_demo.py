"""Reset script for LexProof demo environment.

This script removes all demo data and resets the environment to a clean state.

Usage:
    python scripts/reset_demo.py

Author: LexProof Development Team
Date: 2026-08-23
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Demo files to remove
DEMO_FILES = [
    "demo_data.json",
    "demo_data_backup.json",
    "demo_data_backup_*.json",
]

# Database tables to drop (if applicable)
DB_TABLES_TO_DROP = [
    "contracts",
    "contract_passports",
    "evidence_items",
    "regulatory_changes",
    "monitoring_events",
    "amendment_requests",
    "audit_trail_entries",
]

# Directory paths to clean
DIRECTORIES_TO_CLEAN = [
    "temp",
    "logs",
]


def remove_files() -> None:
    """Remove demo data files."""
    print("\n" + "=" * 80)
    print("REMOVING DEMO DATA FILES")
    print("=" * 80)

    base_dir = Path(__file__).parent.parent

    for pattern in DEMO_FILES:
        print(f"\nSearching for: {pattern}")
        found_files = list(Path(base_dir).glob(pattern))

        if not found_files:
            print(f"  ✗ No files found matching '{pattern}'")
            continue

        for file_path in found_files:
            try:
                if file_path.is_file():
                    file_path.unlink()
                    print(f"  ✓ Removed: {file_path.name}")
            except Exception as e:
                print(f"  ✗ Error removing {file_path.name}: {e}")


def remove_directories() -> None:
    """Remove temporary directories."""
    print("\n" + "=" * 80)
    print("REMOVING TEMPORARY DIRECTORIES")
    print("=" * 80)

    base_dir = Path(__file__).parent.parent

    for dir_path in DIRECTORIES_TO_CLEAN:
        full_path = Path(base_dir) / dir_path

        if full_path.exists():
            try:
                shutil.rmtree(full_path)
                print(f"  ✓ Removed: {dir_path}")
            except Exception as e:
                print(f"  ✗ Error removing {dir_path}: {e}")
        else:
            print(f"  ✓ Not found (skipping): {dir_path}")


def show_database_info() -> None:
    """Show database information and offer to reset tables."""
    print("\n" + "=" * 80)
    print("DATABASE INFORMATION")
    print("=" * 80)

    print("\nDemo data tables that can be dropped:")
    for table in DB_TABLES_TO_DROP:
        print(f"  - {table}")

    print("\nTo reset database tables, run:")
    print("  psql -U your_user -d lexproof -c '\\dt'")
    print("  psql -U your_user -d lexproof -c 'DROP TABLE IF EXISTS {table} CASCADE;'")

    print("\nNote: Database reset requires database admin privileges.")
    print("      This script only removes demo data files.")


def main():
    """Main entry point."""
    print("\n" + "=" * 80)
    print("LEXPROOF DEMO ENVIRONMENT RESET")
    print("=" * 80)
    print("\nThis script will remove all demo data and temporary files.")
    print("This action cannot be undone.")

    # Confirm reset
    print("\n" + "-" * 80)
    response = input("Are you sure you want to reset the demo environment? (yes/no): ")

    if response.lower() not in ["yes", "y"]:
        print("\nReset cancelled.")
        return

    # Remove files
    remove_files()

    # Remove directories
    remove_directories()

    # Show database info
    show_database_info()

    print("\n" + "=" * 80)
    print("RESET COMPLETE")
    print("=" * 80)
    print("\nDemo environment has been reset to a clean state.")
    print("\nTo re-seed demo data, run:")
    print("  python scripts/seed_demo.py --output demo_data.json")
    print("\nOr to see demo data summary without saving:")
    print("  python scripts/seed_demo.py --print-only")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
