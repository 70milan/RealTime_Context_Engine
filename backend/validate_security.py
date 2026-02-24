import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from main import get_hwid, verify_license_signature
    print("[SUCCESS] Imported security functions from main.py")
except ImportError as e:
    print(f"[ERROR] Failed to import from main.py: {e}")
    sys.exit(1)

def test_hwid():
    print("\n--- Testing HWID Generation ---")
    hwid = get_hwid()
    print(f"Generated HWID: {hwid}")
    
    # Check format: XXXX-XXXX-XXXX-XXXX
    parts = hwid.split('-')
    if len(parts) == 4 and all(len(p) == 4 for p in parts):
        print("[PASS] HWID format is correct (XXXX-XXXX-XXXX-XXXX)")
    else:
        print("[FAIL] HWID format is incorrect")

def test_rsa_verification():
    print("\n--- Testing RSA Verification (Negative) ---")
    hwid = get_hwid()
    garbage_license = "A" * 342 + "=="
    
    print(f"Testing with garbage license: {garbage_license[:20]}...")
    result = verify_license_signature(hwid, garbage_license)
    if result is False:
        print("[PASS] Garbage license correctly rejected")
    else:
        print("[FAIL] Garbage license was NOT rejected")

    print("\n--- Testing RSA Verification (Format Check) ---")
    too_short = "ShortKey=="
    result = verify_license_signature(hwid, too_short)
    if result is False:
        print("[PASS] Short license correctly rejected")
    else:
        print("[FAIL] Short license was NOT rejected")

if __name__ == "__main__":
    test_hwid()
    test_rsa_verification()
