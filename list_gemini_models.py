import json
import os
import httpx
from litellm.llms.gemini_cli.authenticator import Authenticator

def list_gemini_cli_models():
    auth = Authenticator()
    try:
        access_token, project_id = auth.get_credentials()
        print(f"Project ID: {project_id}")
        
        # Thử endpoint list models (giả định cấu trúc giống các API khác của Google)
        endpoints = [
            "https://cloudcode-pa.googleapis.com/v1internal/models",
            "https://cloudcode-pa.googleapis.com/v1internal:listModels",
        ]
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Goog-Api-Client": "google-genai-sdk/1.41.0 gl-node/v22.19.0",
        }
        
        for url in endpoints:
            print(f"\nĐang thử: {url}")
            resp = httpx.get(url, headers=headers)
            print(f"Status: {resp.status_code}")
            try:
                print(json.dumps(resp.json(), indent=2))
            except:
                print(resp.text[:500])
                
    except Exception as e:
        print(f"Lỗi: {e}")

if __name__ == "__main__":
    list_gemini_cli_models()
