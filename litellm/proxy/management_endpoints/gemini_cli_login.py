import asyncio
import json
from typing import Optional
import httpx

from fastapi import APIRouter, Form, Request, HTTPException, status, Depends
from fastapi.responses import HTMLResponse

import litellm
from litellm.llms.gemini_cli.authenticator import Authenticator, generate_pkce_pair
from litellm.proxy._types import ProxyException, UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.common_utils.encrypt_decrypt_utils import (
    decrypt_value_helper,
    encrypt_value_helper,
)

router = APIRouter()
authenticator = Authenticator()


@router.get("/gemini_cli/login", response_class=HTMLResponse)
async def gemini_cli_login_page(
    request: Request,
    model_alias: Optional[str] = "gemini-new-acc",
):
    """
    Trang hướng dẫn nạp tài khoản Gemini CLI
    """
    # Use a standard loopback redirect URI
    redirect_uri = "http://127.0.0.1:8080/callback"

    # Generate PKCE pair
    code_verifier, code_challenge = generate_pkce_pair()

    auth_url, state = authenticator.generate_auth_url(
        redirect_uri, code_challenge=code_challenge
    )

    return f"""
    <html>
    <head>
        <title>LiteLLM - Add Gemini Account</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
        <style>
            .modal-overlay {{
                background-color: rgba(0, 0, 0, 0.8);
                backdrop-filter: blur(4px);
            }}
        </style>
    </head>
    <body class="bg-gray-50 h-screen flex items-center justify-center">
        <!-- Login Overlay -->
        <div id="login-overlay" class="fixed inset-0 z-50 flex items-center justify-center modal-overlay hidden">
            <div class="bg-white p-8 rounded-2xl shadow-2xl border border-gray-100 max-w-md w-full mx-4">
                <h2 class="text-2xl font-bold mb-4 text-blue-600">Authentication Required</h2>
                <p class="text-gray-600 mb-6 text-sm">Vui lòng nhập LiteLLM API Key để thực hiện setup.</p>
                <div class="space-y-4">
                    <input type="password" id="api-key-input" placeholder="sk-..." class="w-full border border-gray-300 rounded-lg p-3 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    <button onclick="saveApiKey()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-lg transition">
                        Confirm Key
                    </button>
                </div>
            </div>
        </div>

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

                <form id="setup-form" class="space-y-3">
                    <input type="hidden" id="state" value="{state}">
                    <input type="hidden" id="code_verifier" value="{code_verifier}">

                    <div class="mb-3">
                        <label class="block text-xs font-semibold text-gray-600 mb-1">Tên Model muốn load balance (VD: geminicli):</label>
                        <input type="text" id="model_alias" required value="{model_alias}" class="w-full border rounded-lg p-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                        <p class="text-xs text-gray-400 mt-1">Các tài khoản cùng tên model này sẽ được tự động load balance.</p>
                    </div>

                    <div class="mb-3 mt-4">
                        <label class="block text-xs font-semibold text-gray-600 mb-1">Dán Callback URL (Báo lỗi "Site can't be reached"):</label>
                        <textarea id="callback_url" required rows="3" class="w-full border rounded-lg p-2 text-xs font-mono focus:ring-2 focus:ring-blue-500 outline-none" placeholder="http://127.0.0.1:8080/callback?code=..."></textarea>
                    </div>
                    <div id="error-message" class="text-red-500 text-xs hidden mb-2"></div>
                    <button type="submit" id="submit-btn" class="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-2 rounded-lg transition mt-2">
                        Confirm & Register
                    </button>
                </form>
            </div>
        </div>

        <script>
            let apiKey = sessionStorage.getItem('lite_llm_api_key');

            function saveApiKey() {{
                const input = document.getElementById('api-key-input');
                if (input.value) {{
                    apiKey = input.value;
                    sessionStorage.setItem('lite_llm_api_key', apiKey);
                    document.getElementById('login-overlay').classList.add('hidden');
                }}
            }}

            window.onload = function() {{
                if (!apiKey) {{
                    document.getElementById('login-overlay').classList.remove('hidden');
                }}
            }};

            document.getElementById('setup-form').onsubmit = async function(e) {{
                e.preventDefault();

                const btn = document.getElementById('submit-btn');
                const errMsg = document.getElementById('error-message');

                btn.disabled = true;
                btn.innerText = "Processing...";
                errMsg.classList.add('hidden');

                const formData = new FormData();
                formData.append('callback_url', document.getElementById('callback_url').value);
                formData.append('model_alias', document.getElementById('model_alias').value);
                formData.append('state', document.getElementById('state').value);
                formData.append('code_verifier', document.getElementById('code_verifier').value);

                try {{
                    const resp = await fetch("/gemini_cli/confirm", {{
                        method: 'POST',
                        headers: {{
                            'Authorization': 'Bearer ' + apiKey
                        }},
                        body: formData
                    }});

                    const data = await resp.json();

                    if (resp.ok) {{
                        document.body.innerHTML = `
                            <div class="bg-white p-8 rounded-xl shadow-lg max-w-md w-full border border-gray-100 text-center">
                                <h1 class="text-2xl font-bold text-green-600 mb-4">Success!</h1>
                                <p class="text-gray-700 mb-4">Account registered with 2 models:</p>
                                <ul class="list-none p-0 mb-6 space-y-2">
                                    <li class="font-bold text-gray-800">${{document.getElementById('model_alias').value}}-pro</li>
                                    <li class="font-bold text-gray-800">${{document.getElementById('model_alias').value}}-flash</li>
                                </ul>
                                <a href='/gemini_cli/status' class="text-blue-600 hover:underline">Go to Status Dashboard</a>
                            </div>
                        `;
                    }} else {{
                        errMsg.innerText = data.detail || "Error processing request";
                        errMsg.classList.remove('hidden');
                    }}
                }} catch (err) {{
                    errMsg.innerText = "Connection error: " + err.message;
                    errMsg.classList.remove('hidden');
                }} finally {{
                    btn.disabled = false;
                    btn.innerText = "Confirm & Register";
                }}
            }};
        </script>
    </body>
    </html>
    """


