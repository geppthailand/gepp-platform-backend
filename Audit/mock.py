"""
Mock Transaction Generator for AI Audit Testing

This script generates test transactions with 6 different cases:
1. Correct: 4 transaction_records with correct materials and images
2. Incorrect No Images: Some/all transaction_records without images
3. Incorrect Image Type: Wrong waste type images
4. Incorrect Number: 1-3 transaction_records (not meeting 4 materials requirement)
5. Incorrect Waste Type: Wrong material_id but correct structure
6. Unknown Images: Correct structure but some images from Unknown folder

Features:
- Pre-uploads ALL images from each folder to S3 at startup
- Randomly selects from uploaded S3 URLs for each transaction (following test rules)
- Multi-threaded transaction creation (up to 100 concurrent threads)
- Thread-safe operations with proper locking
- Performance metrics and progress tracking
- Each transaction gets random variety while reusing uploaded images

Usage:
    Set JWT_TOKEN and populations below, then run:
    python mock.py
"""

import os
import random
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

# ============================================================
# CONFIGURATION - EDIT THESE VALUES
# ============================================================

# JWT Token for authentication (REQUIRED)
JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoyNiwib3JnYW5pemF0aW9uX2lkIjo4LCJlbWFpbCI6InRvcDNAdG9wLmNvbSIsInR5cGUiOiJhdXRoIiwiZXhwIjoxNzYwODM1MjEwLCJpYXQiOjE3NjA4MzQzMTB9.z2GvDYgE8J45U7_xFGGHh1egC83JWjYZ4RK-X6dU-SU"

# Number of transactions to generate for each case
CASE1_COUNT = 4210  # Correct transactions
CASE2_COUNT = 256   # No images
CASE3_COUNT = 128   # Wrong image type
CASE4_COUNT = 157   # Wrong count (1-3 materials)
CASE5_COUNT = 312  # Wrong waste type
CASE6_COUNT = 200   # Unknown waste images

# Debug mode - print full request payloads
DEBUG_MODE = True  # Set to True to see detailed API requests

# Threading configuration
MAX_THREADS = 100  # Maximum number of concurrent threads for API calls
USE_THREADING = True  # Set to False to run sequentially (for debugging)

# ============================================================

# API Configuration
API_URL = "https://obis666x3jacckmvlasisnwfgm0uaxxv.lambda-url.ap-southeast-1.on.aws/api/transactions"
ORGANIZATION_ID = 8
CREATED_BY_ID = 26

# Image folder mapping for correct materials
IMAGE_FOLDERS = {
    "General": "backend/Audit/General",      # category_id: 4, main_material_id: 11
    "Organic": "backend/Audit/Organic",      # category_id: 3, main_material_id: 10
    "Recyclable": "backend/Audit/Recyclable", # category_id: 1, main_material_id: 33
    "Hazardous": "backend/Audit/Hazardous",  # category_id: 5, main_material_id: 25
    "Unknown": "backend/Audit/Unknown"       # Unknown waste type
}

# Correct material configurations (4 required waste types)
CORRECT_MATERIALS = [
    {
        "material_id": 98,
        "main_material_id": 11,
        "category_id": 4,
        "folder": "General",
        "name": "General Waste"
    },
    {
        "material_id": 97,
        "main_material_id": 10,
        "category_id": 3,
        "folder": "Organic",
        "name": "Food and Plant Waste"
    },
    {
        "material_id": 298,
        "main_material_id": 33,
        "category_id": 1,
        "folder": "Recyclable",
        "name": "Non-Specific Recyclables"
    },
    {
        "material_id": 113,
        "main_material_id": 25,
        "category_id": 5,
        "folder": "Hazardous",
        "name": "Non-Specific Hazardous Waste"
    }
]

