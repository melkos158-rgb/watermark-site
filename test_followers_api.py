"""
Тестування followers/following endpoints

Використання:
1. Запустити Flask app
2. python test_followers_api.py
"""

import requests

BASE_URL = "http://localhost:5000"
USER_ID = 1  # Замініть на реальний user_id

def test_followers():
    """Тест GET /api/user/<id>/followers"""
    url = f"{BASE_URL}/api/user/{USER_ID}/followers"
    resp = requests.get(url)
    
    print(f"\n=== GET {url} ===")
    print(f"Status: {resp.status_code}")
    print(f"Headers: Cache-Control = {resp.headers.get('Cache-Control')}")
    
    data = resp.json()
    print(f"Response: {data}")
    
    if data.get("ok"):
        print(f"✅ Success: Found {len(data.get('users', []))} followers")
        for user in data.get("users", [])[:3]:
            print(f"   - {user.get('name')} (ID: {user.get('id')})")
    else:
        print(f"❌ Error: {data.get('error')}")

def test_following():
    """Тест GET /api/user/<id>/following"""
    url = f"{BASE_URL}/api/user/{USER_ID}/following"
    resp = requests.get(url)
    
    print(f"\n=== GET {url} ===")
    print(f"Status: {resp.status_code}")
    print(f"Headers: Cache-Control = {resp.headers.get('Cache-Control')}")
    
    data = resp.json()
    print(f"Response: {data}")
    
    if data.get("ok"):
        print(f"✅ Success: Following {len(data.get('users', []))} users")
        for user in data.get("users", [])[:3]:
            print(f"   - {user.get('name')} (ID: {user.get('id')})")
    else:
        print(f"❌ Error: {data.get('error')}")

if __name__ == "__main__":
    print("🧪 Testing Followers/Following API endpoints")
    print(f"Base URL: {BASE_URL}")
    print(f"User ID: {USER_ID}")
    
    try:
        test_followers()
        test_following()
        print("\n✅ All tests completed")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
