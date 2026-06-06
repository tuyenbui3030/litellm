# Gemini CLI Review and Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Review and polish the Gemini CLI integration and formalize the new test suites into the main repository.

**Architecture:** This plan focuses on backend logic in the proxy management endpoints and standardizing experimental tests into the main `pytest` suite.

**Tech Stack:** Python, FastAPI, Pytest, LiteLLM Core.

---

### Task 1: Integrate and Refactor Response Transformation Tests

**Files:**
- Create: `tests/test_litellm/llms/vertex_ai/gemini/test_gemini_transformation_integration.py`
- Delete: `tests/verify_transformation_full.py`

- [ ] **Step 1: Create the new test file with formalized pytest structure**

```python
import pytest
from litellm.llms.gemini_cli.chat.transformation import GeminiCLIConfig

def test_gemini_cli_metadata_injection():
    """
    Verify that GeminiCLIConfig correctly injects model_id and organization into metadata.
    """
    config = GeminiCLIConfig()
    litellm_params = {
        "model_info": {"id": "test-model-123", "organization": "test-org"},
        "organization": "override-org"
    }
    
    # Run the method that injects metadata (usually get_error_class or similar config methods)
    # Based on our diff, it was in a header/config method.
    config.validate_environment(api_key="test", model="gemini-1.5-pro", messages=[], optional_params={}, litellm_params=litellm_params)
    
    assert litellm_params["metadata"]["model_info"]["id"] == "test-model-123"
    assert litellm_params["metadata"]["organization"] == "override-org"
```

- [ ] **Step 2: Run the test to verify**
Run: `pytest tests/test_litellm/llms/vertex_ai/gemini/test_gemini_transformation_integration.py -v`

- [ ] **Step 3: Remove the old untracked file**
Run: `rm tests/verify_transformation_full.py`

- [ ] **Step 4: Commit**
Run: `git add . && git commit -m "test: integrate gemini transformation tests"`

---

### Task 2: Integrate Tool Use Tests

**Files:**
- Create: `tests/test_litellm/llms/vertex_ai/gemini/test_gemini_tool_use_integration.py`
- Delete: `tests/verify_gemini_tool_use.py`
- Delete: `tests/live_gemini_tool_test.py`

- [ ] **Step 1: Create the tool use test file**

```python
import pytest
from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import VertexGeminiConfig

def test_vertex_ai_search_tool_choice_mapping():
    """
    Verify that search tools correctly map to None to avoid Gemini API errors.
    """
    v = VertexGeminiConfig()
    for search_tool in ["web_search", "web_search_preview"]:
        tc = v.map_tool_choice_values(
            model="gemini-1.5-pro",
            tool_choice={"type": "function", "function": {"name": search_tool}},
        )
        assert tc is None
```

- [ ] **Step 2: Run the test**
Run: `pytest tests/test_litellm/llms/vertex_ai/gemini/test_gemini_tool_use_integration.py -v`

- [ ] **Step 3: Cleanup old files**
Run: `rm tests/verify_gemini_tool_use.py tests/live_gemini_tool_test.py`

- [ ] **Step 4: Commit**
Run: `git commit -am "test: integrate gemini tool use tests"`

---

### Task 3: Backend Code Review & Security Polish

**Files:**
- Modify: `litellm/proxy/management_endpoints/gemini_cli_login.py`

- [ ] **Step 1: Add input validation for model_id in endpoints**
Ensure `model_id` is a valid string before processing.

- [ ] **Step 2: Verify exception handling in _fetch_quota_for_model**
Ensure no raw exceptions leak to the user.

- [ ] **Step 3: Commit polish changes**
Run: `git commit -am "refactor: polish gemini cli backend endpoints"`

---

### Task 4: Final Cleanup

- [ ] **Step 1: Remove remaining dev scripts**
Run: `rm test_db.py test_logs.py test_logs2.py test_quota.py plan-quota-check.md`

- [ ] **Step 2: Run all related tests to ensure 100% success**
Run: `pytest tests/test_litellm/llms/vertex_ai/gemini/ -v`

- [ ] **Step 3: Final commit**
Run: `git commit -am "chore: final cleanup of gemini cli dev artifacts"`
