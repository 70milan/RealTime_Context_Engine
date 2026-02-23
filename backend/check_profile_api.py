
import json
from pathlib import Path
from openai import OpenAI

def check_key():
    profile_path = Path("user_profile.json")
    if not profile_path.exists():
        return "Error: user_profile.json not found"
    
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        api_key = profile.get("openai_api_key")
        if not api_key:
            return "Error: No API key found in profile"
        
        # Strip just in case, though profile shows it's there
        api_key = api_key.strip()
        
        print(f"Testing key starting with: {api_key[:10]}...")
        
        client = OpenAI(api_key=api_key)
        models = client.models.list()
        return f"Success: Key is valid. Found {len(list(models))} models."
    except Exception as e:
        return f"Failure: {str(e)}"

if __name__ == "__main__":
    result = check_key()
    Path("api_check_result.txt").write_text(result, encoding="utf-8")
    print(result)
