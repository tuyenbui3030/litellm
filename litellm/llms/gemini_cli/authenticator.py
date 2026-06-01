import hashlib
import base64
import json
import os
import secrets
import socket
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple

import httpx

from litellm._logging import verbose_logger
from litellm.llms.custom_httpx.http_handler import _get_httpx_client

from .common_utils import (
    GEMINI_CLI_API_BASE,
    GEMINI_CLI_AUTHORIZE_URL,
    GEMINI_CLI_CLIENT_ID,
    GEMINI_CLI_CLIENT_SECRET,
    GEMINI_CLI_SCOPES,
    GEMINI_CLI_TOKEN_URL,
    FetchProjectIdError,
    GetAccessTokenError,
    RefreshAccessTokenError,
    get_oauth_client_metadata,
)

TOKEN_EXPIRY_SKEW_SECONDS = 60
OAUTH_TIMEOUT_SECONDS = 120

def generate_pkce_pair() -> Tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    sha256_hash = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(sha256_hash).decode("ascii").replace("=", "")
    return verifier, challenge


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        # 9router checks for /callback or /auth/callback
        if parsed_path.path not in ["/callback", "/auth/callback"]:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        query = urllib.parse.parse_qs(parsed_path.query)

        self.server.auth_code = query.get("code", [None])[0]  # type: ignore
        self.server.auth_error = query.get("error", [None])[0]  # type: ignore
        self.server.received_state = query.get("state", [None])[0]  # type: ignore

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        if self.server.auth_code:  # type: ignore
            html = """
            <html>
            <body style='font-family: sans-serif; text-align: center; padding-top: 50px;'>
                <h1 style='color: #22c55e;'>Authentication Successful</h1>
                <p>You can close this window and return to your terminal.</p>
                <script>setTimeout(function() { window.close(); }, 3000);</script>
            </body>
            </html>
            """
        else:
            html = f"<html><body><h1>Authentication Failed</h1><p>Error: {self.server.auth_error}</p></body></html>"  # type: ignore
            
        self.wfile.write(html.encode("utf-8"))
        
        # Trigger shutdown
        threading.Thread(target=self.server.shutdown).start()

    def log_message(self, format, *args):
        # Suppress logging
        pass


