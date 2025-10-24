import requests
import json

# Your API key
api_key = "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"

# API endpoint
url = "https://api.openai.com/v1/chat/completions"

# Headers
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

# Request body
data = {
    "model": "gpt-3.5-turbo",
    "messages": [
        {"role": "user", "content": "Hi"}
    ]
}

print("Sending request to OpenAI...")

# Send request
response = requests.post(url, headers=headers, json=data)

# Print response
if response.status_code == 200:
    result = response.json()
    print("\nAI Response:", result['choices'][0]['message']['content'])
else:
    print(f"\nError {response.status_code}: {response.text}")
