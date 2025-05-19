import requests

API_KEY = ""  # Thay bằng API Key của bạn
API_URL = "https://api.groq.com/openai/v1/chat/completions"

headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

data = {
    "model": "llama3-70b-8192",  # Hoặc "mixtral-8x7b-32768"
    "messages": [{"role": "user", "content": "today's date"}],
    "temperature": 0.7,
    "max_tokens": 512,
}

response = requests.post(API_URL, headers=headers, json=data)

if response.status_code == 200:
    print(response.json()["choices"][0]["message"]["content"])
else:
    print("Lỗi:", response.status_code, response.text)
