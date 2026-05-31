import os
from typing import Any, List, Optional, Tuple

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
            access_token, project_id = self.authenticator.get_credentials(litellm_params)
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
            "Accept": "text/event-stream" if optional_params.get("stream") else "application/json",
        }
        
        return {**validated_headers, **default_headers}

    # In LiteLLM, VertexGeminiConfig doesn't have a simple transform_request that we can easily override to wrap the whole payload.
    # The wrapping of the payload: { project, model, request: { original_body } }
    # might need to be done in the main.py handler or by overriding _get_openai_compatible_provider_info.
    # Wait, let's just create this config and we'll handle the request wrapping in the provider's `completion` function or in a `transform_request` if available.
