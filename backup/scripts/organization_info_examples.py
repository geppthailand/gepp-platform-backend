"""
Examples of how to use the Organization and OrganizationInfo models
"""

from database import SessionLocal
from models import Organization, OrganizationInfo, UserLocation

def create_organization_with_info():
    """Create an organization with detailed information"""
    db = SessionLocal()
    
    try:
        # Create organization info first
        org_info = OrganizationInfo(
            company_name="Green Earth Recycling Co., Ltd.",
            company_name_th="บริษัท กรีนเอิร์ธ รีไซเคิลลิ่ง จำกัด",
            company_name_en="Green Earth Recycling Co., Ltd.",
            display_name="Green Earth Recycling",
            
            # Business details
            business_type="waste_management",
            business_industry="environmental_services",
            business_sub_industry="waste_recycling",
            account_type="corporate",
            
            # Legal information
            tax_id="0123456789012",
            business_registration_certificate="BRC-2024-001234",
            
            # Contact information
            company_phone="+66-2-123-4567",
            company_email="info@greenearth.co.th",
            
            # Address
            address="123 Green Street, Eco District, Bangkok 10110",
            country_id=212,  # Thailand
            
            # Images
            profile_image_url="https://example.com/logos/greenearth.png",
            company_logo_url="https://example.com/logos/greenearth-logo.png",
            
            # Additional info
            project_id="GE-2024-001",
            use_purpose="Corporate waste management and recycling services",
            footprint=1250.50
        )
        
        db.add(org_info)
        db.flush()  # Get the ID
        
        # Create organization
        organization = Organization(
            name="Green Earth Recycling",
            description="Leading waste management and recycling company in Thailand",
            organization_info_id=org_info.id
        )
        
        db.add(organization)
        db.flush()
        
        # Create some user-locations under this organization
        ceo = UserLocation(
            is_user=True,
            is_location=False,
            display_name="CEO - Green Earth",
            email="ceo@greenearth.co.th",
            username="ceo_greenearth",
            password="hashed_password",
            organization_id=organization.id,
            organization_level=0,
            organization_path=f"/{organization.id}/"
        )
        
        recycling_center = UserLocation(
            is_user=True,
            is_location=True,
            name_en="Green Earth Recycling Center - Bangkok",
            display_name="Recycling Center Bangkok",
            email="bangkok@greenearth.co.th",
            username="rc_bangkok",
            password="hashed_password",
            organization_id=organization.id,
            functions="recycler,sorter",
            business_type="recycling_facility",
            address="456 Industrial Road, Bangkok",
            country_id=212
        )
        
        db.add_all([ceo, recycling_center])
        db.commit()
        
        print("✅ Organization created successfully!")
        print(f"Organization: {organization.name}")
        print(f"Company Name: {org_info.company_name}")
        print(f"Tax ID: {org_info.tax_id}")
        print(f"Contact: {org_info.company_email}")
        
        return organization.id
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating organization: {e}")
        return None
    finally:
        db.close()

def query_organization_details(org_id):
    """Query organization with all related information"""
    db = SessionLocal()
    
    try:
        # Get organization with info
        org = db.query(Organization).filter(Organization.id == org_id).first()
        
        if not org:
            print("Organization not found")
            return
        
        print(f"\n📋 Organization Details:")
        print(f"Name: {org.name}")
        print(f"Description: {org.description}")
        
        if org.organization_info:
            info = org.organization_info
            print(f"\n🏢 Company Information:")
            print(f"Company Name (TH): {info.company_name_th}")
            print(f"Company Name (EN): {info.company_name_en}")
            print(f"Display Name: {info.display_name}")
            print(f"Business Type: {info.business_type}")
            print(f"Industry: {info.business_industry}")
            print(f"Tax ID: {info.tax_id}")
            print(f"Email: {info.company_email}")
            print(f"Phone: {info.company_phone}")
            print(f"Address: {info.address}")
            
        # Get all user-locations in this organization
        user_locations = db.query(UserLocation).filter(
            UserLocation.organization_id == org_id,
            UserLocation.is_active == True
        ).all()
        
        print(f"\n👥 Organization Members ({len(user_locations)}):")
        for ul in user_locations:
            user_type = []
            if ul.is_user:
                user_type.append("User")
            if ul.is_location:
                user_type.append("Location")
            
            print(f"  - {ul.display_name} ({'/'.join(user_type)})")
            if ul.functions:
                print(f"    Functions: {ul.functions}")
            if ul.email:
                print(f"    Email: {ul.email}")
                
    except Exception as e:
        print(f"❌ Error querying organization: {e}")
    finally:
        db.close()

def update_organization_info(org_id, updates):
    """Update organization information"""
    db = SessionLocal()
    
    try:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        
        if not org or not org.organization_info:
            print("Organization or organization info not found")
            return False
        
        # Update organization info fields
        for field, value in updates.items():
            if hasattr(org.organization_info, field):
                setattr(org.organization_info, field, value)
        
        db.commit()
        print("✅ Organization info updated successfully!")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error updating organization info: {e}")
        return False
    finally:
        db.close()

def list_organizations_by_business_type(business_type):
    """List all organizations by business type"""
    db = SessionLocal()
    
    try:
        orgs = db.query(Organization).join(OrganizationInfo).filter(
            OrganizationInfo.business_type == business_type,
            Organization.is_active == True
        ).all()
        
        print(f"\n🏭 Organizations with business type '{business_type}' ({len(orgs)}):")
        
        for org in orgs:
            print(f"  - {org.name}")
            if org.organization_info:
                print(f"    Company: {org.organization_info.company_name}")
                print(f"    Industry: {org.organization_info.business_industry}")
                print(f"    Contact: {org.organization_info.company_email}")
        
        return orgs
        
    except Exception as e:
        print(f"❌ Error listing organizations: {e}")
        return []
    finally:
        db.close()

if __name__ == "__main__":
    print("🏢 Organization Info Management Examples")
    print("=" * 50)
    
    # Create organization with detailed info
    org_id = create_organization_with_info()
    
    if org_id:
        # Query organization details
        query_organization_details(org_id)
        
        # Update organization info
        updates = {
            'footprint': 1500.75,
            'company_phone': '+66-2-987-6543',
            'use_purpose': 'Updated: Comprehensive waste management and recycling services across Thailand'
        }
        update_organization_info(org_id, updates)
        
        # List organizations by business type
        list_organizations_by_business_type('waste_management')