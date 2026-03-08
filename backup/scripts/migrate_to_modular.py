"""
Migration script to help transition from monolithic models.py to modular structure
"""

import os
import shutil
from pathlib import Path

def migrate_to_modular_structure():
    """
    Migrate from single models.py to modular structure
    """
    
    # Backup original models.py
    if os.path.exists('models.py'):
        print("Backing up original models.py to models_backup.py...")
        shutil.copy2('models.py', 'models_backup.py')
        
        # Optional: Remove old models.py after backup
        # os.remove('models.py')
        print("Original models.py backed up successfully!")
    
    # Verify new structure exists
    models_dir = Path('models')
    cores_dir = models_dir / 'cores'
    users_dir = models_dir / 'users'
    
    required_files = [
        models_dir / '__init__.py',
        models_dir / 'base.py',
        cores_dir / '__init__.py',
        cores_dir / 'locations.py',
        cores_dir / 'references.py',
        cores_dir / 'permissions.py',
        cores_dir / 'subscriptions.py',
        cores_dir / 'translations.py',
        users_dir / '__init__.py',
        users_dir / 'user_location.py',
        users_dir / 'organizations.py',
        users_dir / 'roles.py',
        users_dir / 'user_related.py'
    ]
    
    missing_files = [f for f in required_files if not f.exists()]
    
    if missing_files:
        print("❌ Missing files:")
        for file in missing_files:
            print(f"  - {file}")
        return False
    
    print("✅ All modular structure files are present!")
    
    # Test imports
    try:
        print("Testing imports...")
        
        # Test base imports
        from models.base import Base, BaseModel, PlatformEnum
        print("  ✅ Base imports successful")
        
        # Test core imports
        from models.cores import (
            LocationCountry, Bank, Currency, Material, 
            Permission, SubscriptionPackage, Translation
        )
        print("  ✅ Core model imports successful")
        
        # Test user imports
        from models.users import (
            UserLocation, Organization, UserRole, 
            UserBank, UserSubscription, UserInputChannel
        )
        print("  ✅ User model imports successful")
        
        # Test main models import
        from models import Base, UserLocation, Bank, Currency
        print("  ✅ Main models import successful")
        
        print("🎉 Migration to modular structure completed successfully!")
        
        # Print usage instructions
        print("\n📋 Usage Instructions:")
        print("1. Update your imports from:")
        print("   from models import UserLocation, Bank")
        print("   to:")
        print("   from models import UserLocation, Bank")
        print("   (No change needed for main imports!)")
        print("")
        print("2. For specific module imports:")
        print("   from models.cores import Bank, Currency")
        print("   from models.users import UserLocation, UserRole")
        print("")
        print("3. Database initialization remains the same:")
        print("   python database.py")
        print("")
        print("4. Your old models.py is backed up as models_backup.py")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def show_module_structure():
    """Show the new modular structure"""
    
    print("📁 New Modular Structure:")
    print("models/")
    print("├── __init__.py          # Main imports")
    print("├── base.py              # Base classes and enums")
    print("├── cores/               # Core/reference data")
    print("│   ├── __init__.py")
    print("│   ├── locations.py     # Location models")
    print("│   ├── references.py    # Banks, currencies, materials")
    print("│   ├── permissions.py   # Permission models")
    print("│   ├── subscriptions.py # Subscription models")
    print("│   └── translations.py  # Translation models")
    print("└── users/               # User and organizational models")
    print("    ├── __init__.py")
    print("    ├── user_location.py # Main UserLocation model")
    print("    ├── organizations.py # Organization models")
    print("    ├── roles.py         # User role models")
    print("    └── user_related.py  # User-related models")
    print("")
    print("Benefits of modular structure:")
    print("• Better code organization")
    print("• Easier to maintain and extend")
    print("• Clearer separation of concerns")
    print("• Faster imports for specific modules")
    print("• Team collaboration friendly")

if __name__ == "__main__":
    print("🚀 GEPP Database Model Migration")
    print("=" * 40)
    
    show_module_structure()
    print("")
    
    migrate_success = migrate_to_modular_structure()
    
    if migrate_success:
        print("\n✅ Migration completed successfully!")
        print("You can now use the new modular structure.")
    else:
        print("\n❌ Migration failed. Please check the errors above.")