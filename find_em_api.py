import requests
import json

url = "http://localhost:8000/trace"

# Use addresses from the same known transaction
payload = {
    "list_a": ["38YEkk8pKA1DXWhQTdW53ibXUaFDYqk269"],  
    "list_b": ["bc1qap3l4kcwx0fsp9h9wy0umjv0fjp6th00syagd3",
                "bc1qeqdtuuywk0zv76hz55w93k7r64nkltr7rx9pvk",
                "bc1qg9lwm3cfyt56ttdtqsf2rrhy0sqhwwf05gkr35",
                "32z7Jgnc6hRfiVDzTq9uQyCRSVVyNhN5Cy",
                "34S1oUqvPcCfgcGCkZWyKDbdzJKZrSRsbM",
                "372j1Q7ta1ktVcJvVkEUgnNEwZ7ofce8bg",
                "38bZ6VsWeEYnYC3VqzPJPVBRGLFWijZyo9",
                "bc1q5s8qs5dzf2acdnaq2l9rhe85v2chm4gqsxcvr8",
                "bc1qk3f08q6ekessqx9ufkpda3xsafcmnue7p57pfe",
                "bc1qkh6xvzj3ncq3zl522rpgvw3mlvqf3nkv063mym",
                "bc1qldy0sfqwg9nf02hydyk56lre3d5q39dqxuylfx",
                "bc1qmjflnn85pkfkygqsfvx6ay7eew4y9q8x839vpg",
                "bc1qu23mc4w0ramhk79lahvg8we756jsjzezmavsj8",
                "bc1quchr9xrx7d7rtl6p907wwmumn7285d2vzw6684"
                ],  
    "max_depth": 4,
    "start_block": 0,
    "end_block": 999999
}

response = requests.post(url, json=payload)
result = response.json()
print(json.dumps(result, indent=2))

session_id = result['session_id']
print(f"\nSession ID: {session_id}")
print("Check status with: curl http://localhost:8000/status/" + session_id)
