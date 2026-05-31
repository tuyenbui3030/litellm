import sys
import requests
import urllib.parse
from litellm.llms.gemini_cli.authenticator import Authenticator, generate_pkce_pair

# Cấu hình Proxy của bạn
PROXY_URL = "http://localhost:4000"
MASTER_KEY = "sk-admin-123456789"

def add_account():
    auth = Authenticator()
    # 1. Tạo Auth URL với localhost redirect (Sử dụng 127.0.0.1 để tuân thủ chính sách Google)
    redirect_uri = "http://127.0.0.1:8080/callback"
    
    # Generate PKCE pair
    code_verifier, code_challenge = generate_pkce_pair()
    
    url, state = auth.generate_auth_url(redirect_uri, code_challenge=code_challenge)
    
    print("\n" + "="*60)
    print("BƯỚC 1: ĐĂNG NHẬP")
    print("="*60)
    print("Hãy copy đường link dưới đây và dán vào trình duyệt trên máy của bạn:")
    print(f"\n{url}\n")
    print("Sau khi đăng nhập xong, trình duyệt sẽ báo lỗi 'Unable to connect' hoặc 'Site can't be reached'.")
    print("Điều này là BÌNH THƯỜNG. Hãy copy toàn bộ đường link trên thanh địa chỉ đó.")
    
    print("\n" + "="*60)
    print("BƯỚC 2: XÁC NHẬN")
    print("="*60)
    callback_url = input("Dán toàn bộ URL (hoặc mã 'code') vào đây: ").strip()
    
    try:
        print("\nĐang lấy Token và Project ID...")
        tokens = auth.handle_callback(callback_url, redirect_uri, state, code_verifier=code_verifier)
        
        acc_name = input("\nNhập tên gợi nhớ cho tài khoản này (ví dụ: gemini-acc-2): ").strip()
        if not acc_name: acc_name = "gemini-new-account"
        
        # 2. Gọi API Proxy để nạp tài khoản vào Database
        print(f"Đang nạp tài khoản '{acc_name}' vào Proxy...")
        
        payload = {
            "model_name": acc_name,
            "litellm_params": {
                "model": "gemini_cli/gemini-3.1-pro-preview",
                "gemini_cli_refresh_token": tokens["refresh_token"],
                "gemini_cli_project_id": tokens["project_id"]
            }
        }
        
        resp = requests.post(
            f"{PROXY_URL}/model/new",
            headers={"Authorization": f"Bearer {MASTER_KEY}", "Content-Type": "application/json"},
            json=payload
        )
        
        if resp.status_code == 200:
            print(f"\n✅ THÀNH CÔNG! Tài khoản đã được nạp.")
            print(f"Giờ bạn có thể gọi model này bằng tên: {acc_name}")
        else:
            print(f"\n❌ LỖI khi nạp vào Proxy: {resp.text}")
            
    except Exception as e:
        print(f"\n❌ LỖI xác thực: {e}")

if __name__ == "__main__":
    add_account()
