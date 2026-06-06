import pytest
from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import (
    VertexGeminiConfig,
)


@pytest.mark.parametrize(
    "search_tool",
    ["web_search", "web_search_preview"],
)
def test_vertex_ai_search_tool_choice_mapping(search_tool):
    """
    Test that Google Search tools are correctly mapped when tool_choice is provided.
    For Gemini, when tool_choice is a specific search tool, it should return None
    to indicate it's handled separately or should not be included in standard function calling config.
    """
    v = VertexGeminiConfig()
    tc = v.map_tool_choice_values(
        model="gemini-1.5-pro",
        tool_choice={"type": "function", "function": {"name": search_tool}},
    )
    assert tc is None
