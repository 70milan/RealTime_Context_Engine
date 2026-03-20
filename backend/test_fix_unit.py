import sys
import os
import json
from pathlib import Path

# Mock profile_cache and load_profile
profile_cache = {"openai_api_key": "sk-proj-invalidKiwA"}

def load_profile_mock():
    return {"openai_api_key": "sk-proj-valid-key-ending-in-XYZ"}

# The logic from get_api_key
def test_get_api_key(cache, disk_key):
    # 1. Check in-memory
    key = cache.get('openai_api_key', '').strip()
    if key.startswith("sk-") and not key.endswith("KiwA"):
        return key
        
    # 2. Disk
    key = disk_key.strip()
    if key.startswith("sk-") and not key.endswith("KiwA"):
        return key
        
    return "FALLBACK_OR_NONE"

print("Test 1: Cache has invalid KiwA key, Disk has valid key")
result = test_get_api_key({"openai_api_key": "sk-proj-badKiwA"}, "sk-proj-goodXYZ")
print(f"Result: {result} (Expected: sk-proj-goodXYZ)")

print("\nTest 2: Both have invalid keys")
result = test_get_api_key({"openai_api_key": "sk-proj-badKiwA"}, "sk-proj-alsobadKiwA")
print(f"Result: {result} (Expected: FALLBACK_OR_NONE)")

print("\nTest 3: Cache has valid key")
result = test_get_api_key({"openai_api_key": "sk-proj-goodABC"}, "sk-proj-ignored")
print(f"Result: {result} (Expected: sk-proj-goodABC)")

# Test load_session logic
def test_load_session_logic(session_key, current_valid_key):
    res_key = None
    if session_key.startswith("sk-") and not session_key.endswith("KiwA"):
        res_key = session_key
    elif current_valid_key:
        res_key = current_valid_key
    return res_key

print("\nTest 4: Loading session with KiwA key, but profile has valid key")
result = test_load_session_logic("sk-proj-sessionKiwA", "sk-proj-profileGOOD")
print(f"Result: {result} (Expected: sk-proj-profileGOOD)")