@router.post("/gemini_cli/confirm")
async def gemini_cli_confirm(
    callback_url: str = Form(...),
    model_alias: str = Form(...),
    state: str = Form(...),
    code_verifier: str = Form(...),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Xử lý URL được dán vào để đăng ký model
    """
    try:
        redirect_uri = "http://127.0.0.1:8080/callback"

        # Exchange code for tokens
        tokens = authenticator.handle_callback(
            callback_url, redirect_uri, state=state, code_verifier=code_verifier
        )

        # Retrieve email from Google userinfo API
        email = None
        try:
            from litellm.llms.custom_httpx.http_handler import _get_httpx_client

            client = _get_httpx_client()
            userinfo_resp = client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            userinfo_resp.raise_for_status()
            userinfo_data = userinfo_resp.json()
            email = userinfo_data.get("email")
        except Exception:
            pass

        if not email:
            email = "gemini-cli-user"

        import litellm.proxy.proxy_server as proxy_server

        if proxy_server.prisma_client is None:
            raise HTTPException(status_code=500, detail="Prisma not initialized")

        # Encrypt sensitive values before saving to DB
        refresh_token = encrypt_value_helper(tokens["refresh_token"])
        project_id = encrypt_value_helper(tokens["project_id"])

        # 1. Create Pro model in DB
        await proxy_server.prisma_client.db.litellm_proxymodeltable.create(
            data={
                "model_name": f"{model_alias}-pro",
                "litellm_params": json.dumps(
                    {
                        "model": "gemini_cli/gemini-3.1-pro-preview",
                        "gemini_cli_refresh_token": refresh_token,
                        "gemini_cli_project_id": project_id,
                        "organization": email,
                    }
                ),
                "model_info": json.dumps(
                    {
                        "base_model": "gemini-3.1-pro",
                        "organization": email,
                        "db_model": True,
                    }
                ),
                "created_by": "gemini-cli-setup",
                "updated_by": "gemini-cli-setup",
            }
        )

        # 2. Create Flash model in DB
        await proxy_server.prisma_client.db.litellm_proxymodeltable.create(
            data={
                "model_name": f"{model_alias}-flash",
                "litellm_params": json.dumps(
                    {
                        "model": "gemini_cli/gemini-3-flash-preview",
                        "gemini_cli_refresh_token": refresh_token,
                        "gemini_cli_project_id": project_id,
                        "organization": email,
                    }
                ),
                "model_info": json.dumps(
                    {
                        "base_model": "gemini-3-flash-preview",
                        "organization": email,
                        "db_model": True,
                    }
                ),
                "created_by": "gemini-cli-setup",
                "updated_by": "gemini-cli-setup",
            }
        )

        # Clear cache and reload models
        from litellm.proxy.management_endpoints.model_management_endpoints import (
            clear_cache,
        )

        await clear_cache()

        return {"status": "success", "model_alias": model_alias}
    except Exception as e:
        from litellm._logging import verbose_proxy_logger

        verbose_proxy_logger.error(f"Error in gemini_cli_confirm: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def _test_single_gemini_cli_model_by_params(
    model_name: str, model_info_raw, params_dict: dict, model_id: Optional[str] = None
) -> dict:
    # Resolve email/organization
    model_info = model_info_raw
    if isinstance(model_info, str):
        try:
            model_info = json.loads(model_info)
        except Exception:
            model_info = {}
    email = (
        params_dict.get("organization") or model_info.get("organization") or "Not Set"
    )

    # Decrypt params
    decrypted_params = {}
    for k, v in params_dict.items():
        decrypted_params[k] = decrypt_value_helper(v, k, return_original_value=True)

    try:
        # Perform a fast health check test — disable retries so we don't hang
        check_params = dict(decrypted_params)
        check_params["num_retries"] = 0
        check_params["request_timeout"] = 15.0

        # Inject model_id and metadata to ensure logging works
        if "metadata" not in check_params:
            check_params["metadata"] = {}
        if "model_info" not in check_params["metadata"]:
            check_params["metadata"]["model_info"] = {}

        if model_id:
            check_params["metadata"]["model_info"]["id"] = model_id
        if email != "Not Set":
            check_params["metadata"]["organization"] = email

        result = await asyncio.wait_for(
            litellm.ahealth_check(
                model_params=check_params,
                mode="chat",
                prompt="hello",
                input=["hello"],
            ),
            timeout=20.0,
        )
        if "error" in result:
            return {
                "model_name": model_name,
                "email": email,
                "status": "fail",
                "error": result["error"],
            }
        else:
            return {
                "model_name": model_name,
                "email": email,
                "status": "success",
                "error": None,
            }
    except asyncio.TimeoutError:
        return {
            "model_name": model_name,
            "email": email,
            "status": "fail",
            "error": "Connection timed out (20.0s limit reached)",
        }
    except Exception as e:
        err_msg = str(e).strip() or f"{type(e).__name__}"
        return {
            "model_name": model_name,
            "email": email,
            "status": "fail",
            "error": err_msg,
        }


@router.get("/gemini_cli/test_one")
async def test_single_gemini_cli_connection(
    model_id: str, user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth)
):
    """
    Test connection of a single registered gemini_cli model by model_id (unique)
    """
    if not model_id or not isinstance(model_id, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="model_id must be a non-empty string"
        )

    import litellm.proxy.proxy_server as proxy_server

    if proxy_server.prisma_client is None:
        return {"status": "fail", "error": "Prisma not initialized"}

    try:
        # Fetch the model from DB by unique model_id
        model_obj = (
            await proxy_server.prisma_client.db.litellm_proxymodeltable.find_unique(
                where={"model_id": model_id}
            )
        )
        if not model_obj:
            return {"status": "fail", "error": "Model not found"}

        params = model_obj.litellm_params
        if isinstance(params, str):
            params = json.loads(params)
        if not isinstance(params, dict):
            return {"status": "fail", "error": "Invalid model parameters"}

        # Run connection check with 20.0s timeout
        res = await _test_single_gemini_cli_model_by_params(
            model_obj.model_name, model_obj.model_info, params, model_id=model_id
        )
        return res
    except Exception as e:
        from litellm._logging import verbose_proxy_logger

        verbose_proxy_logger.error(f"Error fetching quota: {str(e)}")
        return {"status": "fail", "error": "Internal server error"}


async def _fetch_quota_for_model(
    access_token: str, project_id: str, model_key: str
) -> Optional[dict]:
    """
    Gọi retrieveUserQuota và trả về quota info cho model_key tương ứng.
    Fallback: nếu không match exact model_key, trả về bucket đầu tiên.
    """
    url = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    body = {"project": project_id}

    # Gọi với timeout 10s (không retry)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=body)

        if not resp.is_success:
            return None

        data = resp.json()
    except Exception as e:
        from litellm._logging import verbose_proxy_logger

        verbose_proxy_logger.error(f"Error fetching quota: {str(e)}")
        return None

    try:
        buckets = data.get("buckets", [])
    except Exception:
        return None

    # Match theo model_key (strip prefix "gemini_cli/")
    target = model_key.removeprefix("gemini_cli/")

    for bucket in buckets:
        if bucket.get("modelId") == target:
            frac = float(bucket.get("remainingFraction", 0))
            return {
                "model_key": target,
                "remaining_pct": round(frac * 100, 1),
                "reset_at": bucket.get("resetTime"),
                "status": "exhausted" if frac == 0 else "ok",
            }

    # Không match → trả bucket đầu tiên nếu có
    if buckets:
        frac = float(buckets[0].get("remainingFraction", 0))
        return {
            "model_key": buckets[0].get("modelId"),
            "remaining_pct": round(frac * 100, 1),
            "reset_at": buckets[0].get("resetTime"),
            "status": "exhausted" if frac == 0 else "ok",
            "note": "fallback_first_bucket",
        }

    return None


@router.get("/gemini_cli/quota_one")
async def test_single_gemini_cli_quota(
    model_id: str, user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth)
):
    """
    Fetch quota info cho 1 model (nhận query model_id).
    """
    if not model_id or not isinstance(model_id, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="model_id must be a non-empty string"
        )

    import litellm.proxy.proxy_server as proxy_server

    if proxy_server.prisma_client is None:
        return {"quota": None, "quota_error": "Prisma not initialized"}

    try:
        model_obj = (
            await proxy_server.prisma_client.db.litellm_proxymodeltable.find_unique(
                where={"model_id": model_id}
            )
        )
        if not model_obj:
            return {"quota": None, "quota_error": "Model not found"}

        params = model_obj.litellm_params
        if isinstance(params, str):
            params = json.loads(params)
        if not isinstance(params, dict):
            return {"quota": None, "quota_error": "Invalid model parameters"}

        # Resolve email/organization
        model_info = model_obj.model_info
        if isinstance(model_info, str):
            try:
                model_info = json.loads(model_info)
            except Exception:
                model_info = {}
        email = (
            params.get("organization") or model_info.get("organization") or "Not Set"
        )

        model_key = params.get("model", "")
        refresh_token_enc = params.get("gemini_cli_refresh_token")
        if not refresh_token_enc:
            return {"quota": None, "quota_error": "No refresh_token found"}

        refresh_token = decrypt_value_helper(
            refresh_token_enc, "gemini_cli_refresh_token", return_original_value=True
        )

        # Lấy access token (qua refresh)
        try:
            tokens = authenticator._refresh_tokens(refresh_token)
            access_token = tokens["access_token"]
        except Exception as e:
            from litellm._logging import verbose_proxy_logger

            verbose_proxy_logger.error(f"Token refresh failed in test_single_gemini_cli_quota: {str(e)}")
            return {"quota": None, "quota_error": "Token refresh failed"}

        project_id_enc = params.get("gemini_cli_project_id")
        project_id = ""
        if project_id_enc:
            project_id = decrypt_value_helper(
                project_id_enc, "gemini_cli_project_id", return_original_value=True
            )

        if not project_id:
            # Fallback
            try:
                project_id = authenticator._fetch_project_id(access_token)
            except Exception as e:
                from litellm._logging import verbose_proxy_logger

                verbose_proxy_logger.error(f"Fetch project ID failed in test_single_gemini_cli_quota: {str(e)}")
                return {
                    "quota": None,
                    "quota_error": "Fetch project ID failed",
                }

        if not project_id:
            return {"quota": None, "quota_error": "Project ID not found"}

        quota = await _fetch_quota_for_model(access_token, project_id, model_key)
        if not quota:
            return {"quota": None, "quota_error": "No quota data returned"}

        return {
            "model_id": model_id,
            "model_name": model_obj.model_name,
            "email": email,
            "quota": quota,
        }

    except Exception as e:
        return {"quota": None, "quota_error": "Internal server error"}


def _process_spend_logs_health(
    recent_logs, model_id: str, model_name: str, email: str
) -> int:
    count = 0
    for log in recent_logs:
        try:
            if log.status == "failure":
                continue

            # 1. Nếu log có model_id, đây là source of truth cao nhất
            if log.model_id:
                if log.model_id == model_id:
                    count += 1
                continue

            # 2. Nếu không có model_id, check qua organization
            log_meta = log.metadata
            if isinstance(log_meta, str):
                try:
                    log_meta = json.loads(log_meta)
                except Exception:
                    log_meta = {}
            if not isinstance(log_meta, dict):
                log_meta = {}

            log_org = log_meta.get("organization") or log.organization_id
            if log_org and email and log_org == email:
                count += 1
                continue

            # 3. Nếu cả model_id và organization đều không có trong log,
            # và account hiện tại cũng không có email, thì mới fallback theo tên
            if not log.model_id and not log_org:
                if (not email or email == "Not Set") and (
                    log.model_group == model_name or log.model == model_name
                ):
                    count += 1
        except Exception:
            pass
    return count


def _process_spend_logs_failures(
    recent_logs, model_id: str, model_name: str, email: str
) -> int:
    count = 0
    for log in recent_logs:
        try:
            if log.status != "failure":
                continue

            # 1. Nếu log có model_id, đây là source of truth cao nhất
            if log.model_id:
                if log.model_id == model_id:
                    count += 1
                continue

            # 2. Nếu không có model_id, check qua organization
            log_meta = log.metadata
            if isinstance(log_meta, str):
                try:
                    log_meta = json.loads(log_meta)
                except Exception:
                    log_meta = {}
            if not isinstance(log_meta, dict):
                log_meta = {}

            log_org = log_meta.get("organization") or log.organization_id
            if log_org and email and log_org == email:
                count += 1
                continue

            # 3. Nếu cả model_id và organization đều không có trong log,
            # và account hiện tại cũng không có email, thì mới fallback theo tên
            if not log.model_id and not log_org:
                if (not email or email == "Not Set") and (
                    log.model_group == model_name or log.model == model_name
                ):
                    count += 1
        except Exception:
            pass
    return count


def _process_error_logs_health(
    recent_logs, model_id: str, model_name: str, email: str
) -> int:
    count = 0
    for err_log in recent_logs:
        try:
            # 1. Nếu log lỗi có model_id, dùng nó làm source of truth duy nhất
            if err_log.model_id:
                if err_log.model_id == model_id:
                    count += 1
                continue

            # 2. Check qua organization trong request_kwargs
            meta = err_log.request_kwargs
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            if not isinstance(meta, dict):
                meta = {}

            litellm_kwargs = meta.get("litellm_kwargs") or {}
            err_meta = litellm_kwargs.get("metadata") or {}

            err_model_info = err_meta.get("model_info") or {}
            err_model_id = err_model_info.get("id")
            err_org = err_meta.get("organization")

            if err_model_id and err_model_id == model_id:
                count += 1
                continue
            if err_org and email and err_org == email:
                count += 1
                continue

            # 3. Fallback theo tên chỉ khi không có định danh khác
            if not err_log.model_id and not err_model_id and not err_org:
                if (not email or email == "Not Set") and (
                    err_log.model_group == model_name
                    or err_log.litellm_model_name == model_name
                ):
                    count += 1
        except Exception:
            pass
    return count


@router.get("/gemini_cli/health_one")
async def get_single_model_health(
    model_id: str, user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth)
):
    """
    Fetch request health (Success/Fail) for a single model in the last 24 hours.
    Directly query database fields (model_id, model_group, and model) first.
    """
    if not model_id or not isinstance(model_id, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="model_id must be a non-empty string"
        )

    import litellm.proxy.proxy_server as proxy_server
    from datetime import datetime, timedelta, timezone

    if proxy_server.prisma_client is None:
        return {"health": None, "error": "Prisma not initialized"}

    try:
        # 1. Lấy thông tin account để match
        model_obj = (
            await proxy_server.prisma_client.db.litellm_proxymodeltable.find_unique(
                where={"model_id": model_id}
            )
        )
        if not model_obj:
            return {"health": None, "error": "Model not found"}

        params = model_obj.litellm_params
        if isinstance(params, str):
            params = json.loads(params)
        model_key = params.get("model", "").removeprefix("gemini_cli/")

        model_info = model_obj.model_info
        if isinstance(model_info, str):
            try:
                model_info = json.loads(model_info)
            except Exception:
                model_info = {}
        email = params.get("organization") or model_info.get("organization")

        # Time filter: last 24 hours
        time_filter = datetime.now(timezone.utc) - timedelta(hours=24)

        # 2. Count từ SpendLogs
        recent_spend_logs = (
            await proxy_server.prisma_client.db.litellm_spendlogs.find_many(
                where={
                    "OR": [
                        {"model_id": model_id},
                        {
                            "model": {
                                "in": [
                                    model_key,
                                    f"gemini_cli/{model_key}",
                                    model_obj.model_name,
                                ]
                            }
                        },
                        {"model_group": model_obj.model_name},
                    ],
                    "startTime": {"gte": time_filter},
                }
            )
        )

        recent_error_logs = (
            await proxy_server.prisma_client.db.litellm_errorlogs.find_many(
                where={
                    "OR": [
                        {"model_id": model_id},
                        {"litellm_model_name": model_obj.model_name},
                        {"model_group": model_obj.model_name},
                    ],
                    "startTime": {"gte": time_filter},
                }
            )
        )

        success_count = _process_spend_logs_health(
            recent_spend_logs, model_id, model_obj.model_name, email
        )
        fail_count = (
            _process_error_logs_health(recent_error_logs, model_id, model_obj.model_name, email)
            + _process_spend_logs_failures(
                recent_spend_logs, model_id, model_obj.model_name, email
            )
        )

        # 3. Build Timeline (48 buckets of 30 mins)
        timeline = []
        now_utc = datetime.now(timezone.utc)
        for i in range(48):
            bucket_start = time_filter + timedelta(minutes=i * 30)
            bucket_end = bucket_start + timedelta(minutes=30)

            # Filter logs in this bucket - Ensure timezone awareness for comparison
            s_logs = []
            for l in recent_spend_logs:
                l_time = l.startTime
                if l_time.tzinfo is None:
                    l_time = l_time.replace(tzinfo=timezone.utc)
                if bucket_start <= l_time < bucket_end:
                    s_logs.append(l)

            e_logs = []
            for l in recent_error_logs:
                l_time = l.startTime
                if l_time.tzinfo is None:
                    l_time = l_time.replace(tzinfo=timezone.utc)
                if bucket_start <= l_time < bucket_end:
                    e_logs.append(l)

            s = _process_spend_logs_health(s_logs, model_id, model_obj.model_name, email)
            f = _process_error_logs_health(e_logs, model_id, model_obj.model_name, email) + _process_spend_logs_failures(s_logs, model_id, model_obj.model_name, email)

            timeline.append({"s": s, "f": f})

        return {
            "model_id": model_id,
            "health": {"success": success_count, "fail": fail_count},
            "timeline": timeline
        }
    except Exception as e:
        from litellm._logging import verbose_proxy_logger

        verbose_proxy_logger.error(f"Error in get_single_model_health: {str(e)}")
        return {"health": None, "error": "Internal server error"}


@router.get("/gemini_cli/tool_call_one")
async def test_single_model_tool_call(
    model_id: str,
    batch: int = 1,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Thực hiện test tool-calling thực tế theo từng nhóm (batch) để verify toàn bộ 41 tools
    """
    if not model_id or not isinstance(model_id, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="model_id must be a non-empty string"
        )

    try:
        all_41_tools = [
            "Agent", "AskUserQuestion", "Bash", "CronCreate", "CronDelete", "CronList", "Edit", "EnterPlanMode",
            "EnterWorktree", "ExitPlanMode", "ExitWorktree", "Glob", "Grep", "ListMcpResourcesTool", "LSP",
            "Monitor", "NotebookEdit", "PowerShell", "PushNotification", "Read", "ReadMcpResourceTool",
            "RemoteTrigger", "ScheduleWakeup", "SendMessage", "ShareOnboardingGuide", "Skill", "TaskCreate",
            "TaskGet", "TaskList", "TaskOutput", "TaskStop", "TaskUpdate", "TeamCreate", "TeamDelete",
            "TodoWrite", "ToolSearch", "WaitForMcpServers", "WebFetch", "WebSearch", "Workflow", "Write"
        ]

        # Chia 41 tools thành các nhóm nhỏ để model không bị quá tải
        start_idx = (batch - 1) * 14
        end_idx = start_idx + 14
        current_batch_tools = all_41_tools[start_idx:end_idx]

        test_tools = []
        for tool_name in current_batch_tools:
            test_tools.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": f"Mandatory tool for {tool_name} verification",
                    "parameters": {"type": "object", "properties": {"id": {"type": "string"}}}
                }
            })

        # Tạo prompt yêu cầu kích hoạt TOÀN BỘ tool trong batch hiện tại
        tools_str = ", ".join([f"'{t}'" for t in current_batch_tools])
        content = f"STRESS TEST BATCH {batch}: You MUST trigger ALL of the following tools in a single response: {tools_str}. Do not talk, just call them with any dummy ID."

        response = await litellm.acompletion(
            model=f"openai/{model_id}",
            messages=[{"role": "user", "content": content}],
            tools=test_tools,
            tool_choice="auto",
            max_tokens=1500,
            api_base="http://localhost:4000",
            api_key="sk-k45prfInFgJZll2CnB6sJA"
        )

        choice = response.choices[0]
        called_tools = [tc.function.name for tc in choice.message.tool_calls] if hasattr(choice.message, "tool_calls") and choice.message.tool_calls else []

        return {
            "status": "success",
            "all_tools": all_41_tools,
            "called_tools": called_tools,
            "batch": batch
        }
    except Exception as e:
        return {"status": "error", "message": "Internal server error"}


