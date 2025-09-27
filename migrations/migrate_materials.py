#!/usr/bin/env python3
"""
Materials Migration Script
Automated migration from CSV data to new three-tier materials architecture

Usage:
    python migrate_materials.py [--dry-run] [--verify-only]

Options:
    --dry-run       Show what would be done without executing
    --verify-only   Only verify data integrity without migration
"""

import os
import sys
import csv
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MaterialsMigrator:
    def __init__(self, db_url: str, csv_path: str):
        self.db_url = db_url
        self.csv_path = csv_path
        self.conn = None

    def connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(self.db_url)
            self.conn.autocommit = False
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def disconnect(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def execute_sql_file(self, file_path: str, dry_run: bool = False) -> bool:
        """Execute SQL migration file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            if dry_run:
                logger.info(f"DRY RUN: Would execute {file_path}")
                logger.info(f"SQL Content Preview: {sql_content[:200]}...")
                return True

            logger.info(f"Executing migration: {file_path}")

            with self.conn.cursor() as cursor:
                cursor.execute(sql_content)
                self.conn.commit()

            logger.info(f"Successfully executed: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to execute {file_path}: {e}")
            if self.conn:
                self.conn.rollback()
            return False

    def read_csv_data(self) -> List[Dict[str, Any]]:
        """Read and parse CSV data"""
        try:
            materials = []
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    materials.append({
                        'id': int(row['ID']),
                        'name_th': row['name_th'],
                        'category': row['Category'],
                        'main_material': row['Main material'],
                        'unit_name_th': row['unit_name_th'],
                        'unit_name_en': row['unit_name_en'],
                        'unit_weight': float(row['unit_weight']) if row['unit_weight'] else 1.0,
                        'color': row['color'].strip() if row['color'] else '',
                        'calc_ghg': float(row['calc_ghg']) if row['calc_ghg'] else 0.0,
                        'name_en': row['name_en']
                    })

            logger.info(f"Read {len(materials)} materials from CSV")
            return materials

        except Exception as e:
            logger.error(f"Failed to read CSV data: {e}")
            raise

    def analyze_csv_data(self) -> Dict[str, Any]:
        """Analyze CSV data structure"""
        materials = self.read_csv_data()

        categories = set(material['category'] for material in materials)
        main_materials = set(material['main_material'] for material in materials)
        units = set(material['unit_name_en'] for material in materials)

        analysis = {
            'total_materials': len(materials),
            'categories': sorted(list(categories)),
            'main_materials': sorted(list(main_materials)),
            'units': sorted(list(units)),
            'category_count': len(categories),
            'main_material_count': len(main_materials),
            'unit_count': len(units)
        }

        logger.info("CSV Data Analysis:")
        logger.info(f"  Total Materials: {analysis['total_materials']}")
        logger.info(f"  Categories: {analysis['category_count']} - {analysis['categories']}")
        logger.info(f"  Main Materials: {analysis['main_material_count']} - {analysis['main_materials']}")
        logger.info(f"  Units: {analysis['unit_count']} - {analysis['units']}")

        return analysis

    def verify_migration(self) -> bool:
        """Verify migration results"""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Check table existence
                cursor.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name IN ('material_categories', 'main_materials', 'materials')
                    AND table_schema = 'public'
                """)
                tables = [row['table_name'] for row in cursor.fetchall()]

                expected_tables = ['material_categories', 'main_materials', 'materials']
                missing_tables = set(expected_tables) - set(tables)

                if missing_tables:
                    logger.error(f"Missing tables: {missing_tables}")
                    return False

                # Check record counts
                cursor.execute("SELECT COUNT(*) as count FROM material_categories WHERE is_active = true")
                category_count = cursor.fetchone()['count']

                cursor.execute("SELECT COUNT(*) as count FROM main_materials WHERE is_active = true")
                main_material_count = cursor.fetchone()['count']

                cursor.execute("SELECT COUNT(*) as count FROM materials WHERE is_active = true")
                material_count = cursor.fetchone()['count']

                # Check relationships
                cursor.execute("""
                    SELECT COUNT(*) as count FROM materials
                    WHERE category_id IS NULL OR main_material_id IS NULL
                """)
                orphaned_materials = cursor.fetchone()['count']

                # Check data integrity
                cursor.execute("""
                    SELECT
                        m.id,
                        m.name_th,
                        cat.name_th as category_name,
                        mm.name_th as main_material_name
                    FROM materials m
                    LEFT JOIN material_categories cat ON m.category_id = cat.id
                    LEFT JOIN main_materials mm ON m.main_material_id = mm.id
                    WHERE cat.id IS NULL OR mm.id IS NULL
                    LIMIT 5
                """)
                broken_relationships = cursor.fetchall()

                # Report results
                logger.info("Migration Verification Results:")
                logger.info(f"  ✓ All required tables exist: {len(tables)}/3")
                logger.info(f"  ✓ Material Categories: {category_count}")
                logger.info(f"  ✓ Main Materials: {main_material_count}")
                logger.info(f"  ✓ Materials: {material_count}")

                if orphaned_materials > 0:
                    logger.warning(f"  ⚠ Orphaned materials (no category/main_material): {orphaned_materials}")

                if broken_relationships:
                    logger.error(f"  ✗ Broken relationships found: {len(broken_relationships)}")
                    for rel in broken_relationships:
                        logger.error(f"    - Material {rel['id']}: {rel['name_th']}")
                    return False
                else:
                    logger.info("  ✓ All relationships are valid")

                # Expected counts based on CSV analysis
                csv_analysis = self.analyze_csv_data()
                if material_count != csv_analysis['total_materials']:
                    logger.warning(f"Material count mismatch: DB={material_count}, CSV={csv_analysis['total_materials']}")

                return orphaned_materials == 0 and len(broken_relationships) == 0

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False

    def run_migration(self, dry_run: bool = False) -> bool:
        """Run complete migration process"""
        try:
            # Step 1: Analyze CSV data
            logger.info("Step 1: Analyzing CSV data...")
            self.analyze_csv_data()

            # Step 2: Execute table structure migration
            logger.info("Step 2: Creating new table structure...")
            structure_file = os.path.join(
                os.path.dirname(__file__),
                '20250922_100000_020_restructure_materials_tables.sql'
            )

            if not self.execute_sql_file(structure_file, dry_run):
                return False

            # Step 3: Execute data migration
            logger.info("Step 3: Migrating data from CSV...")
            data_file = os.path.join(
                os.path.dirname(__file__),
                '20250922_110000_021_migrate_materials_data_from_csv.sql'
            )

            if not self.execute_sql_file(data_file, dry_run):
                return False

            if not dry_run:
                # Step 4: Verify migration
                logger.info("Step 4: Verifying migration results...")
                if not self.verify_migration():
                    logger.error("Migration verification failed!")
                    return False

            logger.info("✅ Migration completed successfully!")
            return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description='Migrate materials data to new architecture')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without executing')
    parser.add_argument('--verify-only', action='store_true', help='Only verify data integrity')
    parser.add_argument('--db-url', help='Database URL (default: from .env)')
    parser.add_argument('--csv-path', help='Path to CSV file (default: data/New Mainmat_Submat.csv)')

    args = parser.parse_args()

    # Get database URL
    db_url = args.db_url
    if not db_url:
        # Try to read from .env file
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.startswith('DATABASE_URL='):
                        db_url = line.split('=', 1)[1].strip()
                        break

    if not db_url:
        logger.error("Database URL not provided. Use --db-url or set DATABASE_URL in .env file")
        sys.exit(1)

    # Get CSV path
    csv_path = args.csv_path or os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'data',
        'New Mainmat_Submat.csv'
    )

    if not os.path.exists(csv_path):
        logger.error(f"CSV file not found: {csv_path}")
        sys.exit(1)

    # Initialize migrator
    migrator = MaterialsMigrator(db_url, csv_path)

    try:
        migrator.connect()

        if args.verify_only:
            logger.info("Running verification only...")
            success = migrator.verify_migration()
        else:
            logger.info(f"Running migration (dry_run={args.dry_run})...")
            success = migrator.run_migration(dry_run=args.dry_run)

        if success:
            logger.info("✅ Operation completed successfully!")
            sys.exit(0)
        else:
            logger.error("❌ Operation failed!")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        migrator.disconnect()


if __name__ == '__main__':
    main()