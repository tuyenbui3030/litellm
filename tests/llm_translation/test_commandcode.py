import litellm

from litellm.llms.commandcode.chat.handler import CommandCodeStreamProcessor
from litellm.llms.commandcode.chat.transformation import CommandCodeConfig
from litellm.types.utils import LlmProviders


def test_commandcode_transform_request_maps_model_and_messages():
    request = CommandCodeConfig().transform_request(
        model="commandcode/deepseek-v4-flash",
        messages=[
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Hello"},
        ],
        optional_params={"max_tokens": 100, "temperature": 0.2},
        api_base="https://api.commandcode.ai",
    )

    assert request["config"]["workingDir"] == ""
    assert request["config"]["environment"] == "LiteLLM"
    assert request["params"] == {
        "model": "deepseek/deepseek-v4-flash",
        "messages": [{"role": "user", "content": "Hello"}],
        "tools": [],
        "system": "You are concise.",
        "max_tokens": 100,
        "stream": True,
        "temperature": 0.2,
    }


def test_commandcode_transform_request_maps_tool_choice():
    request = CommandCodeConfig().transform_request(
        model="commandcode/deepseek-v4-flash",
        messages=[{"role": "user", "content": "Hello"}],
        optional_params={
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Lookup a value",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "lookup"}},
        },
        api_base="https://api.commandcode.ai",
    )

    assert request["params"]["toolChoice"] == {
        "type": "tool",
        "toolName": "lookup",
    }


def test_commandcode_transform_request_maps_tools():
    request = CommandCodeConfig().transform_request(
        model="commandcode/deepseek-v4-flash",
        messages=[{"role": "user", "content": "Hello"}],
        optional_params={
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Lookup a value",
                        "parameters": {"type": "object"},
                    },
                }
            ]
        },
        api_base="https://api.commandcode.ai",
    )

    assert request["params"]["tools"] == [
        {
            "type": "function",
            "name": "lookup",
            "description": "Lookup a value",
            "input_schema": {"type": "object"},
        }
    ]


def test_commandcode_stream_processor_collects_raw_json_lines():
    processor = CommandCodeStreamProcessor(
        iter(
            [
                '{"type":"start"}',
                '{"type":"text-delta","text":"Xin "}',
                '{"type":"text-delta","text":"chao"}',
                '{"type":"finish","finishReason":"stop","totalUsage":{"inputTokens":2,"outputTokens":3,"inputTokenDetails":{"cacheReadTokens":1,"cacheWriteTokens":0}}}',
            ]
        )
    )

    content, finish_reason, usage, tool_calls = processor.collect()

    assert content == "Xin chao"
    assert finish_reason == "stop"
    assert usage == {
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 6,
    }
    assert tool_calls == []


def test_commandcode_stream_processor_collects_tool_calls():
    processor = CommandCodeStreamProcessor(
        iter(
            [
                '{"type":"text-delta","text":"Let me check."}',
                '{"type":"tool-input-start","id":"call_123","toolName":"get_changed_files","dynamic":false}',
                '{"type":"tool-input-delta","id":"call_123","delta":"{}"}',
                '{"type":"tool-input-end","id":"call_123"}',
                '{"type":"tool-call","toolCallId":"call_123","toolName":"get_changed_files","input":{}}',
                '{"type":"finish","finishReason":"tool-calls","totalUsage":{"inputTokens":2,"outputTokens":3}}',
            ]
        )
    )

    content, finish_reason, usage, tool_calls = processor.collect()

    assert content == "Let me check."
    assert finish_reason == "tool_calls"
    assert usage == {
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5,
    }
    assert tool_calls == [
        {
            "id": "call_123",
            "type": "function",
            "function": {"name": "get_changed_files", "arguments": "{}"},
            "index": 0,
        }
    ]


def test_commandcode_stream_processor_emits_tool_call_chunk():
    processor = CommandCodeStreamProcessor(
        iter(
            [
                '{"type":"tool-call","toolCallId":"call_123","toolName":"get_changed_files","input":{}}'
            ]
        )
    )

    chunk = next(processor)

    assert chunk["text"] == ""
    assert chunk["tool_use"] == {
        "id": "call_123",
        "type": "function",
        "function": {"name": "get_changed_files", "arguments": "{}"},
        "index": 0,
    }
    assert chunk["is_finished"] is False


def test_commandcode_transform_response_matches_base_config_signature():
    """transform_response must accept all parameters BaseConfig passes."""
    import inspect

    from litellm.llms.base_llm.chat.transformation import BaseConfig

    sig = inspect.signature(CommandCodeConfig.transform_response)
    params = list(sig.parameters.keys())

    expected_params = [
        "model",
        "raw_response",
        "model_response",
        "logging_obj",
        "request_data",
        "messages",
        "optional_params",
        "litellm_params",
        "encoding",
        "api_key",
        "json_mode",
    ]
    for p in expected_params:
        assert p in params, f"Missing parameter: {p}"


def test_commandcode_maps_developer_role_to_system():
    """CommandCode should map developer role to system role (default BaseConfig behavior)."""
    config = CommandCodeConfig()
    messages = [
        {"role": "developer", "content": "You are a helpful coding assistant."},
        {"role": "user", "content": "Hello"},
    ]

    result = config.translate_developer_role_to_system_role(messages)

    assert result[0]["role"] == "system"
    assert result[0]["content"] == "You are a helpful coding assistant."


