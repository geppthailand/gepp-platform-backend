"""
Examples of how to use the organizational tree structure in UserLocation model
"""

from database import SessionLocal
from models import UserLocation, user_subusers
from sqlalchemy import text

def create_organizational_structure():
    """
    Create a sample organizational structure:
    
    GEPP Corp (CEO)
    ├── Regional Manager North
    │   ├── Collector A
    │   └── Collector B  
    ├── Regional Manager South
    │   ├── Recycler A
    │   └── Recycler B
    └── Operations Manager
        ├── Sorter A
        └── Sorter B
    """
    db = SessionLocal()
    
    try:
        # Create root organization (CEO)
        ceo = UserLocation(
            is_user=True,
            is_location=False,
            name_en="GEPP Corporation",
            display_name="CEO Office",
            email="ceo@gepp.com",
            username="ceo",
            password="hashed_password",
            organization_level=0,
            organization_path="/",
            business_type="headquarters"
        )
        db.add(ceo)
        db.flush()  # Get the ID
        
        # Update the organization path with actual ID
        ceo.organization_path = f"/{ceo.id}/"
        
        # Create Regional Managers
        rm_north = UserLocation(
            is_user=True,
            is_location=True,
            name_en="Regional Manager North",
            display_name="RM North",
            email="rm.north@gepp.com",
            username="rm_north",
            password="hashed_password",
            parent_user_id=ceo.id,
            organization_level=1,
            organization_path=f"/{ceo.id}/",
            functions="management,collection",
            business_type="regional_office"
        )
        
        rm_south = UserLocation(
            is_user=True,
            is_location=True,
            name_en="Regional Manager South",
            display_name="RM South",
            email="rm.south@gepp.com",
            username="rm_south", 
            password="hashed_password",
            parent_user_id=ceo.id,
            organization_level=1,
            organization_path=f"/{ceo.id}/",
            functions="management,recycling",
            business_type="regional_office"
        )
        
        ops_manager = UserLocation(
            is_user=True,
            is_location=True,
            name_en="Operations Manager",
            display_name="Ops Manager",
            email="ops@gepp.com",
            username="ops_manager",
            password="hashed_password",
            parent_user_id=ceo.id,
            organization_level=1,
            organization_path=f"/{ceo.id}/",
            functions="management,sorting",
            business_type="operations"
        )
        
        db.add_all([rm_north, rm_south, ops_manager])
        db.flush()
        
        # Update paths for managers
        for manager in [rm_north, rm_south, ops_manager]:
            manager.organization_path = f"/{ceo.id}/{manager.id}/"
        
        # Create operational units under managers
        collector_a = UserLocation(
            is_user=True,
            is_location=True,
            name_en="Collector A",
            display_name="Collector A",
            email="collector.a@gepp.com",
            username="collector_a",
            password="hashed_password",
            parent_user_id=rm_north.id,
            organization_level=2,
            organization_path=f"/{ceo.id}/{rm_north.id}/",
            functions="collector",
            business_type="collection_point"
        )
        
        collector_b = UserLocation(
            is_user=True,
            is_location=True,
            name_en="Collector B", 
            display_name="Collector B",
            email="collector.b@gepp.com",
            username="collector_b",
            password="hashed_password",
            parent_user_id=rm_north.id,
            organization_level=2,
            organization_path=f"/{ceo.id}/{rm_north.id}/",
            functions="collector",
            business_type="collection_point"
        )
        
        recycler_a = UserLocation(
            is_user=True,
            is_location=True,
            name_en="Recycler A",
            display_name="Recycler A",
            email="recycler.a@gepp.com",
            username="recycler_a",
            password="hashed_password",
            parent_user_id=rm_south.id,
            organization_level=2,
            organization_path=f"/{ceo.id}/{rm_south.id}/",
            functions="recycler",
            business_type="recycling_facility"
        )
        
        recycler_b = UserLocation(
            is_user=True,
            is_location=True,
            name_en="Recycler B",
            display_name="Recycler B", 
            email="recycler.b@gepp.com",
            username="recycler_b",
            password="hashed_password",
            parent_user_id=rm_south.id,
            organization_level=2,
            organization_path=f"/{ceo.id}/{rm_south.id}/",
            functions="recycler",
            business_type="recycling_facility"
        )
        
        sorter_a = UserLocation(
            is_user=True,
            is_location=True,
            name_en="Sorter A",
            display_name="Sorter A",
            email="sorter.a@gepp.com",
            username="sorter_a",
            password="hashed_password",
            parent_user_id=ops_manager.id,
            organization_level=2,
            organization_path=f"/{ceo.id}/{ops_manager.id}/",
            functions="sorter",
            business_type="sorting_facility"
        )
        
        sorter_b = UserLocation(
            is_user=True,
            is_location=True,
            name_en="Sorter B",
            display_name="Sorter B",
            email="sorter.b@gepp.com",
            username="sorter_b",
            password="hashed_password",
            parent_user_id=ops_manager.id,
            organization_level=2,
            organization_path=f"/{ceo.id}/{ops_manager.id}/",
            functions="sorter",
            business_type="sorting_facility"
        )
        
        db.add_all([collector_a, collector_b, recycler_a, recycler_b, sorter_a, sorter_b])
        db.flush()
        
        # Update final paths
        for unit in [collector_a, collector_b]:
            unit.organization_path = f"/{ceo.id}/{rm_north.id}/{unit.id}/"
            
        for unit in [recycler_a, recycler_b]:
            unit.organization_path = f"/{ceo.id}/{rm_south.id}/{unit.id}/"
            
        for unit in [sorter_a, sorter_b]:
            unit.organization_path = f"/{ceo.id}/{ops_manager.id}/{unit.id}/"
        
        # Add subuser relationships using the many-to-many table
        ceo.subusers.extend([rm_north, rm_south, ops_manager])
        rm_north.subusers.extend([collector_a, collector_b])
        rm_south.subusers.extend([recycler_a, recycler_b])
        ops_manager.subusers.extend([sorter_a, sorter_b])
        
        db.commit()
        print("Organizational structure created successfully!")
        return ceo.id
        
    except Exception as e:
        db.rollback()
        print(f"Error creating organizational structure: {e}")
        return None
    finally:
        db.close()

