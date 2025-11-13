import requests
import json

url = "http://localhost:8000/trace"

# Use addresses from the same known transaction
payload = {
    "list_a": ["1A1z7agoat4FqCnf4Xy7jJn1eJd7azHXzA"],  # Genesis block era
    "list_b": ["1A1z7agoat4FqCnf4Xy7jJn1eJd7azHXzA"],  # Same address (should connect immediately)
    "max_depth": 1,
    "start_block": 0,
    "end_block": 200000
}

response = requests.post(url, json=payload)
result = response.json()
print(json.dumps(result, indent=2))

session_id = result['session_id']
print(f"\nSession ID: {session_id}")
print("Check status with: curl http://localhost:8000/status/" + session_id)
