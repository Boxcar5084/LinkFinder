import requests
import sys
import json

if len(sys.argv) < 2:
    print("Usage: python cancel_trace.py SESSION_ID")
    print("\nExample:")
    print("  python cancel_trace.py 3f008e47-1fee-4160-9064-6967067e5a74")
    sys.exit(1)

session_id = sys.argv
url = f"http://localhost:8000/cancel/{session_id}"

try:
    response = requests.post(url)
    result = response.json()
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"Error: {e}")
