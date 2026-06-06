"""
Integration tests for Gemini CLI transformation logic.

Tests the injection of metadata and handling of responses for the Gemini CLI provider.
"""

from unittest.mock import patch

import httpx
import pytest

from litellm.llms.gemini_cli.chat.transformation import GeminiCLIConfig, _unwrap_gemini_cli_response_json


def test_gemini_cli_validate_environment_metadata_injection():
    """
    Test that validate_environment correctly injects model_info and organization
    into litellm_params["metadata"] for logging purposes.
    """
    config = GeminiCLIConfig()
    litellm_params = {
        "model_info": {"id": "test-model-123", "organization": "test-org"},
        "organization": "override-org",
    }

    # Mock the authenticator to avoid real network/env calls
    with patch.object(
        config.authenticator, "get_credentials", return_value=("fake-token", "fake-project")
    ) as mock_auth:
        config.validate_environment(
            headers={},
            model="gemini-1.5-pro",
            messages=[],
            optional_params={},
            litellm_params=litellm_params,
            api_key="test",
        )

    assert litellm_params["metadata"]["model_info"]["id"] == "test-model-123"
    assert litellm_params["metadata"]["organization"] == "override-org"
    assert litellm_params["gemini_cli_project_id"] == "fake-project"


def test_gemini_cli_transform_response_unwraps_envelope():
    """
    Test that transform_response correctly unwraps the gemini_cli response envelope.
    """
    config = GeminiCLIConfig()
    wrapped_content = {
        "response": {
            "candidates": [{"content": {"parts": [{"text": "hello"}]}}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 1},
        },
        "traceId": "trace-123",
    }

    # Create response without triggering automatic decompression error in httpx
    mock_response = httpx.Response(
        status_code=200,
        headers={"Content-Type": "application/json", "X-Content-Encoding": "mock-gzip"},
        json=wrapped_content,
    )
    # Give it a dummy request because transformation code accesses it
    mock_response.request = httpx.Request("POST", "https://example.com")

    # We patch the base class method that transform_response eventually calls
    with patch(
        "litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini.VertexGeminiConfig.transform_response"
    ) as mock_super_transform:
        config.transform_response(
            model="gemini-1.5-pro",
            raw_response=mock_response,
            model_response=None,
            logging_obj=None,
            request_data={},
            messages=[],
            optional_params={},
            litellm_params={},
            encoding=None,
        )

        # Verify that the response passed to super().transform_response is unwrapped
        assert mock_super_transform.called
        passed_response = mock_super_transform.call_args[1]["raw_response"]

        # Check that it is actually unwrapped
        assert passed_response.json() == wrapped_content["response"]
        assert "traceId" not in passed_response.json()


def test_unwrap_logic_directly():
    """
    Verify the unwrapping logic itself.
    """
    wrapped = {
        "response": {"data": "inner"},
        "traceId": "123"
    }
    unwrapped = _unwrap_gemini_cli_response_json(wrapped)
    assert unwrapped == {"data": "inner"}

    # Should not unwrap if candidates already present (not wrapped)
    not_wrapped = {"candidates": [], "usageMetadata": {}}
    assert _unwrap_gemini_cli_response_json(not_wrapped) == not_wrapped
