from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import RedirectResponse, HTMLResponse
import httpx
import os
import json
from typing import Optional

from litellm.llms.gemini_cli.authenticator import Authenticator, generate_pkce_pair
from litellm.llms.gemini_cli.common_utils import (
    GEMINI_CLI_AUTHORIZE_URL,
    GEMINI_CLI_CLIENT_ID,
    GEMINI_CLI_SCOPES,
)
from litellm._logging import verbose_proxy_logger
from litellm.proxy.common_utils.encrypt_decrypt_utils import encrypt_value_helper

router = APIRouter()
authenticator = Authenticator()

@router.get("/gemini_cli/login", response_class=HTMLResponse)
async def gemini_cli_login_page(request: Request, model_alias: Optional[str] = "gemini-new-acc"):
    """
    Trang hướng dẫn nạp tài khoản Gemini CLI
    """
    # Use a standard loopback redirect URI
    redirect_uri = "http://127.0.0.1:8080/callback"
    
    # Generate PKCE pair
    code_verifier, code_challenge = generate_pkce_pair()
    
    auth_url, state = authenticator.generate_auth_url(redirect_uri, code_challenge=code_challenge)
    
    return f"""
    <html>
    <head>
        <title>LiteLLM - Add Gemini Account</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    </head>
    <body class="bg-gray-50 h-screen flex items-center justify-center">
        <div class="bg-white p-8 rounded-xl shadow-lg max-w-md w-full border border-gray-100">
            <h1 class="text-2xl font-bold text-gray-800 mb-2">Gemini CLI Setup</h1>
            <p class="text-gray-600 mb-6 text-sm">Vì lý do bảo mật của Google, bạn cần thực hiện các bước sau để nạp tài khoản vào Proxy.</p>
            
            <div class="space-y-4">
                <div class="flex items-start space-x-3">
                    <span class="bg-blue-100 text-blue-600 rounded-full h-6 w-6 flex items-center justify-center flex-shrink-0 text-xs font-bold">1</span>
                    <p class="text-sm text-gray-700">Nhấn nút bên dưới để đăng nhập Google trên máy tính của bạn.</p>
                </div>
                <a href="{auth_url}" target="_blank" class="block w-full text-center bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg transition">
                    Login with Google
                </a>
                
                <div class="flex items-start space-x-3 pt-4">
                    <span class="bg-blue-100 text-blue-600 rounded-full h-6 w-6 flex items-center justify-center flex-shrink-0 text-xs font-bold">2</span>
                    <p class="text-sm text-gray-700">Sau khi xong, trình duyệt sẽ báo "Site can't be reached". Đừng lo, hãy <b>Copy toàn bộ URL</b> đó dán vào đây:</p>
                </div>
                
                <form action="/gemini_cli/confirm" method="POST" class="space-y-3">
                    <input type="hidden" name="model_alias" value="{model_alias}">
                    <input type="hidden" name="state" value="{state}">
                    <input type="hidden" name="code_verifier" value="{code_verifier}">
                    <textarea name="callback_url" rows="3" class="w-full border rounded-lg p-2 text-xs font-mono focus:ring-2 focus:ring-blue-500 outline-none" placeholder="http://127.0.0.1:8080/callback?code=..."></textarea>
                    <button type="submit" class="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-2 rounded-lg transition">
                        Confirm & Register
                    </button>
                </form>
            </div>
            
            <p class="mt-6 text-center text-xs text-gray-400 italic">Account will be saved as: <b>{model_alias}</b></p>
        </div>
    </body>
    </html>
    """

@router.post("/gemini_cli/confirm", response_class=HTMLResponse)
async def gemini_cli_confirm(callback_url: str = Form(...), model_alias: str = Form(...), state: str = Form(...), code_verifier: str = Form(...)):
    """
    Xử lý URL được dán vào để đăng ký model
    """
    try:
        redirect_uri = "http://127.0.0.1:8080/callback"
        
        # Exchange code for tokens
        tokens = authenticator.handle_callback(callback_url, redirect_uri, state=state, code_verifier=code_verifier)
        
        import litellm.proxy.proxy_server as proxy_server
        if proxy_server.prisma_client is None:
            return "<h1>Error: Prisma not initialized</h1>"

        # Encrypt sensitive values before saving to DB
        refresh_token = encrypt_value_helper(tokens["refresh_token"])
        project_id = encrypt_value_helper(tokens["project_id"])

        # 1. Create Pro model in DB
        await proxy_server.prisma_client.db.litellm_proxymodeltable.create(
            data={
                "model_name": f"{model_alias}-pro",
                "litellm_params": json.dumps({
                    "model": "gemini_cli/gemini-3.1-pro-preview",
                    "gemini_cli_refresh_token": refresh_token,
                    "gemini_cli_project_id": project_id
                }),
                "model_info": json.dumps({"base_model": "gemini-3.1-pro"}),
                "created_by": "gemini-cli-setup",
                "updated_by": "gemini-cli-setup"
            }
        )

        # 2. Create Flash model in DB
        await proxy_server.prisma_client.db.litellm_proxymodeltable.create(
            data={
                "model_name": f"{model_alias}-flash",
                "litellm_params": json.dumps({
                    "model": "gemini_cli/gemini-3.1-flash",
                    "gemini_cli_refresh_token": refresh_token,
                    "gemini_cli_project_id": project_id
                }),
                "model_info": json.dumps({"base_model": "gemini-3.1-flash"}),
                "created_by": "gemini-cli-setup",
                "updated_by": "gemini-cli-setup"
            }
        )
        
        return f"""
        <body style='font-family: sans-serif; text-align: center; padding-top: 100px;'>
            <h1 style='color: #059669;'>Success!</h1>
            <p>Account registered with 2 models:</p>
            <ul style='list-style: none; padding: 0;'>
                <li><b>{model_alias}-pro</b></li>
                <li><b>{model_alias}-flash</b></li>
            </ul>
            <a href='/ui' style='color: #2563eb;'>Go to Dashboard</a>
        </body>
        """
    except Exception as e:
        return f"<body style='font-family: sans-serif; padding: 20px;'><h1>Error</h1><p>{str(e)}</p></body>"
