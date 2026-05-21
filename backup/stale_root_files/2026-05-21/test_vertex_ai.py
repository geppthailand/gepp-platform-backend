#!/usr/bin/env python3
"""
Test script for Vertex AI configuration
Run this to verify your Vertex AI setup is working correctly
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_vertex_ai_connection():
    """Test Vertex AI connection and configuration"""
    print("=" * 60)
    print("Vertex AI Configuration Test")
    print("=" * 60)

    # Check environment variables
    project_id = os.getenv('VERTEX_AI_PROJECT_ID') or os.getenv('GOOGLE_CLOUD_PROJECT')
    location = os.getenv('VERTEX_AI_LOCATION', 'us-central1')
    credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

    print("\n1. Checking Environment Variables...")
    print(f"   VERTEX_AI_PROJECT_ID: {'✓ Set' if project_id else '✗ Not set'}")
    print(f"   VERTEX_AI_LOCATION: {location}")
    print(f"   GOOGLE_APPLICATION_CREDENTIALS: {'✓ Set' if credentials_path else '○ Using default credentials'}")

    if not project_id:
        print("\n✗ ERROR: VERTEX_AI_PROJECT_ID not set!")
        print("   Set it in your .env file or environment:")
        print("   export VERTEX_AI_PROJECT_ID=your-project-id")
        return False

    # Try to import google-genai
    print("\n2. Checking Dependencies...")
    try:
        from google import genai
        print("   ✓ google-genai package installed")
    except ImportError:
        print("   ✗ google-genai not installed")
        print("   Install with: pip install google-genai")
        return False

    # Try to create client
    print("\n3. Initializing Vertex AI Client...")
    try:
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location
        )
        print(f"   ✓ Client initialized successfully")
        print(f"   Project: {project_id}")
        print(f"   Location: {location}")
    except Exception as e:
        print(f"   ✗ Failed to initialize client: {str(e)}")
        print("\n   Common solutions:")
        print("   1. Run: gcloud auth application-default login")
        print("   2. Enable Vertex AI API: gcloud services enable aiplatform.googleapis.com")
        print("   3. Set up service account with proper permissions")
        return False

    # Try a simple API call
    print("\n4. Testing API Call...")
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Say hello in Thai and English"
        )
        print("   ✓ API call successful!")
        print(f"   Response: {response.text[:100]}...")

        # Check usage metadata
        if hasattr(response, 'usage_metadata'):
            usage = response.usage_metadata
            print(f"   Token usage: {usage.total_token_count} tokens")
            print(f"   - Input: {usage.prompt_token_count}")
            print(f"   - Output: {usage.candidates_token_count}")
    except Exception as e:
        print(f"   ✗ API call failed: {str(e)}")
        print("\n   This might be a permissions issue.")
        print("   Ensure your account has 'roles/aiplatform.user' role")
        return False

    print("\n" + "=" * 60)
    print("✓ All tests passed! Vertex AI is configured correctly.")
    print("=" * 60)
    return True

def test_transaction_audit_service():
    """Test the TransactionAuditService initialization"""
    print("\n" + "=" * 60)
    print("Transaction Audit Service Test")
    print("=" * 60)

    try:
        # Import the service
        sys.path.insert(0, os.path.dirname(__file__))
        from GEPPPlatform.services.cores.transaction_audit.transaction_audit_service import TransactionAuditService

        print("\n1. Initializing TransactionAuditService...")
        service = TransactionAuditService()

        if service.client:
            print("   ✓ Service initialized successfully")
            print(f"   Project: {service.project_id}")
            print(f"   Location: {service.location}")
            print(f"   Model: {service.model_name}")
        else:
            print("   ✗ Service client not initialized")
            return False

        print("\n" + "=" * 60)
        print("✓ TransactionAuditService is ready!")
        print("=" * 60)
        return True

    except ImportError as e:
        print(f"   ✗ Could not import service: {str(e)}")
        return False
    except Exception as e:
        print(f"   ✗ Error initializing service: {str(e)}")
        return False

if __name__ == "__main__":
    print("\nVertex AI Setup Verification")
    print("This script will test your Vertex AI configuration\n")

    # Test basic Vertex AI connection
    vertex_ok = test_vertex_ai_connection()

    if vertex_ok:
        # Test the actual audit service
        service_ok = test_transaction_audit_service()

        if service_ok:
            print("\n✓ SUCCESS: Everything is configured correctly!")
            print("\nYou can now use the AI audit service with Vertex AI.")
            sys.exit(0)
        else:
            print("\n⚠ WARNING: Basic Vertex AI works, but service initialization failed.")
            print("Check the service configuration and dependencies.")
            sys.exit(1)
    else:
        print("\n✗ FAILED: Please fix the configuration issues above.")
        print("\nRefer to VERTEX_AI_MIGRATION.md for detailed setup instructions.")
        sys.exit(1)