# All incorrect material IDs (for case 5)
INCORRECT_MATERIAL_IDS = [311, 310, 309, 308, 307, 306, 305, 304, 299, 298, 297, 289, 288, 287, 286, 285, 284, 273, 272, 263, 262, 261, 260, 259, 258, 257, 256, 255, 254, 253, 252, 251, 250, 249, 248, 247, 246, 245, 244, 243, 242, 241, 240, 239, 238, 237, 236, 235, 234, 233, 232, 231, 230, 229, 228, 227, 226, 225, 224, 223, 222, 221, 220, 219, 218, 217, 216, 215, 214, 213, 212, 211, 210, 209, 208, 207, 206, 205, 204, 203, 202, 201, 200, 199, 198, 197, 196, 195, 194, 193, 192, 191, 190, 189, 188, 187, 186, 160, 159, 158, 157, 156, 155, 154, 153, 152, 151, 150, 149, 148, 147, 146, 145, 144, 143, 142, 141, 140, 139, 138, 137, 136, 135, 134, 133, 132, 131, 130, 129, 128, 127, 126, 125, 124, 123, 122, 121, 120, 119, 118, 117, 116, 115, 114, 113, 111, 110, 109, 107, 106, 105, 104, 103, 102, 101, 100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 84, 83, 82, 81, 80, 79, 78, 77, 76, 75, 74, 73, 72, 71, 70, 69, 68, 67, 66, 65, 64, 63, 62, 61, 60, 59, 58, 57, 56, 55, 54, 53, 52, 51, 50, 49, 48, 47, 46, 45, 44, 43, 42, 41, 40, 39, 38, 37, 36, 35, 34, 33, 32, 31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]


def load_org_structure():
    """Load organization structure to get valid origin_ids (level-4 nodes)"""
    org_file = Path(__file__).parent / "org.jsonl"
    with open(org_file, 'r') as f:
        org_data = json.load(f)

    # Extract all level-4 nodeIds
    level4_nodes = []

    def extract_level4(nodes, level=1):
        for node in nodes:
            if level == 4:
                level4_nodes.append(node['nodeId'])
            if 'children' in node:
                extract_level4(node['children'], level + 1)

    extract_level4(org_data, level=1)
    return level4_nodes


def get_image_files(folder_name: str) -> List[str]:
    """Get all image files from a specific folder"""
    folder_path = Path(__file__).parent / folder_name
    if not folder_path.exists():
        print(f"Warning: Folder {folder_name} does not exist")
        return []

    image_extensions = ['.jpg', '.jpeg', '.png']
    images = []
    for ext in image_extensions:
        images.extend([str(f) for f in folder_path.glob(f'*{ext}')])
    return images


def random_date_in_range():
    """Generate random date between 2025-01-01 and 2025-10-15 with milliseconds"""
    start_date = datetime(2025, 1, 1)
    end_date = datetime(2025, 10, 15)
    delta = end_date - start_date
    random_days = random.randint(0, delta.days)
    random_seconds = random.randint(0, 86399)  # Random time of day
    random_microseconds = random.randint(0, 999999)  # Random microseconds
    random_date = start_date + timedelta(days=random_days, seconds=random_seconds, microseconds=random_microseconds)
    # Format with milliseconds (3 decimal places) like web interface: 2025-10-18T03:19:42.945Z
    return random_date.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + "Z"


def create_transaction_record(material_config: Dict, s3_urls: List[str] = None) -> Dict[str, Any]:
    """
    Create a single transaction record

    Args:
        material_config: Material configuration dict
        s3_urls: List of S3 URLs to use as images (already uploaded)
    """
    # Use integer weight to avoid Decimal + float errors in backend
    weight = random.randint(1, 100)

    # Use provided S3 URLs or empty list
    images = s3_urls if s3_urls is not None else []

    return {
        "material_id": material_config['material_id'],
        "main_material_id": material_config['main_material_id'],
        "category_id": material_config['category_id'],
        "unit": "กิโลกรัม",
        "origin_quantity": weight,
        "origin_weight_kg": weight,
        "images": images,
        "origin_price_per_unit": 0,
        "total_amount": 0,
        "transaction_type": "manual_input",
        "hazardous_level": 0,
        "notes": "test"
    }


def generate_case1_correct(origin_ids: List[int]) -> Dict[str, Any]:
    """Case 1: Correct transaction with 4 materials and correct images"""
    records = []

    for material_config in CORRECT_MATERIALS:
        # Randomly select from pre-uploaded S3 URLs for this folder
        if material_config['folder'] in folder_s3_urls and folder_s3_urls[material_config['folder']]:
            selected_s3_url = [random.choice(folder_s3_urls[material_config['folder']])]
        else:
            selected_s3_url = []
        record = create_transaction_record(material_config, selected_s3_url)
        records.append(record)

    return {
        "origin_id": random.choice(origin_ids),
        "transaction_method": "origin",
        "status": "pending",
        "transaction_date": random_date_in_range(),
        "notes": "Case 1: Correct transaction",
        "images": [],
        "records": records
    }