class Authenticator:
    def __init__(self) -> None:
        self.token_dir = os.getenv(
            "GEMINI_CLI_TOKEN_DIR",
            os.path.expanduser("~/.config/litellm/gemini_cli"),
        )
        self.auth_file = os.path.join(
            self.token_dir, os.getenv("GEMINI_CLI_AUTH_FILE", "auth.json")
        )
        self._ensure_token_dir()

    def get_api_base(self) -> str:
        return os.getenv("GEMINI_CLI_API_BASE") or GEMINI_CLI_API_BASE

    def get_credentials(self, litellm_params: Optional[dict] = None) -> Tuple[str, str]:
        """Returns (access_token, project_id)"""
        # 1. Check in litellm_params (Highest priority - for dynamic Proxy config)
        if litellm_params:
            project_id = litellm_params.get("gemini_cli_project_id")
            access_token = litellm_params.get("gemini_cli_access_token")
            refresh_token = litellm_params.get("gemini_cli_refresh_token")

            if refresh_token:
                try:
                    refreshed = self._refresh_tokens(refresh_token)
                    new_access_token = refreshed["access_token"]
                    # If project_id missing or decrypt failed, fetch it
                    if not project_id:
                        project_id = self._fetch_project_id(new_access_token)
                    return new_access_token, project_id
                except Exception as e:
                    if access_token and project_id:
                        return access_token, project_id
                    raise e

            if access_token and project_id:
                return access_token, project_id

        # 2. Check environment variables
        env_access_token = os.getenv("GEMINI_CLI_ACCESS_TOKEN")
        env_project_id = os.getenv("GEMINI_CLI_PROJECT_ID")
        if env_access_token and env_project_id:
            return env_access_token, env_project_id

        # 3. Check for auth file (For local development)
        auth_data = self._read_auth_file()
        
        if auth_data:
            access_token = auth_data.get("access_token")
            project_id = auth_data.get("project_id")
            
            if access_token and project_id and not self._is_token_expired(auth_data):
                return access_token, project_id
                
            refresh_token = auth_data.get("refresh_token")
            if refresh_token:
                try:
                    refreshed = self._refresh_tokens(refresh_token)
                    access_token = refreshed["access_token"]
                    # If project_id is missing, try to fetch it
                    if not project_id:
                        project_id = self._fetch_project_id(access_token)
                    
                    refreshed["project_id"] = project_id
                    self._write_auth_file(refreshed)
                    return access_token, project_id
                except Exception as exc:
                    verbose_logger.warning(
                        "Gemini CLI credential refresh failed, re-login required: %s", exc
                    )

        # Fallback to full login flow - only allowed in non-proxy (interactive) environments
        import litellm
        if getattr(litellm, "proxy_server_started", False):
            raise GetAccessTokenError(
                message=(
                    "Gemini CLI credentials not found or expired. "
                    "Please re-authenticate via /gemini_cli/login endpoint."
                ),
                status_code=401,
            )

        print(  # noqa: T201
            "Sign in with Gemini CLI (Google Cloud Code Assist) required.\n"
            "A browser window will open shortly to complete the OAuth flow...",
            flush=True,
        )
        tokens = self._login_loopback()
        access_token = tokens["access_token"]
        project_id = self._fetch_project_id(access_token)
        tokens["project_id"] = project_id
        
        self._write_auth_file(tokens)
        
        print(f"Successfully authenticated as project: {project_id}") # noqa: T201
        
        return access_token, project_id

    def _ensure_token_dir(self) -> None:
        if not os.path.exists(self.token_dir):
            os.makedirs(self.token_dir, exist_ok=True)

    def _read_auth_file(self) -> Optional[Dict[str, Any]]:
        try:
            with open(self.auth_file, "r") as f:
                return json.load(f)
        except IOError:
            return None
        except json.JSONDecodeError as exc:
            verbose_logger.warning("Invalid Gemini CLI auth file: %s", exc)
            return None

    def _write_auth_file(self, data: Dict[str, Any]) -> None:
        try:
            with open(self.auth_file, "w") as f:
                json.dump(data, f)
        except IOError as exc:
            verbose_logger.error("Failed to write Gemini CLI auth file: %s", exc)

    def _is_token_expired(self, auth_data: Dict[str, Any]) -> bool:
        expires_at = auth_data.get("expires_at")
        if expires_at is None:
            return True
        return time.time() >= float(expires_at) - TOKEN_EXPIRY_SKEW_SECONDS

    def _find_available_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def _login_loopback(self) -> Dict[str, Any]:
        # This remains for local use
        port = self._find_available_port()
        redirect_uri = f"http://127.0.0.1:{port}/callback"
        
        # Generate PKCE pair
        code_verifier, code_challenge = generate_pkce_pair()
        
        auth_url, state = self.generate_auth_url(redirect_uri, code_challenge=code_challenge)
        
        server = HTTPServer(("127.0.0.1", port), OAuthCallbackHandler)
        server.auth_code = None  # type: ignore
        server.auth_error = None  # type: ignore
        server.received_state = None  # type: ignore

        try:
            webbrowser.open(auth_url)
        except Exception:
            pass
        
        print(f"\nRemote Server detected. Please visit this URL to authenticate:\n{auth_url}\n") # noqa: T201

        # Wait for the callback
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        
        # Wait up to timeout
        deadline = time.time() + OAUTH_TIMEOUT_SECONDS
        while time.time() < deadline:
            if getattr(server, "auth_code", None) or getattr(server, "auth_error", None):
                break
            time.sleep(0.5)
        
        server.shutdown()
        thread.join()
        
        auth_code = getattr(server, "auth_code", None)
        if not auth_code:
            # Fallback to manual input for true headless environments
            print("Loopback timed out. Please paste the 'code' or full callback URL here:") # noqa: T201
            manual_input = input("> ").strip()
            return self.handle_callback(manual_input, redirect_uri, state, code_verifier=code_verifier)

        return self._exchange_code_for_tokens(auth_code, redirect_uri, code_verifier=code_verifier)

    def generate_auth_url(self, redirect_uri: str, code_challenge: Optional[str] = None) -> Tuple[str, str]:
        state = secrets.token_urlsafe(16)
        params_dict = {
            "client_id": GEMINI_CLI_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(GEMINI_CLI_SCOPES),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        if code_challenge:
            params_dict["code_challenge"] = code_challenge
            params_dict["code_challenge_method"] = "S256"
            
        params = urllib.parse.urlencode(params_dict, quote_via=urllib.parse.quote)
        return f"{GEMINI_CLI_AUTHORIZE_URL}?{params}", state

    def handle_callback(self, callback_input: str, redirect_uri: str, state: Optional[str] = None, code_verifier: Optional[str] = None) -> Dict[str, Any]:
        """Parses code from URL or raw input and exchanges for tokens"""
        code = callback_input
        if "code=" in callback_input:
            parsed = urllib.parse.urlparse(callback_input)
            query = urllib.parse.parse_qs(parsed.query)
            code = query.get("code", [code])[0]
            received_state = query.get("state", [None])[0]
            if state and received_state and received_state != state:
                raise ValueError("OAuth state mismatch")
        
        tokens = self._exchange_code_for_tokens(code, redirect_uri, code_verifier=code_verifier)
        project_id = self._fetch_project_id(tokens["access_token"])
        tokens["project_id"] = project_id
        return tokens

    def _exchange_code_for_tokens(self, code: str, redirect_uri: str, code_verifier: Optional[str] = None) -> Dict[str, Any]:
        try:
            client = _get_httpx_client()
            data = {
                "grant_type": "authorization_code",
                "client_id": GEMINI_CLI_CLIENT_ID,
                "client_secret": GEMINI_CLI_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
            }
            if code_verifier:
                data["code_verifier"] = code_verifier
                
            resp = client.post(
                GEMINI_CLI_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                data=data,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise GetAccessTokenError(
                message=f"Token exchange failed: {exc} - Response: {exc.response.text}",
                status_code=exc.response.status_code,
            )
        except Exception as exc:
            raise GetAccessTokenError(
                message=f"Token exchange failed: {exc}",
                status_code=400,
            )

        if "access_token" not in data:
            raise GetAccessTokenError(
                message=f"Token exchange response missing access_token: {data}",
                status_code=400,
            )
            
        expires_in = data.get("expires_in", 3599)
        
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_at": time.time() + expires_in,
        }

    def _refresh_tokens(self, refresh_token: str) -> Dict[str, Any]:
        try:
            client = _get_httpx_client()
            resp = client.post(
                GEMINI_CLI_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": GEMINI_CLI_CLIENT_ID,
                    "client_secret": GEMINI_CLI_CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise RefreshAccessTokenError(
                message=f"Refresh token failed: {exc}",
                status_code=exc.response.status_code,
            )
        except Exception as exc:
            raise RefreshAccessTokenError(
                message=f"Refresh token failed: {exc}",
                status_code=400,
            )

        access_token = data.get("access_token")
        if not access_token:
            raise RefreshAccessTokenError(
                message=f"Refresh response missing access_token: {data}",
                status_code=400,
            )

        expires_in = data.get("expires_in", 3599)
        return {
            "access_token": access_token,
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_at": time.time() + expires_in,
        }

    def _fetch_project_id(self, access_token: str) -> str:
        try:
            client = _get_httpx_client()
            resp = client.post(
                "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "google-api-nodejs-client/9.15.1",
                    "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
                    "Client-Metadata": json.dumps(get_oauth_client_metadata()),
                },
                json={
                    "metadata": get_oauth_client_metadata(),
                    "mode": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise FetchProjectIdError(
                message=f"Failed to fetch project ID: {exc}",
                status_code=exc.response.status_code,
            )
        except Exception as exc:
            raise FetchProjectIdError(
                message=f"Failed to fetch project ID: {exc}",
                status_code=400,
            )

        project_field = data.get("cloudaicompanionProject")
        project_id = ""
        
        if isinstance(project_field, str):
            project_id = project_field.strip()
        elif isinstance(project_field, dict):
            project_id = project_field.get("id", "").strip()

        if not project_id:
            raise FetchProjectIdError(
                message=f"No project ID found in response: {data}",
                status_code=400,
            )

        return project_id
