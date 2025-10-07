#!/usr/bin/env python3
"""
Setup test data for IoT Scale System
Creates test users, locations, and IoT scales
"""

import os
import sys
import bcrypt
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from GEPPPlatform.database import DatabaseManager
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.iot.iot_scale import IoTScale

class TestDataSetup:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.session = None
    
    def get_session(self):
        """Get database session"""
        return self.db_manager.get_session()
    
    def close_session(self):
        """Close database session"""
        pass  # Session is managed by context manager
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def create_test_user(self, email: str, password: str, display_name: str, organization_id: int = 1) -> UserLocation:
        """Create a test user"""
        with self.get_session() as session:
            # Check if user already exists
            existing_user = session.query(UserLocation).filter_by(email=email).first()
            if existing_user:
                print(f"User {email} already exists, skipping...")
                return existing_user
            
            # Create new user
            hashed_password = self.hash_password(password)
            
            user = UserLocation(
                email=email,
                password=hashed_password,
                display_name=display_name,
                is_user=True,
                is_location=False,
                is_active=True,
                organization_id=organization_id,
                organization_level=1,
                business_type="Test Business",
                business_industry="Technology"
            )
            
            session.add(user)
            session.commit()
            session.refresh(user)
            
            print(f"Created test user: {email} (ID: {user.id})")
            return user
    
    def create_test_location(self, display_name: str, organization_id: int = 1) -> UserLocation:
        """Create a test location"""
        with self.get_session() as session:
            # Check if location already exists
            existing_location = session.query(UserLocation).filter_by(
                display_name=display_name, 
                is_location=True
            ).first()
            if existing_location:
                print(f"Location {display_name} already exists, skipping...")
                return existing_location
            
            # Create new location
            location = UserLocation(
                display_name=display_name,
                name_th=f"{display_name} (TH)",
                name_en=display_name,
                is_user=False,
                is_location=True,
                is_active=True,
                organization_id=organization_id,
                organization_level=2,
                address="123 Test Street, Bangkok 10110",
                coordinate="13.7563,100.5018",
                postal_code="10110",
                country="Thailand",
                province="Bangkok",
                district="Pathumwan",
                subdistrict="Lumphini",
                timezone="Asia/Bangkok",
                currency="THB",
                locale="th_TH"
            )
            
            session.add(location)
            session.commit()
            session.refresh(location)
            
            print(f"Created test location: {display_name} (ID: {location.id})")
            return location
    
    def create_test_iot_scale(self, scale_name: str, password: str, owner_id: int, location_id: int) -> IoTScale:
        """Create a test IoT scale"""
        with self.get_session() as session:
            # Check if scale already exists
            existing_scale = session.query(IoTScale).filter_by(scale_name=scale_name).first()
            if existing_scale:
                print(f"IoT Scale {scale_name} already exists, skipping...")
                return existing_scale
            
            # Create new IoT scale
            hashed_password = self.hash_password(password)
            
            iot_scale = IoTScale(
                scale_name=scale_name,
                password=hashed_password,
                owner_user_location_id=owner_id,
                location_point_id=location_id,
                added_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc) + timedelta(days=365),  # 1 year from now
                mac_tablet="AA:BB:CC:DD:EE:FF",
                mac_scale="11:22:33:44:55:66",
                status='active',
                scale_type="digital"
            )
            
            session.add(iot_scale)
            session.commit()
            session.refresh(iot_scale)
            
            print(f"Created test IoT scale: {scale_name} (ID: {iot_scale.id})")
            return iot_scale
    
    def setup_all_test_data(self):
        """Setup all test data"""
        print("Setting up test data for IoT Scale System...")
        print("=" * 50)
        
        try:
            # Create test users
            print("\n1. Creating test users...")
            test_user = self.create_test_user(
                email="test@example.com",
                password="password123",
                display_name="Test User",
                organization_id=1
            )
            
            admin_user = self.create_test_user(
                email="admin@example.com",
                password="admin123",
                display_name="Admin User",
                organization_id=1
            )
            
            # Create test locations
            print("\n2. Creating test locations...")
            warehouse_location = self.create_test_location(
                display_name="Test Warehouse",
                organization_id=1
            )
            
            office_location = self.create_test_location(
                display_name="Test Office",
                organization_id=1
            )
            
            # Create test IoT scales
            print("\n3. Creating test IoT scales...")
            scale1 = self.create_test_iot_scale(
                scale_name="SCALE-001",
                password="scale123456",
                owner_id=test_user.id,
                location_id=warehouse_location.id
            )
            
            scale2 = self.create_test_iot_scale(
                scale_name="SCALE-002",
                password="scale789012",
                owner_id=admin_user.id,
                location_id=office_location.id
            )
            
            print("\n" + "=" * 50)
            print("✅ Test data setup completed successfully!")
            print("=" * 50)
            print("\nTest Data Summary:")
            print(f"📧 Test User: test@example.com / password123 (ID: {test_user.id})")
            print(f"👤 Admin User: admin@example.com / admin123 (ID: {admin_user.id})")
            print(f"🏢 Warehouse: {warehouse_location.display_name} (ID: {warehouse_location.id})")
            print(f"🏢 Office: {office_location.display_name} (ID: {office_location.id})")
            print(f"⚖️  Scale 1: {scale1.scale_name} / scale123456 (ID: {scale1.id})")
            print(f"⚖️  Scale 2: {scale2.scale_name} / scale789012 (ID: {scale2.id})")
            print("\n🚀 Ready for testing!")
            
        except Exception as e:
            print(f"❌ Error setting up test data: {str(e)}")
            raise
        finally:
            self.close_session()
    
    def cleanup_test_data(self):
        """Clean up test data"""
        print("Cleaning up test data...")
        
        with self.get_session() as session:
            try:
                # Delete test IoT scales
                session.query(IoTScale).filter(
                    IoTScale.scale_name.in_(["SCALE-001", "SCALE-002"])
                ).delete(synchronize_session=False)
                
                # Delete test locations
                session.query(UserLocation).filter(
                    UserLocation.display_name.in_(["Test Warehouse", "Test Office"]),
                    UserLocation.is_location == True
                ).delete(synchronize_session=False)
                
                # Delete test users
                session.query(UserLocation).filter(
                    UserLocation.email.in_(["test@example.com", "admin@example.com"]),
                    UserLocation.is_user == True
                ).delete(synchronize_session=False)
                
                session.commit()
                print("✅ Test data cleanup completed!")
                
            except Exception as e:
                print(f"❌ Error cleaning up test data: {str(e)}")
                session.rollback()
                raise

def main():
    """Main function"""
    if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        setup = TestDataSetup()
        setup.cleanup_test_data()
    else:
        setup = TestDataSetup()
        setup.setup_all_test_data()

if __name__ == "__main__":
    main()