def generate_case2_no_images(origin_ids: List[int]) -> Dict[str, Any]:
    """Case 2: Transaction with missing images in some/all records"""
    records = []

    # Randomly decide how many records will have no images (1-4)
    num_without_images = random.randint(1, 4)
    records_to_remove_images = random.sample(range(4), num_without_images)

    for idx, material_config in enumerate(CORRECT_MATERIALS):
        if idx in records_to_remove_images:
            # No images for this record
            record = create_transaction_record(material_config, s3_urls=[])
        else:
            # Include correct images - randomly select from pre-uploaded S3 URLs
            if material_config['folder'] in folder_s3_urls and folder_s3_urls[material_config['folder']]:
                selected_s3_url = [random.choice(folder_s3_urls[material_config['folder']])]
            else:
                selected_s3_url = []
            record = create_transaction_record(material_config, selected_s3_url)
        records.append(record)

    return {
        "origin_id": random.choice(origin_ids),
        "transaction_method": "origin",
        "status": "pending",
        "transaction_date": random_date_in_range(),
        "notes": f"Case 2: Missing images ({num_without_images} records without images)",
        "images": [],
        "records": records
    }


def generate_case3_wrong_image_type(origin_ids: List[int]) -> Dict[str, Any]:
    """Case 3: Transaction with wrong waste type images"""
    records = []

    # Randomly decide how many records will have wrong images (1-4)
    num_wrong_images = random.randint(1, 4)
    records_with_wrong_images = random.sample(range(4), num_wrong_images)

    for idx, material_config in enumerate(CORRECT_MATERIALS):
        if idx in records_with_wrong_images:
            # Use wrong images - randomly select from wrong folder's S3 URLs
            wrong_folders = [f for f in IMAGE_FOLDERS.keys() if f != material_config['folder']]
            wrong_folder = random.choice(wrong_folders)
            if wrong_folder in folder_s3_urls and folder_s3_urls[wrong_folder]:
                selected_s3_url = [random.choice(folder_s3_urls[wrong_folder])]
            else:
                selected_s3_url = []
            record = create_transaction_record(material_config, selected_s3_url)
        else:
            # Use correct images - randomly select from correct folder's S3 URLs
            if material_config['folder'] in folder_s3_urls and folder_s3_urls[material_config['folder']]:
                selected_s3_url = [random.choice(folder_s3_urls[material_config['folder']])]
            else:
                selected_s3_url = []
            record = create_transaction_record(material_config, selected_s3_url)
        records.append(record)

    return {
        "origin_id": random.choice(origin_ids),
        "transaction_method": "origin",
        "status": "pending",
        "transaction_date": random_date_in_range(),
        "notes": f"Case 3: Wrong image types ({num_wrong_images} records with wrong images)",
        "images": [],
        "records": records
    }


def generate_case4_wrong_count(origin_ids: List[int]) -> Dict[str, Any]:
    """Case 4: Transaction with 1-3 records (not meeting 4 materials requirement)"""
    # Randomly select 1-3 materials
    num_materials = random.randint(1, 3)
    selected_materials = random.sample(CORRECT_MATERIALS, num_materials)

    records = []
    for material_config in selected_materials:
        # Randomly select from pre-uploaded S3 URLs
        if material_config['folder'] in folder_s3_urls and folder_s3_urls[material_config['folder']]:
            selected_s3_url = [random.choice(folder_s3_urls[material_config['folder']])]
        else:
            selected_s3_url = []
        record = create_transaction_record(material_config, selected_s3_url)
        records.append(record)

    return {
        "origin_id": random.choice(origin_ids),
        "transaction_method": "origin",
        "status": "pending",
        "transaction_date": random_date_in_range(),
        "notes": f"Case 4: Incorrect count ({num_materials} materials instead of 4)",
        "images": [],
        "records": records
    }