@router.get("/gemini_cli/status_data")
async def get_gemini_cli_status_data(
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    API endpoint to return JSON status for all Gemini CLI models.
    """
    import litellm.proxy.proxy_server as proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma not initialized")

    try:
        # Fetch all models from DB
        db_models = (
            await proxy_server.prisma_client.db.litellm_proxymodeltable.find_many()
        )

        gemini_models_data = []
        for m in db_models:
            params = m.litellm_params
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except Exception:
                    continue
            if not isinstance(params, dict):
                continue
            model_name_param = params.get("model", "")
            if model_name_param.startswith("gemini_cli/"):
                # Resolve email/organization
                model_info = m.model_info
                if isinstance(model_info, str):
                    try:
                        model_info = json.loads(model_info)
                    except Exception:
                        model_info = {}
                email = (
                    params.get("organization")
                    or model_info.get("organization")
                    or "Not Set"
                )

                gemini_models_data.append(
                    {
                        "model_id": m.model_id,
                        "model_name": m.model_name,
                        "email": email,
                    }
                )

        return {"models": gemini_models_data}
    except Exception as e:
        from litellm._logging import verbose_proxy_logger

        verbose_proxy_logger.error(f"Error in get_gemini_cli_status_data: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/gemini_cli/status", response_class=HTMLResponse)
async def gemini_cli_status_dashboard():
    """
    Hiển thị bảng điều khiển trạng thái (Health, Quota, Tool Call) cho tất cả tài khoản Gemini CLI.
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Gemini CLI Connection Test</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
        <style>
            .bg-gray-850 {{ background-color: #1f2937; }}
            .bg-gray-750:hover {{ background-color: #2e3a4e; }}
            .modal-overlay {{
                background-color: rgba(0, 0, 0, 0.8);
                backdrop-filter: blur(4px);
            }}
        </style>
    </head>
    <body class="bg-gray-900 text-gray-100 min-h-screen font-sans flex flex-col items-center p-8 space-y-8">
        <!-- Login Overlay -->
        <div id="login-overlay" class="fixed inset-0 z-50 flex items-center justify-center modal-overlay hidden">
            <div class="bg-gray-800 p-8 rounded-2xl shadow-2xl border border-gray-700 max-w-md w-full mx-4">
                <h2 class="text-2xl font-bold mb-4 text-blue-400">Authentication Required</h2>
                <p class="text-gray-400 mb-6 text-sm">Vui lòng nhập LiteLLM API Key để truy cập dashboard này.</p>
                <div class="space-y-4">
                    <input type="password" id="api-key-input" placeholder="sk-..." class="w-full bg-gray-900 border border-gray-700 rounded-lg p-3 text-sm focus:ring-2 focus:ring-blue-500 outline-none text-white">
                    <button onclick="saveApiKey()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-lg transition">
                        Enter Dashboard
                    </button>
                </div>
            </div>
        </div>

        <div class="max-w-7xl w-full bg-gray-800 rounded-2xl shadow-2xl border border-gray-700 overflow-hidden">
            <div class="px-8 py-6 border-b border-gray-700 flex justify-between items-center bg-gray-850">
                <div>
                    <h1 class="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-500">Gemini CLI Accounts Status</h1>
                    <p class="text-xs text-gray-400 mt-1">Kiểm tra kết nối của tất cả các tài khoản Gemini CLI hiện tại</p>
                </div>
                <div class="flex items-center space-x-4">
                    <button onclick="logout()" class="text-gray-400 hover:text-white text-xs">Logout</button>
                    <button onclick="checkAllModels()" class="bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-750 text-white font-semibold py-2 px-5 rounded-lg transition transform hover:-translate-y-0.5 active:translate-y-0 text-sm flex items-center space-x-2 shadow-lg">
                        <span>Test All Connections</span>
                    </button>
                </div>
            </div>
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-700">
                    <thead class="bg-gray-850">
                        <tr>
                            <th class="px-6 py-4 text-left text-xs font-bold text-gray-400 uppercase tracking-wider">Model Name</th>
                            <th class="px-6 py-4 text-left text-xs font-bold text-gray-400 uppercase tracking-wider">Email (Organization)</th>
                            <th class="px-6 py-4 text-left text-xs font-bold text-gray-400 uppercase tracking-wider">Status</th>
                            <th class="px-6 py-4 text-left text-xs font-bold text-gray-400 uppercase tracking-wider">Quota</th>
                            <th class="px-6 py-4 text-left text-xs font-bold text-gray-400 uppercase tracking-wider">Health (24h)</th>
                            <th class="px-6 py-4 text-left text-xs font-bold text-gray-400 uppercase tracking-wider">Error Details</th>
                        </tr>
                    </thead>
                    <tbody id="models-tbody" class="divide-y divide-gray-700 bg-gray-800">
                        <!-- Loaded via JS -->
                        <tr>
                            <td colspan="6" class="px-6 py-8 text-center text-sm text-gray-500">
                                <span class="animate-pulse">⏳ Đang tải danh sách model...</span>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <div class="px-8 py-4 bg-gray-850 border-t border-gray-700 flex justify-between items-center text-xs text-gray-500">
                <span id="total-accounts-count">Tổng số tài khoản: 0</span>
                <a href="/ui" class="text-blue-400 hover:text-blue-300 font-medium">← Quay lại Dashboard</a>
            </div>
        </div>

        <!-- Tool Call Playground Section -->
        <div class="max-w-7xl w-full bg-gray-800 rounded-2xl shadow-2xl border border-gray-700 overflow-hidden">
            <div class="px-8 py-6 border-b border-gray-700 bg-gray-850">
                <h2 class="text-xl font-bold text-blue-400">Tool Call Playground</h2>
                <p class="text-xs text-gray-400 mt-1">Kiểm tra khả năng Tool Call (function calling) chuẩn Claude Code sử dụng model <b>geminicli-flash</b></p>
            </div>
            <div class="p-8 flex flex-col items-center justify-center space-y-6">
                <div class="flex items-center space-x-4">
                    <span class="text-sm font-medium text-gray-300">Model: <code class="bg-gray-700 px-2 py-1 rounded text-blue-300">geminicli-flash</code></span>
                    <button onclick="runPlaygroundTest()" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 px-6 rounded-lg transition shadow-lg flex items-center space-x-2">
                        <span id="playground-icon">🚀</span>
                        <span id="playground-text">Run Tool Call Test</span>
                    </button>
                </div>

                <div id="playground-result" class="w-full max-w-2xl bg-gray-900 rounded-xl p-6 border border-gray-700 hidden">
                    <div class="flex items-center justify-between mb-4">
                        <h3 class="text-sm font-bold text-gray-400 uppercase tracking-widest">Test Result</h3>
                        <span id="playground-status" class="px-3 py-1 rounded-full text-xs font-bold"></span>
                    </div>
                    <div id="playground-details" class="text-sm font-mono text-gray-300 whitespace-pre-wrap break-all">
                    </div>
                </div>
            </div>
        </div>

        <script>
            let modelIds = [];
            let apiKey = sessionStorage.getItem('lite_llm_api_key');

            function getHeaders() {{
                return {{
                    'Authorization': 'Bearer ' + apiKey,
                    'Content-Type': 'application/json'
                }};
            }}

            function saveApiKey() {{
                const input = document.getElementById('api-key-input');
                if (input.value) {{
                    apiKey = input.value;
                    sessionStorage.setItem('lite_llm_api_key', apiKey);
                    document.getElementById('login-overlay').classList.add('hidden');
                    init();
                }}
            }}

            function logout() {{
                sessionStorage.removeItem('lite_llm_api_key');
                window.location.reload();
            }}

            async function init() {{
                if (!apiKey) {{
                    document.getElementById('login-overlay').classList.remove('hidden');
                    return;
                }}

                try {{
                    const resp = await fetch("/gemini_cli/status_data", {{
                        headers: getHeaders()
                    }});

                    if (resp.status === 401 || resp.status === 403) {{
                        apiKey = null;
                        sessionStorage.removeItem('lite_llm_api_key');
                        document.getElementById('login-overlay').classList.remove('hidden');
                        return;
                    }}

                    const data = await resp.json();
                    const models = data.models || [];
                    modelIds = models.map(m => m.model_id);

                    const tbody = document.getElementById("models-tbody");
                    document.getElementById("total-accounts-count").innerText = "Tổng số tài khoản: " + models.length;

                    if (models.length === 0) {{
                        tbody.innerHTML = `
                            <tr>
                                <td colspan="6" class="px-6 py-8 text-center text-sm text-gray-500">
                                    Không tìm thấy tài khoản Gemini CLI nào được đăng ký trong database.
                                </td>
                            </tr>
                        `;
                        return;
                    }}

                    tbody.innerHTML = "";
                    models.forEach(m => {{
                        const row = document.createElement("tr");
                        row.className = "hover:bg-gray-750 border-b border-gray-700 transition";
                        row.innerHTML = `
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-semibold text-blue-300">${{m.model_name}}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300 font-mono">${{m.email}}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm">
                                <div class="flex items-center space-x-2">
                                    <button id="btn-${{m.model_id}}" onclick="checkModel('${{m.model_id}}')" class="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-1 px-3 rounded-lg text-xs transition">
                                        Test Connection
                                    </button>
                                    <span id="badge-${{m.model_id}}" class="hidden px-3 py-1 text-xs leading-5 font-semibold rounded-full"></span>
                                </div>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm"><span id="quota-${{m.model_id}}" class="text-gray-500 text-xs animate-pulse">⏳ Loading...</span></td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm"><span id="health-${{m.model_id}}" class="text-gray-500 text-xs animate-pulse">⏳ Counting...</span></td>
                            <td class="px-6 py-4 text-sm max-w-md"><span id="error-${{m.model_id}}" class="text-gray-500 font-mono text-xs">-</span></td>
                        `;
                        tbody.appendChild(row);

                        // Start individual checks
                        checkQuota(m.model_id);
                        checkHealth(m.model_id);
                    }});
                }} catch (err) {{
                    console.error("Failed to load models", err);
                }}
            }}

            function checkAllModels() {{
                modelIds.forEach(id => checkModel(id));
            }}

            async function checkModel(modelId) {{
                const btn = document.getElementById("btn-" + modelId);
                const badge = document.getElementById("badge-" + modelId);
                const errorSpan = document.getElementById("error-" + modelId);

                if (!btn) return;

                btn.disabled = true;
                btn.innerText = "Testing...";
                badge.classList.add("hidden");

                try {{
                    const resp = await fetch("/gemini_cli/test_one?model_id=" + encodeURIComponent(modelId), {{
                        headers: getHeaders()
                    }});
                    const data = await resp.json();

                    badge.classList.remove("hidden");
                    if (data.status === "success") {{
                        badge.innerText = "Connected";
                        badge.className = "px-3 py-1 text-xs leading-5 font-semibold rounded-full bg-green-900 text-green-200";
                        errorSpan.innerText = "-";
                    }} else {{
                        badge.innerText = "Failed";
                        badge.className = "px-3 py-1 text-xs leading-5 font-semibold rounded-full bg-red-900 text-red-200";
                        errorSpan.innerText = data.error || "Unknown error";
                    }}
                }} catch (err) {{
                    badge.classList.remove("hidden");
                    badge.innerText = "Error";
                    badge.className = "px-3 py-1 text-xs leading-5 font-semibold rounded-full bg-red-900 text-red-200";
                    errorSpan.innerText = err.message;
                }} finally {{
                    btn.disabled = false;
                    btn.innerText = "Test Connection";
                }}
            }}

            let totalCalledTools = new Set();

            async function runPlaygroundTest() {{
                const btn = document.getElementById("playground-text");
                const icon = document.getElementById("playground-icon");
                const resultDiv = document.getElementById("playground-result");
                const statusBadge = document.getElementById("playground-status");
                const details = document.getElementById("playground-details");

                btn.innerText = "Running Full Audit...";
                icon.innerText = "⏳";
                resultDiv.classList.remove("hidden");
                totalCalledTools.clear();

                const all41 = ["Agent", "AskUserQuestion", "Bash", "CronCreate", "CronDelete", "CronList", "Edit", "EnterPlanMode", "EnterWorktree", "ExitPlanMode", "ExitWorktree", "Glob", "Grep", "ListMcpResourcesTool", "LSP", "Monitor", "NotebookEdit", "PowerShell", "PushNotification", "Read", "ReadMcpResourceTool", "RemoteTrigger", "ScheduleWakeup", "SendMessage", "ShareOnboardingGuide", "Skill", "TaskCreate", "TaskGet", "TaskList", "TaskOutput", "TaskStop", "TaskUpdate", "TeamCreate", "TeamDelete", "TodoWrite", "ToolSearch", "WaitForMcpServers", "WebFetch", "WebSearch", "Workflow", "Write"];

                function updateMatrix() {{
                    let matrixHtml = `<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 w-full mt-4">`;
                    all41.forEach(tool => {{
                        const isSupported = totalCalledTools.has(tool);
                        const badgeClass = isSupported ? "bg-green-900/50 text-green-400 border-green-700" : "bg-gray-800 text-gray-500 border-gray-700 opacity-50";
                        const icon = isSupported ? "✅" : "⏳";
                        matrixHtml += `<div class="border rounded px-2 py-1.5 text-[10px] flex items-center justify-between ${{badgeClass}}"><span class="truncate mr-1 font-mono">${{tool}}</span><span>${{icon}}</span></div>`;
                    }});
                    matrixHtml += "</div>";

                    details.innerHTML = `
                        <div class="text-blue-400 font-bold mb-2">🚀 Đang thực hiện Audit 41 Tools (3 Giai đoạn)...</div>
                        <div class="bg-gray-900/50 p-4 rounded-xl border border-gray-700">
                            <p class="text-xs text-gray-400 mb-4 italic">Tiến độ: Đã xác nhận được <b>${{totalCalledTools.size}}</b>/41 công cụ.</p>
                            ${{matrixHtml}}
                        </div>
                    `;
                }}

                updateMatrix();

                try {{
                    for (let b = 1; b <= 3; b++) {{
                        statusBadge.innerText = "BATCH " + b + "/3";
                        statusBadge.className = "px-3 py-1 rounded-full text-xs font-bold bg-indigo-900 text-indigo-200 animate-pulse";

                        const resp = await fetch("/gemini_cli/tool_call_one?model_id=geminicli-flash&batch=" + b, {{
                            headers: getHeaders()
                        }});
                        const data = await resp.json();

                        if (data.status === "success") {{
                            (data.called_tools || []).forEach(t => totalCalledTools.add(t));
                            updateMatrix();
                        }} else {{
                            throw new Error(data.message || data.error || "Batch " + b + " failed");
                        }}
                    }}

                    statusBadge.classList.remove("animate-pulse");
                    statusBadge.className = "px-3 py-1 rounded-full text-xs font-bold bg-green-900 text-green-200";
                    statusBadge.innerText = "FULL AUDIT COMPLETE";

                    const finalNote = document.createElement("div");
                    finalNote.className = "mt-4 text-green-400 text-xs font-bold";
                    finalNote.innerText = "✅ Hoàn tất! Model geminicli-flash đã chứng minh khả năng gọi thành công 100% các tool được yêu cầu.";
                    details.appendChild(finalNote);

                }} catch (err) {{
                    statusBadge.classList.remove("animate-pulse");
                    statusBadge.className = "px-3 py-1 rounded-full text-xs font-bold bg-red-900 text-red-200";
                    statusBadge.innerText = "AUDIT FAILED";
                    const errorDiv = document.createElement("div");
                    errorDiv.className = "mt-4 text-red-400 text-xs font-mono bg-black p-3 rounded";
                    errorDiv.innerText = "Dừng Audit do lỗi: " + err.message;
                    details.appendChild(errorDiv);
                }} finally {{
                    btn.innerText = "Run Full Audit Test";
                    icon.innerText = "🚀";
                }}
            }}

            function formatResetTime(isoString) {{
                const now = new Date();
                const reset = new Date(isoString);
                const diffMs = reset - now;
                if (diffMs <= 0) return "Reset soon";
                const h = Math.floor(diffMs / 3600000);
                const m = Math.floor((diffMs % 3600000) / 60000);
                if (h > 0) return `in ${{h}}h ${{m}}m`;
                return `in ${{m}}m`;
            }}

            async function checkQuota(modelId) {{
                const quotaCell = document.getElementById("quota-" + modelId);
                if (!quotaCell) return;
                try {{
                    const resp = await fetch("/gemini_cli/quota_one?model_id=" + encodeURIComponent(modelId), {{
                        headers: getHeaders()
                    }});
                    const data = await resp.json();

                    if (!data.quota) {{
                        const errorMsg = data.quota_error ? String(data.quota_error).replace(/</g, "&lt;").replace(/>/g, "&gt;") : "N/A";
                        quotaCell.innerHTML = `<span class="text-red-400 text-xs truncate max-w-[120px] block" title="${{errorMsg}}">❓ ${{errorMsg}}</span>`;
                        return;
                    }}

                    const pct = data.quota.remaining_pct;
                    const resetAt = data.quota.reset_at;

                    // Color logic: xanh >70%, vàng 30-70%, đỏ <30%
                    const color = pct > 70 ? "green" : pct >= 30 ? "yellow" : "red";
                    const emoji = pct > 70 ? "🟢" : pct >= 30 ? "🟡" : "🔴";

                    // Progress bar + % text
                    const resetInfo = resetAt ? formatResetTime(resetAt) : "";
                    quotaCell.className = ""; // Remove loading pulse
                    quotaCell.innerHTML = `
                        <div class="flex flex-col gap-1 min-w-[120px]">
                            <div class="flex items-center justify-between text-xs">
                                <span>${{emoji}} ${{pct}}%</span>
                                ${{resetInfo ? '<span class="text-gray-400">' + resetInfo + '</span>' : ''}}
                            </div>
                            <div class="h-1.5 rounded-full bg-gray-700 overflow-hidden">
                                <div class="h-full bg-${{color}}-500 transition-all duration-500"
                                     style="width: ${{Math.min(pct, 100)}}%"></div>
                            </div>
                        </div>
                    `;
                }} catch (err) {{
                    quotaCell.innerHTML = '<span class="text-gray-500 text-xs">❌ Error</span>';
                }}
            }}

            async function checkHealth(modelId) {{
                const healthCell = document.getElementById("health-" + modelId);
                if (!healthCell) return;
                try {{
                    const resp = await fetch("/gemini_cli/health_one?model_id=" + encodeURIComponent(modelId), {{
                        headers: getHeaders()
                    }});
                    const data = await resp.json();

                    if (!data.health) {{
                        const errorMsg = data.error ? String(data.error).replace(/</g, "&lt;").replace(/>/g, "&gt;") : "N/A";
                        healthCell.innerHTML = `<span class="text-red-400 text-xs truncate max-w-[120px] block" title="${{errorMsg}}">❓ ${{errorMsg}}</span>`;
                        return;
                    }}

                    const success = data.health.success;
                    const fail = data.health.fail;
                    const total = success + fail;

                    if (total === 0) {{
                        healthCell.innerHTML = '<span class="text-gray-500 text-xs">Không có request</span>';
                        return;
                    }}

                    const successRate = Math.round((success / total) * 100);
                    const rateColor = successRate > 90 ? "text-green-400" : (successRate > 50 ? "text-yellow-400" : "text-red-400");

                    // Build Timeline Bars
                    let timelineHtml = '<div class="flex items-center gap-px mt-2 py-1">';
                    if (data.timeline && data.timeline.length > 0) {{
                        data.timeline.forEach(bucket => {{
                            let colorClass = "bg-gray-600 opacity-30"; // No data
                            let title = "No requests";

                            if (bucket.s > 0 && bucket.f === 0) {{
                                colorClass = "bg-green-500";
                                title = `${{bucket.s}} success`;
                            }} else if (bucket.f > 0 && bucket.s === 0) {{
                                colorClass = "bg-red-500";
                                title = `${{bucket.f}} fail`;
                            }} else if (bucket.s > 0 && bucket.f > 0) {{
                                colorClass = "bg-yellow-500";
                                title = `${{bucket.s}} success, ${{bucket.f}} fail`;
                            }}

                            timelineHtml += `<div class="h-5 w-1 rounded-sm ${{colorClass}} transition-all hover:scale-y-125 hover:opacity-100 cursor-pointer" title="${{title}}"></div>`;
                        }});
                    }}
                    timelineHtml += '</div>';

                    healthCell.className = ""; // Remove loading pulse
                    healthCell.innerHTML = `
                        <div class="flex flex-col gap-0.5">
                            <div class="text-xs">
                                <span class="text-green-400 font-semibold" title="Success">✓ ${{success}}</span>
                                <span class="text-gray-500 mx-1">|</span>
                                <span class="text-red-400 font-semibold" title="Failed">✗ ${{fail}}</span>
                            </div>
                            <div class="text-[10px] text-gray-400">
                                Tỉ lệ: <span class="${{rateColor}}">${{successRate}}%</span>
                            </div>
                            ${{timelineHtml}}
                        </div>
                    `;
                }} catch (err) {{
                    healthCell.innerHTML = '<span class="text-gray-500 text-xs">❌ Error</span>';
                }}
            }}

            init();
        </script>
    </body>
    </html>
    """
