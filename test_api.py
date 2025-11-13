import requests
import json

url = "http://localhost:8000/trace"

payload = {
    "list_a": ["bc1q90ap5qgxcmxc4pxh7p5xdh8n5q47ycc9rfk8uv"],
    "list_b": ["3Eu8hVnztXnG5xHk3syAtmenn7XMBJaYVj"],
    "max_depth": 3,
    "start_block": 700000,
    "end_block": 750000
}

response = requests.post(url, json=payload)
print(json.dumps(response.json(), indent=2))