def generate_case5_wrong_waste_type(origin_ids: List[int]) -> Dict[str, Any]:
    """Case 5: Transaction with wrong material_id but correct structure"""
    records = []

    for material_config in CORRECT_MATERIALS:
        # Use wrong material_id but keep other properties correct
        wrong_material_id = random.choice(INCORRECT_MATERIAL_IDS)
        wrong_config = material_config.copy()
        wrong_config['material_id'] = wrong_material_id

        # Randomly select from pre-uploaded S3 URLs
        if material_config['folder'] in folder_s3_urls and folder_s3_urls[material_config['folder']]:
            selected_s3_url = [random.choice(folder_s3_urls[material_config['folder']])]
        else:
            selected_s3_url = []
        record = create_transaction_record(wrong_config, selected_s3_url)
        records.append(record)

    return {
        "origin_id": random.choice(origin_ids),
        "transaction_method": "origin",
        "status": "pending",
        "transaction_date": random_date_in_range(),
        "notes": "Case 5: Wrong material IDs",
        "images": [],
        "records": records
    }


def generate_case6_unknown_images(origin_ids: List[int]) -> Dict[str, Any]:
    """Case 6: Correct structure but some images from Unknown folder"""
    records = []

    # Randomly decide how many records will have unknown images (1-4)
    num_unknown_images = random.randint(1, 4)
    records_with_unknown_images = random.sample(range(4), num_unknown_images)

    for idx, material_config in enumerate(CORRECT_MATERIALS):
        if idx in records_with_unknown_images:
            # Use image from Unknown folder - randomly select from pre-uploaded S3 URLs
            if "Unknown" in folder_s3_urls and folder_s3_urls["Unknown"]:
                selected_s3_url = [random.choice(folder_s3_urls["Unknown"])]
            else:
                selected_s3_url = []
            record = create_transaction_record(material_config, selected_s3_url)
        else:
            # Use correct images - randomly select from correct folder's S3 URLs
            if material_config['folder'] in folder_s3_urls and folder_s3_urls[material_config['folder']]:
                selected_s3_url = [random.choice(folder_s3_urls[material_config['folder']])]
            else:
                selected_s3_url = []
            record = create_transaction_record(material_config, selected_s3_url)
        records.append(record)

    return {
        "origin_id": random.choice(origin_ids),
        "transaction_method": "origin",
        "status": "pending",
        "transaction_date": random_date_in_range(),
        "notes": f"Case 6: Unknown waste images ({num_unknown_images} records with unknown images)",
        "images": [],
        "records": records
    }


def upload_image_to_s3(image_path: str, jwt_token: str) -> str:
    """Upload image to S3 and return the S3 URL"""
    # First, get presigned URL
    presigned_url = "https://obis666x3jacckmvlasisnwfgm0uaxxv.lambda-url.ap-southeast-1.on.aws/api/transactions/presigneds"

    filename = os.path.basename(image_path)

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "file_names": [filename],
        "expiration_seconds": 3600
    }

    response = requests.post(presigned_url, json=payload, headers=headers)

    if response.status_code != 200:
        print(f"Failed to get presigned URL: {response.text}")
        return None

    presigned_data = response.json()

    if not presigned_data.get('success'):
        print(f"Presigned URL request failed: {presigned_data}")
        return None

    # Get the presigned URL data
    url_data = presigned_data['data']['presigned_urls'][0]
    upload_url = url_data['upload_url']
    upload_fields = url_data['upload_fields']
    final_s3_url = url_data['final_s3_url']

    # Upload file to S3
    with open(image_path, 'rb') as f:
        files = {'file': f}
        upload_response = requests.post(upload_url, data=upload_fields, files=files)

    if upload_response.status_code in [200, 204]:
        return final_s3_url
    else:
        print(f"Failed to upload image: {upload_response.status_code}")
        return None


# Thread-safe print lock
print_lock = threading.Lock()

# Global image cache: maps local file path to S3 URL
image_cache = {}
image_cache_lock = threading.Lock()

# Global folder to S3 URLs mapping: folder name -> list of S3 URLs
folder_s3_urls = {}

def thread_safe_print(message: str):
    """Thread-safe print function"""
    with print_lock:
        print(message)