def query_organizational_structure(root_user_id):
    """Query and display the organizational structure"""
    db = SessionLocal()
    
    try:
        # Get root user
        root = db.query(UserLocation).get(root_user_id)
        if not root:
            print("Root user not found")
            return
            
        print(f"Organization Root: {root.display_name}")
        
        # Get all descendants using recursive CTE
        descendants = root.get_all_descendants(db)
        
        print("\nOrganizational Tree:")
        for desc in descendants:
            indent = "  " * (desc.organization_level - 1)
            print(f"{indent}├── {desc.display_name} (Level {desc.organization_level})")
        
        # Query by organizational level
        print(f"\nLevel 1 (Direct reports to {root.display_name}):")
        level_1_users = db.query(UserLocation).filter(
            UserLocation.parent_user_id == root_user_id,
            UserLocation.is_active == True
        ).all()
        
        for user in level_1_users:
            print(f"  - {user.display_name}: {user.functions}")
            
        # Query all collectors in the organization
        print(f"\nAll Collectors in Organization:")
        collectors = db.query(UserLocation).filter(
            UserLocation.organization_path.like(f"/{root_user_id}/%"),
            UserLocation.functions.contains("collector"),
            UserLocation.is_active == True
        ).all()
        
        for collector in collectors:
            print(f"  - {collector.display_name} at level {collector.organization_level}")
            
        # Query using subuser relationships
        print(f"\nDirect subusers of {root.display_name}:")
        for subuser in root.subusers:
            print(f"  - {subuser.display_name}")
            print(f"    └── Has {len(subuser.subusers)} subusers")
            
    except Exception as e:
        print(f"Error querying organizational structure: {e}")
    finally:
        db.close()

def manage_subusers_example():
    """Example of managing subusers dynamically"""
    db = SessionLocal()
    
    try:
        # Find a manager
        manager = db.query(UserLocation).filter(
            UserLocation.display_name == "RM North"
        ).first()
        
        if not manager:
            print("Manager not found")
            return
            
        # Create a new collector
        new_collector = UserLocation(
            is_user=True,
            is_location=True,
            name_en="Collector C",
            display_name="Collector C",
            email="collector.c@gepp.com",
            username="collector_c",
            password="hashed_password",
            functions="collector",
            business_type="collection_point"
        )
        
        db.add(new_collector)
        db.flush()
        
        # Add as subuser using the method
        manager.add_subuser(new_collector)
        
        db.commit()
        print(f"Added {new_collector.display_name} as subuser of {manager.display_name}")
        print(f"New collector's organizational path: {new_collector.organization_path}")
        print(f"New collector's level: {new_collector.organization_level}")
        
    except Exception as e:
        db.rollback()
        print(f"Error managing subusers: {e}")
    finally:
        db.close()

def waste_transaction_flow_example():
    """Example showing waste transaction flow between users in the organization"""
    db = SessionLocal()
    
    try:
        # Find source (collector) and destination (recycler)
        collector = db.query(UserLocation).filter(
            UserLocation.functions.contains("collector"),
            UserLocation.is_location == True
        ).first()
        
        recycler = db.query(UserLocation).filter(
            UserLocation.functions.contains("recycler"),
            UserLocation.is_location == True  
        ).first()
        
        if collector and recycler:
            print("Waste Transaction Flow:")
            print(f"Source: {collector.display_name} (Level {collector.organization_level})")
            print(f"  └── Organization Path: {collector.organization_path}")
            print(f"Destination: {recycler.display_name} (Level {recycler.organization_level})")
            print(f"  └── Organization Path: {recycler.organization_path}")
            
            # Check if they're in the same organization
            collector_root = collector.get_organization_root(db)
            recycler_root = recycler.get_organization_root(db)
            
            if collector_root.id == recycler_root.id:
                print(f"✓ Both belong to the same organization: {collector_root.display_name}")
            else:
                print("✗ Different organizations")
                
    except Exception as e:
        print(f"Error in waste transaction flow example: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # Create the organizational structure
    root_id = create_organizational_structure()
    
    if root_id:
        # Query and display the structure
        query_organizational_structure(root_id)
        
        # Demonstrate subuser management
        manage_subusers_example()
        
        # Show waste transaction flow
        waste_transaction_flow_example()