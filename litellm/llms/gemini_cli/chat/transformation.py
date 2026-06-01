import json as _json
from typing import Any, Dict, List, Optional

import httpx

from litellm.exceptions import AuthenticationError
from litellm.llms.gemini.chat.transformation import GoogleAIStudioGeminiConfig
from litellm.types.llms.openai import AllMessageValues

from ..authenticator import Authenticator
from ..common_utils import (
    GEMINI_CLI_API_CLIENT,
    FetchProjectIdError,
    GetAccessTokenError,
    get_gemini_cli_user_agent,
)


def _unwrap_gemini_cli_response_json(response_json: dict) -> dict:
    """Unwrap the gemini_cli response envelope if present.

    gemini_cli wraps every response (both streaming chunks and non-streaming)
    inside an extra layer::

        {
            "response": { "candidates": [...], "usageMetadata": {...}, ... },
            "traceId": "...",
            "metadata": { ... },
        }

    Standard Vertex AI / Google AI Studio responses have ``candidates`` and
    ``usageMetadata`` at the top level, so this helper is a no-op for them.
    """
    if "response" in response_json and (
        "candidates" not in response_json or "usageMetadata" not in response_json
    ):
        return response_json["response"]
    return response_json


def _make_gemini_cli_iterator():
    """Return the GeminiCLIModelResponseIterator class.

    Defined as a factory function to defer the import of ModelResponseIterator
    and avoid circular imports at module-load time.
    """
    from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import (
        ModelResponseIterator,
    )

    class GeminiCLIModelResponseIterator(ModelResponseIterator):
        """Streaming iterator for gemini_cli that unwraps the provider-specific
        response envelope before delegating to the standard Vertex AI iterator.

        gemini_cli SSE chunks arrive as::

            data: {"response": {"candidates": [...], ...}, "traceId": "...", ...}

        This subclass strips the outer wrapper so that the parent ``chunk_parser``
        receives the same structure as a regular Gemini streaming chunk.

        Because ``chunk_parser`` is called by ``_common_chunk_parsing_logic``
        via ``self.chunk_parser``, Python's normal method-resolution order
        ensures our override is invoked for every chunk.
        """

        def chunk_parser(self, chunk: dict):
            chunk = _unwrap_gemini_cli_response_json(chunk)
            return super().chunk_parser(chunk)

    return GeminiCLIModelResponseIterator


# Cache the class after first construction so repeated streaming calls don't
# rebuild it on every request.
_GeminiCLIModelResponseIterator = None


def GeminiCLIModelResponseIterator(
    streaming_response,
    sync_stream: bool,
    logging_obj,
    response_headers=None,
):
    """Factory that returns a GeminiCLIModelResponseIterator instance.

    The actual class is constructed lazily to avoid circular imports.
    """
    global _GeminiCLIModelResponseIterator
    if _GeminiCLIModelResponseIterator is None:
        _GeminiCLIModelResponseIterator = _make_gemini_cli_iterator()
    return _GeminiCLIModelResponseIterator(
        streaming_response=streaming_response,
        sync_stream=sync_stream,
        logging_obj=logging_obj,
        response_headers=response_headers,
    )


class GeminiCLIConfig(GoogleAIStudioGeminiConfig):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.authenticator = Authenticator()

    def get_supported_openai_params(self, model: str) -> List[str]:
        return super().get_supported_openai_params(model)

    def validate_environment(
        self,
        headers: Optional[dict],
        model: str,
        messages: List[AllMessageValues],
        optional_params: dict,
        litellm_params: dict,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> dict:
        # Standard validation
        validated_headers = super().validate_environment(
            headers, model, messages, optional_params, litellm_params, api_key, api_base
        )

        try:
            access_token, project_id = self.authenticator.get_credentials(
                litellm_params
            )
            # Stash project_id in litellm_params so we can use it in request transformation
            litellm_params["gemini_cli_project_id"] = project_id
        except (GetAccessTokenError, FetchProjectIdError) as e:
            raise AuthenticationError(
                model=model,
                llm_provider="gemini_cli",
                message=str(e),
            )

        # Build headers
        default_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": get_gemini_cli_user_agent(model),
            "X-Goog-Api-Client": GEMINI_CLI_API_CLIENT,
            "Accept": (
                "text/event-stream"
                if optional_params.get("stream")
                else "application/json"
            ),
        }

        return {**validated_headers, **default_headers}

    def transform_response(
        self,
        model: str,
        raw_response: httpx.Response,
        model_response,
        logging_obj,
        request_data: Dict,
        messages: List[AllMessageValues],
        optional_params: Dict,
        litellm_params: Dict,
        encoding: Any,
        api_key: Optional[str] = None,
        json_mode: Optional[bool] = None,
    ):
        """Override to unwrap the gemini_cli response envelope before parsing.

        gemini_cli wraps non-streaming responses as::

            {"response": {"candidates": [...], ...}, "traceId": "...", "metadata": {...}}

        We detect and unwrap this before delegating to the parent implementation.
        """
        try:
            response_json = raw_response.json()
            unwrapped = _unwrap_gemini_cli_response_json(response_json)
            if unwrapped is not response_json:
                # Re-create a minimal httpx.Response with the unwrapped body so
                # the parent transform_response can parse it transparently.
                raw_response = httpx.Response(
                    status_code=raw_response.status_code,
                    headers=raw_response.headers,
                    content=_json.dumps(unwrapped).encode(),
                    request=raw_response.request,
                )
        except Exception:
            # If anything goes wrong, fall through and let the parent handle it
            pass

        return super().transform_response(
            model=model,
            raw_response=raw_response,
            model_response=model_response,
            logging_obj=logging_obj,
            request_data=request_data,
            messages=messages,
            optional_params=optional_params,
            litellm_params=litellm_params,
            encoding=encoding,
            api_key=api_key,
            json_mode=json_mode,
        )