def preload_images(jwt_token: str) -> Dict[str, List[str]]:
    """
    Pre-upload ALL images from each folder to S3 and cache the URLs.
    Returns a mapping of folder name to list of S3 URLs.
    """
    print("\n" + "="*60)
    print("PRE-UPLOADING ALL IMAGES")
    print("="*60)

    global folder_s3_urls
    folder_s3_urls = {}

    for folder_name, folder_path in IMAGE_FOLDERS.items():
        images = get_image_files(folder_name)
        if images:
            print(f"Uploading {len(images)} images from {folder_name}...")
            s3_urls = []

            for img_path in images:
                s3_url = upload_image_to_s3(img_path, jwt_token)
                if s3_url:
                    # Add to cache
                    image_cache[img_path] = s3_url
                    s3_urls.append(s3_url)

            if s3_urls:
                folder_s3_urls[folder_name] = s3_urls
                print(f"  ✓ {folder_name}: {len(s3_urls)} images uploaded")
            else:
                print(f"  ✗ Failed to upload images from {folder_name}")
        else:
            print(f"  ✗ No images found in {folder_name}")

    total_uploaded = sum(len(urls) for urls in folder_s3_urls.values())
    print(f"\nPre-uploaded {total_uploaded} images from {len(folder_s3_urls)} folders successfully")
    print("="*60)

    return folder_s3_urls


def create_transaction(transaction_data: Dict[str, Any], jwt_token: str, transaction_num: int = 0) -> Dict[str, Any]:
    """Create transaction via API (thread-safe)"""
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    # Collect all images from records for transaction level (images are already S3 URLs)
    all_transaction_images = []
    for record in transaction_data['records']:
        if record.get('images'):
            all_transaction_images.extend(record['images'])

    # Add all images to transaction level (matching web interface structure)
    transaction_data['images'] = all_transaction_images

    if DEBUG_MODE:
        with print_lock:
            print(f"\n  [{transaction_num}] DEBUG - Request Payload:")
            print(json.dumps(transaction_data, indent=2, ensure_ascii=False))
            print()

    if not DEBUG_MODE:
        thread_safe_print(f"  [{transaction_num}] Sending to API...")

    response = requests.post(API_URL, json=transaction_data, headers=headers)

    result = {
        'status_code': response.status_code,
        'response': None
    }

    if response.status_code == 200:
        try:
            result['response'] = response.json()
            if DEBUG_MODE:
                with print_lock:
                    print(f"\n  [{transaction_num}] DEBUG - Response:")
                    print(json.dumps(result['response'], indent=2, ensure_ascii=False))
                    print()

            # Check if outer success is true but data.success is false (validation error)
            if result['response'].get('success'):
                data = result['response'].get('data', {})

                # Check if data itself has a success field that's false
                if isinstance(data, dict) and data.get('success') == False:
                    thread_safe_print(f"  [{transaction_num}] ✗ VALIDATION ERROR: {data.get('message')}")
                elif isinstance(data, dict) and 'id' in data:
                    transaction_id = data.get('id')
                    thread_safe_print(f"  [{transaction_num}] ✓ Created ID: {transaction_id}")
                    result['success'] = True
                    result['transaction_id'] = transaction_id
                else:
                    thread_safe_print(f"  [{transaction_num}] ✓ Success")
                    result['success'] = True
            else:
                thread_safe_print(f"  [{transaction_num}] ✗ Failed: {result['response'].get('message')}")
        except Exception as e:
            result['response'] = response.text
            thread_safe_print(f"  [{transaction_num}] ✗ Error: {e}")
    else:
        result['response'] = response.text
        thread_safe_print(f"  [{transaction_num}] ✗ HTTP {response.status_code}")

    return result


def process_transactions_batch(generator_func, count: int, case_name: str, origin_ids: List[int], stats: Dict) -> None:
    """Process a batch of transactions with threading"""
    if count <= 0:
        return

    print(f"\n=== Generating {count} {case_name} transactions ===")
    start_time = time.time()

    if USE_THREADING:
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=min(MAX_THREADS, count)) as executor:
            # Submit all tasks
            futures = {}
            for i in range(count):
                transaction = generator_func(origin_ids)
                future = executor.submit(create_transaction, transaction, JWT_TOKEN, i+1)
                futures[future] = i+1

            # Wait for all to complete
            for future in as_completed(futures):
                transaction_num = futures[future]
                try:
                    result = future.result()
                    if result.get('success'):
                        stats[f'{case_name}_success'] += 1
                    else:
                        stats[f'{case_name}_failed'] += 1
                except Exception as e:
                    stats[f'{case_name}_failed'] += 1
                    thread_safe_print(f"  [{transaction_num}] ✗ Exception: {e}")
    else:
        # Sequential processing (for debugging)
        for i in range(count):
            print(f"Creating {case_name} transaction {i+1}/{count}...")
            transaction = generator_func(origin_ids)
            result = create_transaction(transaction, JWT_TOKEN, i+1)
            if result.get('success'):
                stats[f'{case_name}_success'] += 1
            else:
                stats[f'{case_name}_failed'] += 1

    elapsed = time.time() - start_time
    success = stats[f'{case_name}_success']
    failed = stats[f'{case_name}_failed']
    print(f"Completed {case_name}: {success} success, {failed} failed in {elapsed:.2f}s ({success/elapsed:.1f} tx/s)")


