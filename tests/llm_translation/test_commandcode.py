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
        "messages": [{"role": "user", "content": [{"type": "text", "text": "Hello"}]}],
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


def test_commandcode_provider_config_is_registered():
    provider_config = litellm.ProviderConfigManager.get_provider_chat_config(
        model="commandcode/deepseek-v4-flash",
        provider=LlmProviders.COMMANDCODE,
    )

    assert isinstance(provider_config, CommandCodeConfig)
