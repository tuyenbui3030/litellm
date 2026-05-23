import base64
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

import httpx

from litellm.llms.base_llm.chat.transformation import BaseConfig, BaseLLMException
from litellm.types.llms.openai import AllMessageValues
from litellm.types.utils import ModelResponse


class CommandCodeConfigError(BaseLLMException):
    def __init__(
        self, status_code: int, message: str, headers: Union[dict, httpx.Headers]
    ):
        request = httpx.Request(method="POST", url="https://api.commandcode.ai")
        response = httpx.Response(
            status_code=status_code, request=request, headers=headers
        )
        super().__init__(
            status_code=status_code,
            message=message,
            request=request,
            response=response,
        )


class CommandCodeConfig(BaseConfig):
    MODEL_ALIASES = {
        # Anthropic
        "claude-sonnet-4-6": "claude-sonnet-4-6",
        "claude-opus-4-7": "claude-opus-4-7",
        "claude-opus-4-6": "claude-opus-4-6",
        "claude-haiku-4-5": "claude-haiku-4-5",
        # OpenAI
        "gpt-5.5": "gpt-5.5",
        "gpt-5.4": "gpt-5.4",
        "gpt-5.3-codex": "gpt-5.3-codex",
        "gpt-5.4-mini": "gpt-5.4-mini",
        # Google
        "google/gemini-3.5-flash": "google/gemini-3.5-flash",
        "google/gemini-3.1-flash-lite": "google/gemini-3.1-flash-lite",
        # Open source
        "moonshotai/Kimi-K2.6": "moonshotai/Kimi-K2.6",
        "moonshotai/Kimi-K2.5": "moonshotai/Kimi-K2.5",
        "zai-org/GLM-5.1": "zai-org/GLM-5.1",
        "zai-org/GLM-5": "zai-org/GLM-5",
        "MiniMaxAI/MiniMax-M2.7": "MiniMaxAI/MiniMax-M2.7",
        "MiniMaxAI/MiniMax-M2.5": "MiniMaxAI/MiniMax-M2.5",
        "deepseek/deepseek-v4-pro": "deepseek/deepseek-v4-pro",
        "deepseek/deepseek-v4-flash": "deepseek/deepseek-v4-flash",
        "Qwen/Qwen3.6-Max-Preview": "Qwen/Qwen3.6-Max-Preview",
        "Qwen/Qwen3.6-Plus": "Qwen/Qwen3.6-Plus",
        "Qwen/Qwen3.7-Max": "Qwen/Qwen3.7-Max",
        "stepfun/Step-3.5-Flash": "stepfun/Step-3.5-Flash",
        # Short aliases
        "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
        "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    }

    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        return {
            "max_tokens": 200000,
            "temperature": 0.7,
        }

    @classmethod
    def get_supported_openai_params(cls, model: str) -> List[str]:
        return [
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

    @classmethod
    def map_openai_params(
        cls,
        non_default_params: dict,
        optional_params: dict,
        model: str,
        drop_params: bool = False,
    ) -> dict:
        supported_params = cls.get_supported_openai_params(model)

        for param, value in non_default_params.items():
            if param in ("max_tokens", "max_completion_tokens") and "max_tokens" in supported_params:
                optional_params["max_tokens"] = min(value, 200_000)
            elif param in supported_params:
                optional_params[param] = value
            elif not drop_params:
                optional_params[param] = value

        return optional_params

    def validate_environment(
        self,
        headers: dict,
        model: str,
        messages: List[AllMessageValues],
        optional_params: dict,
        litellm_params: dict,
        api_key: Union[str, None] = None,
        api_base: Union[str, None] = None,
    ) -> dict:
        if not api_key:
            raise ValueError("Missing CommandCode API key")
        return {
            **headers,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def transform_request(
        self,
        model: str,
        messages: List[AllMessageValues],
        optional_params: dict,
        api_base: str,
    ) -> Dict[str, Any]:
        transformed_messages = self._transform_messages(messages)
        system_prompt = self._get_system_prompt(messages)
        tools = self._transform_tools(optional_params.get("tools", []))
        api_model = self.MODEL_ALIASES.get(
            self._strip_provider_prefix(model), self._strip_provider_prefix(model)
        )

        params: Dict[str, Any] = {
            "model": api_model,
            "messages": transformed_messages,
            "tools": tools,
            "system": system_prompt,
            "max_tokens": optional_params.get("max_tokens", 8192),
            "stream": True,
        }

        for param in ("temperature", "top_p", "stop"):
            if param in optional_params:
                params[param] = optional_params[param]

        tool_choice = self._transform_tool_choice(optional_params.get("tool_choice"))
        if tool_choice:
            params["toolChoice"] = tool_choice

        return {
            "config": {
                "workingDir": "",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "environment": "LiteLLM",
                "structure": [],
                "isGitRepo": False,
                "currentBranch": "",
                "mainBranch": "",
                "gitStatus": "",
                "recentCommits": [],
            },
            "memory": "",
            "taste": "",
            "skills": None,
            "permissionMode": "standard",
            "params": params,
        }

    @staticmethod
    def _strip_provider_prefix(model: str) -> str:
        return model.removeprefix("commandcode/")

    @staticmethod
    def _get_system_prompt(messages: List[AllMessageValues]) -> str:
        if not messages or messages[0].get("role") != "system":
            return ""

        content = messages[0].get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        return ""

    @staticmethod
    def _transform_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        transformed_tools = []
        for tool in tools:
            if tool.get("type") != "function":
                continue
            function = tool.get("function", {})
            transformed_tools.append(
                {
                    "type": "function",
                    "name": function.get("name", ""),
                    "description": function.get("description", ""),
                    "input_schema": function.get("parameters", {}),
                }
            )
        return transformed_tools

    @staticmethod
    def _transform_tool_choice(tool_choice: Any) -> Union[Dict[str, str], None]:
        if tool_choice is None:
            return None
        if isinstance(tool_choice, str):
            return {"type": tool_choice}
        if not isinstance(tool_choice, dict):
            return None

        choice_type = tool_choice.get("type")
        if choice_type == "function":
            function = tool_choice.get("function", {})
            return {"type": "tool", "toolName": function.get("name", "")}
        if choice_type == "tool":
            return {"type": "tool", "toolName": tool_choice.get("name", "")}
        if choice_type in {"auto", "none", "required"}:
            return {"type": choice_type}
        return None

    def _transform_messages(
        self, messages: List[AllMessageValues]
    ) -> List[Dict[str, Any]]:
        transformed = []

        for message in messages:
            role = message.get("role", "")
            content = message.get("content", "")

            if role == "system":
                continue
            if role == "user":
                transformed.append(
                    {"role": "user", "content": self._transform_user_content(content)}
                )
            elif role == "assistant":
                assistant_content = self._transform_assistant_content(message)
                if assistant_content:
                    transformed.append(
                        {"role": "assistant", "content": assistant_content}
                    )
            elif role == "tool":
                transformed.append(self._transform_tool_message(message, content))

        return transformed

    @staticmethod
    def _transform_user_content(content: Any) -> List[Dict[str, Any]]:
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        if isinstance(content, list):
            parts = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "text":
                    parts.append({"type": "text", "text": item.get("text", "")})
                elif item_type == "image_url":
                    image_url = (item.get("image_url") or {}).get("url", "")
                    if image_url.startswith("data:"):
                        match = re.match(r"data:([^;]+);base64,(.*)", image_url)
                        if match:
                            media_type, data = match.groups()
                            parts.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": data,
                                },
                            })
                        else:
                            parts.append({
                                "type": "image",
                                "source": {"type": "url", "url": image_url},
                            })
                    else:
                        parts.append({
                            "type": "image",
                            "source": {"type": "url", "url": image_url},
                        })
            return parts or [{"type": "text", "text": str(content)}]
        return [{"type": "text", "text": str(content)}]

    @staticmethod
    def _transform_assistant_content(message: AllMessageValues) -> List[Dict[str, Any]]:
        content = message.get("content", "")
        parts: List[Dict[str, Any]] = []

        if isinstance(content, str) and content:
            parts.append({"type": "text", "text": content})
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    parts.append({"type": "text", "text": item.get("text", "")})
                elif item.get("type") == "thinking":
                    parts.append(
                        {"type": "reasoning", "text": item.get("thinking", "")}
                    )
                elif item.get("type") == "tool_call":
                    parts.append(
                        {
                            "type": "tool-call",
                            "toolCallId": item.get("id", ""),
                            "toolName": item.get("name", ""),
                            "input": item.get("arguments", {}),
                        }
                    )

        for tool_call in message.get("tool_calls", []):
            if tool_call.get("type") != "function":
                continue
            function = tool_call.get("function", {})
            arguments = function.get("arguments", "{}")
            parts.append(
                {
                    "type": "tool-call",
                    "toolCallId": tool_call.get("id", ""),
                    "toolName": function.get("name", ""),
                    "input": (
                        json.loads(arguments)
                        if isinstance(arguments, str)
                        else arguments
                    ),
                }
            )

        return parts

    @staticmethod
    def _transform_tool_message(
        message: AllMessageValues, content: Any
    ) -> Dict[str, Any]:
        return {
            "role": "tool",
            "content": [
                {
                    "type": "tool-result",
                    "toolCallId": message.get("tool_call_id", ""),
                    "toolName": message.get("tool_name", ""),
                    "output": {
                        "type": "text" if not message.get("is_error") else "error-text",
                        "value": content if isinstance(content, str) else str(content),
                    },
                }
            ],
        }

    def transform_response(
        self,
        model: str,
        raw_response: httpx.Response,
        model_response: ModelResponse,
        logging_obj: Any,
        request_data: Dict,
        messages: List[AllMessageValues],
        optional_params: Dict,
        litellm_params: dict,
        encoding: Any,
        api_key: Optional[str] = None,
        json_mode: Optional[bool] = None,
    ) -> ModelResponse:
        ## LOGGING
        logging_obj.post_call(
            input=messages,
            api_key=api_key,
            original_response=raw_response.text,
            additional_args={"complete_input_dict": request_data},
        )

        try:
            response_data = raw_response.json()
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Expected JSON response for non-streaming request"
            ) from exc

        usage_data = response_data.get("totalUsage", {})
        input_tokens = usage_data.get("inputTokens", 0)
        output_tokens = usage_data.get("outputTokens", 0)
        details = usage_data.get("inputTokenDetails", {})

        model_response.id = response_data.get("id")
        model_response.created = int(datetime.now().timestamp())
        model_response.model = model

        message: Dict[str, Any] = {
            "role": "assistant",
            "content": response_data.get("text", ""),
        }
        tool_calls = response_data.get("toolCalls")
        if tool_calls:
            message["tool_calls"] = [
                {
                    "id": tc.get("toolCallId") or tc.get("id"),
                    "type": "function",
                    "function": {
                        "name": tc.get("toolName", ""),
                        "arguments": json.dumps(
                            tc.get("input", {}), ensure_ascii=False
                        )
                        if isinstance(tc.get("input"), (dict, list))
                        else str(tc.get("input", "")),
                    },
                }
                for tc in tool_calls
            ]

        model_response.choices = [
            {
                "index": 0,
                "message": message,
                "finish_reason": self._map_finish_reason(
                    response_data.get("finishReason", "stop")
                ),
            }
        ]
        model_response.usage = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens
            + output_tokens
            + details.get("cacheReadTokens", 0)
            + details.get("cacheWriteTokens", 0),
        }

        return model_response

    def get_error_class(
        self, error_message: str, status_code: int, headers: Union[dict, httpx.Headers]
    ) -> BaseLLMException:
        return CommandCodeConfigError(
            status_code=status_code,
            message=error_message,
            headers=headers,
        )

    @staticmethod
    def _map_finish_reason(
        reason: Union[str, None],
    ) -> Literal["stop", "length", "tool_calls"]:
        if reason == "tool-calls":
            return "tool_calls"
        if reason in {"length", "max_tokens", "max-tokens", "max_output_tokens"}:
            return "length"
        return "stop"


