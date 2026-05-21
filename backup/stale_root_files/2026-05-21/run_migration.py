#!/usr/bin/env python3
"""
Simple migration runner to apply SQL migrations
"""

import os
import sys
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from GEPPPlatform.database import db_manager

def run_migration(migration_file):
    """Run a specific SQL migration file"""

    # Read the migration file
    migration_path = backend_dir / "migrations" / migration_file

    if not migration_path.exists():
        print(f"Migration file not found: {migration_path}")
        return False

    print(f"Running migration: {migration_file}")

    with open(migration_path, 'r') as f:
        sql_content = f.read()

    # Execute the SQL
    try:
        with db_manager.get_session() as session:
            # Split by semicolons and execute each statement
            statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]

            for statement in statements:
                if statement.upper().startswith(('ALTER', 'CREATE', 'DROP', 'INSERT', 'UPDATE', 'COMMENT')):
                    print(f"Executing: {statement[:100]}...")
                    session.execute(statement)

            session.commit()
            print(f"✅ Migration {migration_file} completed successfully!")
            return True

    except Exception as e:
        print(f"❌ Error running migration {migration_file}: {str(e)}")
        return False

def main():
    """Main function"""
    if len(sys.argv) != 2:
        print("Usage: python run_migration.py <migration_file>")
        print("Example: python run_migration.py 20250919_160000_019_add_members_to_user_locations.sql")
        return

    migration_file = sys.argv[1]
    success = run_migration(migration_file)

    if success:
        print("Migration completed successfully!")
        sys.exit(0)
    else:
        print("Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()