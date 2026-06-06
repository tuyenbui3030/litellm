---
name: gemini-cli-review-and-integration
description: Review and integrate Gemini CLI health/quota dashboard changes and core utility fixes.
metadata:
  type: design-spec
---

# Design Spec: Gemini CLI Review and Integration

## Background

The project has introduced a comprehensive health and quota monitoring dashboard for Gemini CLI models. This includes new backend endpoints in the proxy, response transformation logic, and improved health check mechanisms. Additionally, several test scripts were created during development but remain untracked.

## Requirements

### 1. Code Review & Polish
- Review `litellm/proxy/management_endpoints/gemini_cli_login.py` for:
    - Security of parameter decryption.
    - Robustness of the `_test_single_gemini_cli_model_by_params` and `_fetch_quota_for_model` functions.
    - Error handling and timeout management (ensuring no hangs).
- Review `litellm/llms/gemini_cli/chat/transformation.py` and `litellm/llms/vertex_ai/gemini/vertex_and_google_ai_studio_gemini.py` for correct metadata injection and tool mapping.
- Review `litellm/litellm_core_utils/streaming_handler.py` and `health_check_helpers.py` for regression risks.

### 2. Test Integration
- Move and refactor the following untracked test files into the formal test suite (`tests/test_litellm/llms/vertex_ai/gemini/`):
    - `tests/live_gemini_tool_test.py`
    - `tests/verify_gemini_tool_use.py`
    - `tests/verify_transformation_full.py`
- Ensure tests use standard `pytest` patterns and do not rely on hardcoded sensitive data.

### 3. Cleanup
- Remove temporary and redundant untracked files:
    - `test_db.py`
    - `test_logs.py`
    - `test_logs2.py`
    - `test_quota.py`
    - `plan-quota-check.md` (content already integrated/documented)

## Architecture

- **Management Endpoints**: `gemini_cli_login.py` serves as the primary hub for administrative Gemini CLI tasks.
- **Provider Config**: `GeminiCLIConfig` and `VertexGeminiConfig` handle the provider-specific nuances of the Google APIs.
- **Observability**: Metadata injection is standardized across the Gemini CLI flow to ensure consistent logging.

## Success Criteria

1. All new and refactored tests pass.
2. The `/gemini_cli/test_all` dashboard functions correctly with both status and quota checks.
3. No sensitive credentials are leaked or hardcoded.
4. The repository is cleaned of all temporary development artifacts.
