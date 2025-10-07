#!/usr/bin/env python3
"""
Test script for IoT Scale System
Tests all IoT endpoints and functionality
"""

import requests
import json
import sys
from datetime import datetime, timezone
from typing import Dict, Any

# Configuration
BASE_URL = "https://your-api-gateway-url/dev"  # Replace with actual API Gateway URL
USER_EMAIL = "test@example.com"
USER_PASSWORD = "password123"

# Test data
TEST_SCALE_NAME = "SCALE-001"
TEST_SCALE_PASSWORD = "scale123456"
TEST_OWNER_ID = 1  # Replace with actual user ID
TEST_LOCATION_ID = 2  # Replace with actual location ID

class IoTTestSuite:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.user_token = None
        self.iot_token = None
        self.scale_id = None
        
    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def make_request(self, method: str, endpoint: str, data: Dict[str, Any] = None, 
                    headers: Dict[str, str] = None, auth_type: str = "user") -> Dict[str, Any]:
        """Make HTTP request with proper headers"""
        url = f"{self.base_url}{endpoint}"
        
        if headers is None:
            headers = {"Content-Type": "application/json"}
        
        # Add authentication header
        if auth_type == "user" and self.user_token:
            headers["Authorization"] = f"Bearer {self.user_token}"
        elif auth_type == "iot" and self.iot_token:
            headers["Authorization"] = f"Bearer {self.iot_token}"
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=data)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, params=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            return {
                "status_code": response.status_code,
                "data": response.json() if response.content else {},
                "headers": dict(response.headers)
            }
        except Exception as e:
            return {
                "status_code": 500,
                "data": {"error": str(e)},
                "headers": {}
            }
    
    def test_user_login(self) -> bool:
        """Test user login to get user token"""
        self.log("Testing user login...")
        
        login_data = {
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }
        
        result = self.make_request("POST", "/api/auth/login", login_data, auth_type="none")
        
        if result["status_code"] == 200 and "auth_token" in result["data"]:
            self.user_token = result["data"]["auth_token"]
            self.log(f"User login successful. Token: {self.user_token[:20]}...")
            return True
        else:
            self.log(f"User login failed: {result['data']}", "ERROR")
            return False
    
    def test_create_iot_scale(self) -> bool:
        """Test creating an IoT scale"""
        self.log("Testing IoT scale creation...")
        
        scale_data = {
            "scale_name": TEST_SCALE_NAME,
            "password": TEST_SCALE_PASSWORD,
            "owner_user_location_id": TEST_OWNER_ID,
            "location_point_id": TEST_LOCATION_ID,
            "mac_tablet": "AA:BB:CC:DD:EE:FF",
            "mac_scale": "11:22:33:44:55:66",
            "scale_type": "digital"
        }
        
        result = self.make_request("POST", "/api/iot/scales", scale_data)
        
        if result["status_code"] == 200:
            self.scale_id = result["data"]["data"]["id"]
            self.log(f"IoT scale created successfully. ID: {self.scale_id}")
            return True
        else:
            self.log(f"IoT scale creation failed: {result['data']}", "ERROR")
            return False
    
    def test_iot_scale_login(self) -> bool:
        """Test IoT scale login"""
        self.log("Testing IoT scale login...")
        
        login_data = {
            "scale_name": TEST_SCALE_NAME,
            "password": TEST_SCALE_PASSWORD
        }
        
        result = self.make_request("POST", "/api/iot/auth/login", login_data, auth_type="none")
        
        if result["status_code"] == 200 and "iot_token" in result["data"]:
            self.iot_token = result["data"]["iot_token"]
            self.log(f"IoT scale login successful. Token: {self.iot_token[:20]}...")
            return True
        else:
            self.log(f"IoT scale login failed: {result['data']}", "ERROR")
            return False
    
    def test_get_iot_scales(self) -> bool:
        """Test getting IoT scales list"""
        self.log("Testing get IoT scales list...")
        
        result = self.make_request("GET", "/api/iot/scales")
        
        if result["status_code"] == 200:
            scales = result["data"]["data"]
            self.log(f"Retrieved {len(scales)} IoT scales")
            return True
        else:
            self.log(f"Get IoT scales failed: {result['data']}", "ERROR")
            return False
    
    def test_get_iot_scale_details(self) -> bool:
        """Test getting IoT scale details"""
        self.log("Testing get IoT scale details...")
        
        if not self.scale_id:
            self.log("No scale ID available for testing", "ERROR")
            return False
        
        result = self.make_request("GET", f"/api/iot/scales/{self.scale_id}")
        
        if result["status_code"] == 200:
            scale_data = result["data"]["data"]
            self.log(f"Retrieved scale details: {scale_data['scale_name']}")
            return True
        else:
            self.log(f"Get IoT scale details failed: {result['data']}", "ERROR")
            return False
    
    def test_get_user_info(self) -> bool:
        """Test getting user info from IoT scale"""
        self.log("Testing get user info from IoT scale...")
        
        result = self.make_request("GET", "/api/iot/user-info", auth_type="iot")
        
        if result["status_code"] == 200:
            user_info = result["data"]["data"]
            self.log(f"Retrieved user info: {user_info['display_name']}")
            return True
        else:
            self.log(f"Get user info failed: {result['data']}", "ERROR")
            return False
    
    def test_get_location_info(self) -> bool:
        """Test getting location info from IoT scale"""
        self.log("Testing get location info from IoT scale...")
        
        result = self.make_request("GET", "/api/iot/location-info", auth_type="iot")
        
        if result["status_code"] == 200:
            location_info = result["data"]["data"]
            self.log(f"Retrieved location info: {location_info['display_name']}")
            return True
        else:
            self.log(f"Get location info failed: {result['data']}", "ERROR")
            return False
    
    def test_update_iot_scale(self) -> bool:
        """Test updating IoT scale"""
        self.log("Testing update IoT scale...")
        
        if not self.scale_id:
            self.log("No scale ID available for testing", "ERROR")
            return False
        
        update_data = {
            "scale_type": "advanced",
            "mac_tablet": "FF:EE:DD:CC:BB:AA"
        }
        
        result = self.make_request("PUT", f"/api/iot/scales/{self.scale_id}", update_data)
        
        if result["status_code"] == 200:
            self.log("IoT scale updated successfully")
            return True
        else:
            self.log(f"Update IoT scale failed: {result['data']}", "ERROR")
            return False
    
    def test_validate_iot_token(self) -> bool:
        """Test IoT token validation"""
        self.log("Testing IoT token validation...")
        
        result = self.make_request("POST", "/api/iot/auth/validate", auth_type="iot")
        
        if result["status_code"] == 200:
            self.log("IoT token validation successful")
            return True
        else:
            self.log(f"IoT token validation failed: {result['data']}", "ERROR")
            return False
    
    def test_delete_iot_scale(self) -> bool:
        """Test deleting IoT scale"""
        self.log("Testing delete IoT scale...")
        
        if not self.scale_id:
            self.log("No scale ID available for testing", "ERROR")
            return False
        
        result = self.make_request("DELETE", f"/api/iot/scales/{self.scale_id}")
        
        if result["status_code"] == 200:
            self.log("IoT scale deleted successfully")
            return True
        else:
            self.log(f"Delete IoT scale failed: {result['data']}", "ERROR")
            return False
    
    def run_all_tests(self) -> Dict[str, bool]:
        """Run all IoT system tests"""
        self.log("Starting IoT System Test Suite...")
        
        tests = {
            "user_login": self.test_user_login,
            "create_iot_scale": self.test_create_iot_scale,
            "iot_scale_login": self.test_iot_scale_login,
            "get_iot_scales": self.test_get_iot_scales,
            "get_iot_scale_details": self.test_get_iot_scale_details,
            "get_user_info": self.test_get_user_info,
            "get_location_info": self.test_get_location_info,
            "update_iot_scale": self.test_update_iot_scale,
            "validate_iot_token": self.test_validate_iot_token,
            "delete_iot_scale": self.test_delete_iot_scale
        }
        
        results = {}
        
        for test_name, test_func in tests.items():
            try:
                results[test_name] = test_func()
            except Exception as e:
                self.log(f"Test {test_name} failed with exception: {str(e)}", "ERROR")
                results[test_name] = False
        
        # Summary
        self.log("=" * 50)
        self.log("TEST RESULTS SUMMARY")
        self.log("=" * 50)
        
        passed = sum(1 for result in results.values() if result)
        total = len(results)
        
        for test_name, result in results.items():
            status = "PASS" if result else "FAIL"
            self.log(f"{test_name}: {status}")
        
        self.log(f"Overall: {passed}/{total} tests passed")
        
        return results

def main():
    """Main function"""
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        base_url = BASE_URL
    
    print(f"Testing IoT System at: {base_url}")
    print("=" * 50)
    
    # Create test suite
    test_suite = IoTTestSuite(base_url)
    
    # Run tests
    results = test_suite.run_all_tests()
    
    # Exit with error code if any test failed
    if not all(results.values()):
        sys.exit(1)
    else:
        print("\n🎉 All tests passed!")
        sys.exit(0)

if __name__ == "__main__":
    main()
