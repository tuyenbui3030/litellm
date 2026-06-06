"""
Constants and helpers for Gemini CLI OAuth.
"""

import os
import platform
from typing import Optional, Union

import httpx

from litellm.llms.base_llm.chat.transformation import BaseLLMException

# OAuth + API constants (derived from Google Cloud Code Assist / Gemini CLI)
GEMINI_CLI_CLIENT_ID = os.getenv("GEMINI_CLI_CLIENT_ID", "")
GEMINI_CLI_CLIENT_SECRET = os.getenv("GEMINI_CLI_CLIENT_SECRET", "")
GEMINI_CLI_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GEMINI_CLI_TOKEN_URL = "https://oauth2.googleapis.com/token"

GEMINI_CLI_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

GEMINI_CLI_API_BASE = "https://cloudcode-pa.googleapis.com/v1internal"
GEMINI_CLI_API_CLIENT = "google-genai-sdk/1.41.0 gl-node/v22.19.0"
GEMINI_CLI_VERSION = "0.34.0"


class GeminiCLIAuthError(BaseLLMException):
    def __init__(
        self,
        status_code,
        message,
        request: Optional[httpx.Request] = None,
        response: Optional[httpx.Response] = None,
        headers: Optional[Union[httpx.Headers, dict]] = None,
        body: Optional[dict] = None,
    ):
        super().__init__(
            status_code=status_code,
            message=message,
            request=request,
            response=response,
            headers=headers,
            body=body,
        )


class GetAccessTokenError(GeminiCLIAuthError):
    pass


class RefreshAccessTokenError(GeminiCLIAuthError):
    pass


class FetchProjectIdError(GeminiCLIAuthError):
    pass


def _gemini_cli_arch() -> str:
    a = platform.machine().lower()
    if a in ("x86_64", "amd64"):
        return "x64"
    if a in ("i386", "i686"):
        return "x86"
    if a in ("arm64", "aarch64"):
        return "arm64"
    return a


def get_gemini_cli_user_agent(model: str = "unknown") -> str:
    os_type = platform.system().lower()
    if os_type == "darwin":
        os_type = "darwin"
    elif os_type == "windows":
        os_type = "win32"
    elif os_type == "linux":
        os_type = "linux"

    arch = _gemini_cli_arch()
    return f"GeminiCLI/{GEMINI_CLI_VERSION}/{model} ({os_type}; {arch}; terminal)"


def get_oauth_platform_enum() -> int:
    os_type = platform.system().lower()
    arch = _gemini_cli_arch()
    if os_type == "darwin":
        return 2 if arch == "arm64" else 1
    if os_type == "linux":
        return 4 if arch == "arm64" else 3
    if os_type == "windows":
        return 5
    return 0


def get_oauth_client_metadata() -> dict:
    return {"ideType": 9, "platform": get_oauth_platform_enum(), "pluginType": 2}
