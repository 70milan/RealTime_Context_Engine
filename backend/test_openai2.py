import sys
from openai import OpenAI
import traceback

log_file = r"c:\Data Engineering\release_package\backend\test_openai_out.txt"

def log(msg):
    with open(log_file, "a") as f:
        f.write(msg + "\n")

# A project key string that is identical in format to what the user provided
key = "sk-proj-invalidkey1234567890invalidkey1234567890invalidkey1234567890invalidkey1234567890invalidkey1234567890invalidkey1234567890invalidkey1234567890invalidkey1234567890KiwA"

try:
    log("Testing models.list...")
    client = OpenAI(api_key=key)
    client.models.list()
    log("Models list succeeded!")
except Exception as e:
    log(f"Models list failed: {e}")
    log(traceback.format_exc())

try:
    log("\nTesting chat.completions.create...")
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hello"}]
    )
    log("Chat succeeded!")
except Exception as e:
    log(f"Chat failed: {e}")
    log(traceback.format_exc())