def main():
    # Validate JWT token
    if JWT_TOKEN == "YOUR_JWT_TOKEN_HERE":
        print("ERROR: Please set your JWT_TOKEN in the configuration section at the top of this file")
        return

    print("="*60)
    print("Mock Transaction Generator")
    print("="*60)
    print(f"Case 1 (Correct):          {CASE1_COUNT} transactions")
    print(f"Case 2 (No Images):        {CASE2_COUNT} transactions")
    print(f"Case 3 (Wrong Image Type): {CASE3_COUNT} transactions")
    print(f"Case 4 (Wrong Count):      {CASE4_COUNT} transactions")
    print(f"Case 5 (Wrong Waste Type): {CASE5_COUNT} transactions")
    print(f"Case 6 (Unknown Images):   {CASE6_COUNT} transactions")
    print(f"Total:                     {CASE1_COUNT + CASE2_COUNT + CASE3_COUNT + CASE4_COUNT + CASE5_COUNT + CASE6_COUNT} transactions")
    print("="*60)

    # Load organization structure
    print("\nLoading organization structure...")
    origin_ids = load_org_structure()
    print(f"Found {len(origin_ids)} valid origin locations")

    # Pre-upload images (1 per folder) to cache
    preload_images(JWT_TOKEN)

    # Statistics
    stats = {
        'case1_success': 0,
        'case1_failed': 0,
        'case2_success': 0,
        'case2_failed': 0,
        'case3_success': 0,
        'case3_failed': 0,
        'case4_success': 0,
        'case4_failed': 0,
        'case5_success': 0,
        'case5_failed': 0,
        'case6_success': 0,
        'case6_failed': 0
    }

    print(f"\nThreading: {'ENABLED' if USE_THREADING else 'DISABLED'}")
    if USE_THREADING:
        print(f"Max concurrent threads: {MAX_THREADS}")
    print()

    overall_start = time.time()

    # Process each case using batch threading
    process_transactions_batch(generate_case1_correct, CASE1_COUNT, 'case1', origin_ids, stats)
    process_transactions_batch(generate_case2_no_images, CASE2_COUNT, 'case2', origin_ids, stats)
    process_transactions_batch(generate_case3_wrong_image_type, CASE3_COUNT, 'case3', origin_ids, stats)
    process_transactions_batch(generate_case4_wrong_count, CASE4_COUNT, 'case4', origin_ids, stats)
    process_transactions_batch(generate_case5_wrong_waste_type, CASE5_COUNT, 'case5', origin_ids, stats)
    process_transactions_batch(generate_case6_unknown_images, CASE6_COUNT, 'case6', origin_ids, stats)

    overall_elapsed = time.time() - overall_start

# Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    total_success = sum([v for k, v in stats.items() if 'success' in k])
    total_failed = sum([v for k, v in stats.items() if 'failed' in k])

    print(f"Case 1 (Correct):          {stats['case1_success']} success, {stats['case1_failed']} failed")
    print(f"Case 2 (No Images):        {stats['case2_success']} success, {stats['case2_failed']} failed")
    print(f"Case 3 (Wrong Image Type): {stats['case3_success']} success, {stats['case3_failed']} failed")
    print(f"Case 4 (Wrong Count):      {stats['case4_success']} success, {stats['case4_failed']} failed")
    print(f"Case 5 (Wrong Waste Type): {stats['case5_success']} success, {stats['case5_failed']} failed")
    print(f"Case 6 (Unknown Images):   {stats['case6_success']} success, {stats['case6_failed']} failed")
    print(f"\nTotal: {total_success} success, {total_failed} failed")
    print(f"Overall time: {overall_elapsed:.2f}s")
    if total_success > 0:
        print(f"Average rate: {total_success/overall_elapsed:.1f} transactions/second")
    print(f"\nImage cache: {len(image_cache)} unique images uploaded and reused")
    print("="*60)


if __name__ == "__main__":
    main()
