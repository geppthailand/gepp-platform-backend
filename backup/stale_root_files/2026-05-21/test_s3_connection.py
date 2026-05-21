#!/usr/bin/env python3
"""
Test S3 Connection and Presigned URL Generation
Run this script to verify AWS credentials and S3 bucket access
"""

import os
import boto3
import logging
from botocore.exceptions import ClientError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_s3_connection():
    """Test basic S3 connection and bucket access"""

    print("🔍 Testing S3 Connection...")
    print("=" * 50)

    # Check environment variables
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_region = os.getenv('AWS_REGION', 'us-east-1')
    bucket_name = os.getenv('S3_BUCKET_NAME', 'prod-gepp-platform-assets')

    print(f"📋 Configuration:")
    print(f"   AWS_ACCESS_KEY_ID: {'✅ Set' if aws_access_key else '❌ Not set'}")
    print(f"   AWS_SECRET_ACCESS_KEY: {'✅ Set' if aws_secret_key else '❌ Not set'}")
    print(f"   AWS_REGION: {aws_region}")
    print(f"   S3_BUCKET_NAME: {bucket_name}")
    print()

    if not aws_access_key or not aws_secret_key:
        print("⚠️  AWS credentials not found in environment variables")
        print("   Using default credential chain (IAM roles, ~/.aws/credentials, etc.)")
        s3_client = boto3.client('s3', region_name=aws_region)
    else:
        print("✅ Using explicit AWS credentials")
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region
        )

    # Test 0: List accessible buckets first
    print("🧪 Test 0: Listing accessible buckets...")
    try:
        response = s3_client.list_buckets()
        buckets = [bucket['Name'] for bucket in response.get('Buckets', [])]
        print(f"   ✅ Found {len(buckets)} accessible buckets:")
        for bucket in buckets[:10]:  # Show first 10
            print(f"      - {bucket}")

        if buckets:
            print(f"\n   💡 You can use any of these buckets instead of: {bucket_name}")
    except ClientError as e:
        print(f"   ❌ Cannot list buckets: {str(e)}")

    # Test 1: Check bucket access
    print(f"\n🧪 Test 1: Checking specific bucket access: {bucket_name}")
    try:
        response = s3_client.head_bucket(Bucket=bucket_name)
        print(f"   ✅ Successfully accessed bucket: {bucket_name}")
        print(f"   📊 Response: {response}")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f"   ❌ Cannot access bucket: {bucket_name}")
        print(f"   🚨 Error Code: {error_code}")
        print(f"   💬 Error Message: {str(e)}")

        if error_code == '403':
            print("   💡 This usually means:")
            print("      - AWS credentials don't have permission to access this bucket")
            print("      - Bucket policy restricts access")
            print("      - IAM user/role lacks S3 permissions")
        elif error_code == '404':
            print("   💡 This usually means:")
            print("      - Bucket doesn't exist")
            print("      - Bucket name is incorrect")
            print("      - Bucket is in a different region")

        return False

    # Test 2: Generate presigned URL
    print("\n🧪 Test 2: Generating presigned URL...")
    try:
        test_key = "test/sample-file.txt"
        response = s3_client.generate_presigned_post(
            Bucket=bucket_name,
            Key=test_key,
            Fields={
                'Content-Type': 'text/plain'
            },
            Conditions=[
                {"bucket": bucket_name},
                ["starts-with", "$key", test_key],
                {"Content-Type": "text/plain"},
                ["content-length-range", 1, 1024]  # 1 byte to 1KB
            ],
            ExpiresIn=3600
        )

        print("   ✅ Successfully generated presigned URL!")
        print(f"   🔗 Upload URL: {response['url']}")
        print(f"   📝 Fields: {list(response['fields'].keys())}")

    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f"   ❌ Failed to generate presigned URL")
        print(f"   🚨 Error Code: {error_code}")
        print(f"   💬 Error Message: {str(e)}")
        return False

    # Test 3: List bucket contents (optional)
    print("\n🧪 Test 3: Testing bucket permissions...")
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=5)
        object_count = response.get('KeyCount', 0)
        print(f"   ✅ Successfully listed bucket contents")
        print(f"   📦 Found {object_count} objects (showing max 5)")

        if 'Contents' in response:
            for obj in response['Contents'][:3]:  # Show first 3 objects
                print(f"      - {obj['Key']} ({obj['Size']} bytes)")

    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f"   ⚠️  Cannot list bucket contents (Error: {error_code})")
        print("   💡 This might be okay if the bucket policy restricts ListObject permission")
        print("      but allows PutObject for presigned URLs")

    print("\n🎉 S3 Connection Test Complete!")
    print("   If presigned URL generation succeeded, file uploads should work.")

    return True

if __name__ == "__main__":
    test_s3_connection()