def test_commandcode_transform_messages_preserves_assistant_tool_calls():
    """Assistant messages with tool_calls should have tool-call blocks in output."""
    config = CommandCodeConfig()
    messages = [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "What files changed?"},
        {
            "role": "assistant",
            "content": "Let me check.",
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {
                        "name": "get_changed_files",
                        "arguments": "{}",
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_abc",
            "content": "file1.py, file2.py",
        },
    ]

    request = config.transform_request(
        model="commandcode/deepseek-v4-flash",
        messages=messages,
        optional_params={},
        api_base="https://api.commandcode.ai",
    )

    transformed = request["params"]["messages"]
    assert len(transformed) == 3  # user, assistant, tool (system extracted)

    assistant_msg = transformed[1]
    assert assistant_msg["role"] == "assistant"
    assert any(
        block["type"] == "tool-call" and block["toolName"] == "get_changed_files"
        for block in assistant_msg["content"]
    )

    tool_msg = transformed[2]
    assert tool_msg["role"] == "tool"
    assert tool_msg["content"][0]["toolCallId"] == "call_abc"


def test_commandcode_transform_messages_with_image_content():
    """User messages with image_url content should be transformed to image blocks."""
    config = CommandCodeConfig()
    messages = [
        {"role": "system", "content": "You are helpful."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What is in this image?"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/photo.jpg"},
                },
            ],
        },
    ]

    request = config.transform_request(
        model="commandcode/deepseek-v4-flash",
        messages=messages,
        optional_params={},
        api_base="https://api.commandcode.ai",
    )

    user_content = request["params"]["messages"][0]["content"]
    assert isinstance(user_content, list)
    assert len(user_content) == 2
    assert user_content[0] == {"type": "text", "text": "What is in this image?"}
    assert user_content[1]["type"] == "image"
    assert user_content[1]["source"]["type"] == "url"
    assert user_content[1]["source"]["url"] == "https://example.com/photo.jpg"


def test_commandcode_supported_params_are_comprehensive():
    """Supported params should include max_completion_tokens and other common params."""
    params = CommandCodeConfig.get_supported_openai_params("deepseek-v4-flash")

    required_params = [
        "max_tokens",
        "max_completion_tokens",
        "temperature",
        "top_p",
        "stream",
        "stop",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
    ]
    for p in required_params:
        assert p in params, f"Missing supported param: {p}"


def test_commandcode_tool_message_uses_tool_call_id():
    """Tool message should correctly use tool_call_id for matching."""
    message = {
        "role": "tool",
        "tool_call_id": "call_xyz",
        "content": "result data",
    }
    result = CommandCodeConfig._transform_tool_message(message, "result data")

    assert result["role"] == "tool"
    assert result["content"][0]["type"] == "tool-result"
    assert result["content"][0]["toolCallId"] == "call_xyz"
    assert result["content"][0]["output"]["value"] == "result data"


def test_commandcode_provider_config_is_registered():
    provider_config = litellm.ProviderConfigManager.get_provider_chat_config(
        model="commandcode/deepseek-v4-flash",
        provider=LlmProviders.COMMANDCODE,
    )

    assert isinstance(provider_config, CommandCodeConfig)


def test_commandcode_multiturn_conversation_plain_strings():
    """Multi-turn conversations should have plain string content for user messages."""
    config = CommandCodeConfig()
    messages = [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
        {"role": "assistant", "content": "I'm great, thanks!"},
        {"role": "user", "content": "Tell me a joke"},
    ]

    request = config.transform_request(
        model="commandcode/deepseek-v4-flash",
        messages=messages,
        optional_params={},
        api_base="https://api.commandcode.ai",
    )

    transformed = request["params"]["messages"]
    assert len(transformed) == 5  # 3 user + 2 assistant (system extracted)
    # All user messages should be plain strings
    for msg in transformed:
        if msg["role"] == "user":
            assert isinstance(msg["content"], str), (
                f"Expected string content for user message, got {type(msg['content'])}"
            )


def test_commandcode_user_content_base64_image():
    """User messages with base64 image_url should be transformed to image blocks."""
    config = CommandCodeConfig()
    messages = [
        {"role": "user", "content": [
            {"type": "text", "text": "Describe this"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
            },
        ]},
    ]

    request = config.transform_request(
        model="commandcode/deepseek-v4-flash",
        messages=messages,
        optional_params={},
        api_base="https://api.commandcode.ai",
    )

    user_content = request["params"]["messages"][0]["content"]
    assert isinstance(user_content, list)
    assert len(user_content) == 2
    assert user_content[0] == {"type": "text", "text": "Describe this"}
    assert user_content[1]["type"] == "image"
    assert user_content[1]["source"]["type"] == "base64"
    assert user_content[1]["source"]["media_type"] == "image/png"
    assert user_content[1]["source"]["data"] == "iVBORw0KGgo="


def test_commandcode_user_content_text_only_list():
    """User messages with a single text block should return plain string."""
    config = CommandCodeConfig()
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "Hello world"}]},
    ]

    request = config.transform_request(
        model="commandcode/deepseek-v4-flash",
        messages=messages,
        optional_params={},
        api_base="https://api.commandcode.ai",
    )

    user_content = request["params"]["messages"][0]["content"]
    assert user_content == "Hello world"


def test_commandcode_user_content_multiple_text_blocks():
    """User messages with multiple text blocks should be combined into a string."""
    config = CommandCodeConfig()
    messages = [
        {"role": "user", "content": [
            {"type": "text", "text": "Part 1"},
            {"type": "text", "text": "Part 2"},
        ]},
    ]

    request = config.transform_request(
        model="commandcode/deepseek-v4-flash",
        messages=messages,
        optional_params={},
        api_base="https://api.commandcode.ai",
    )

    user_content = request["params"]["messages"][0]["content"]
    assert isinstance(user_content, str)
    assert user_content == "Part 1\nPart 2"
