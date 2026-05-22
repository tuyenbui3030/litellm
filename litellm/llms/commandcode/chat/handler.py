import json
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple, Union

import httpx

import litellm
from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler, HTTPHandler
from litellm.types.llms.openai import (
    AllMessageValues,
    ChatCompletionToolCallChunk,
    ChatCompletionUsageBlock,
)
from litellm.types.utils import GenericStreamingChunk, ModelResponse, _generate_id

from ...base import BaseLLM
from .transformation import CommandCodeConfig

if TYPE_CHECKING:
    from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper


class CommandCodeError(Exception):
    def __init__(self, status_code: int, message: str, headers: Optional[dict] = None):
        self.status_code = status_code
        self.message = message
        self.headers = headers
        super().__init__(self.message)


class CommandCodeChatCompletion(BaseLLM):
    def __init__(self) -> None:
        super().__init__()
        self.config = CommandCodeConfig()

    def _get_api_base_and_key(
        self, api_base: Optional[str], api_key: Optional[str]
    ) -> Tuple[str, str]:
        base = api_base or "https://api.commandcode.ai"
        key = api_key or litellm.get_secret_str("COMMANDCODE_API_KEY")
        if not key:
            raise CommandCodeError(
                status_code=401,
                message="COMMANDCODE_API_KEY not found in environment or params",
            )
        return base, key

    def completion(
        self,
        model: str,
        messages: List[AllMessageValues],
        custom_llm_provider: str,
        api_base: Optional[str],
        api_key: Optional[str],
        api_version: Optional[str] = None,
        model_response: ModelResponse = None,
        print_verbose=None,
        encoding=None,
        logging_obj=None,
        optional_params: Optional[dict] = None,
        litellm_params: Optional[dict] = None,
        timeout: Union[float, httpx.Timeout] = 60.0,
        client: Optional[Union[HTTPHandler, AsyncHTTPHandler]] = None,
        acompletion: bool = False,
    ) -> Union[ModelResponse, "CustomStreamWrapper"]:
        optional_params = optional_params or {}
        litellm_params = litellm_params or {}
        if acompletion:
            return self.acompletion(
                model=model,
                messages=messages,
                api_base=api_base,
                api_key=api_key,
                model_response=model_response,
                print_verbose=print_verbose,
                encoding=encoding,
                logging_obj=logging_obj,
                optional_params=optional_params,
                litellm_params=litellm_params,
                timeout=timeout,
                client=client,
            )
        return self._completion(
            model=model,
            messages=messages,
            api_base=api_base,
            api_key=api_key,
            model_response=model_response,
            print_verbose=print_verbose,
            encoding=encoding,
            logging_obj=logging_obj,
            optional_params=optional_params,
            litellm_params=litellm_params,
            timeout=timeout,
            client=client,
        )

    def _completion(
        self,
        model: str,
        messages: List[AllMessageValues],
        api_base: Optional[str],
        api_key: Optional[str],
        model_response: ModelResponse,
        print_verbose,
        encoding,
        logging_obj,
        optional_params: dict,
        litellm_params: dict,
        timeout: Union[float, httpx.Timeout],
        client: Optional[HTTPHandler] = None,
    ) -> Union[ModelResponse, "CustomStreamWrapper"]:
        api_base, api_key = self._get_api_base_and_key(api_base, api_key)
        stream = optional_params.get("stream", False)
        data = self.config.transform_request(
            model=model,
            messages=messages,
            optional_params=optional_params,
            api_base=api_base,
        )
        headers = self._headers(api_key)

        logging_obj.pre_call(
            input=messages,
            api_key=api_key,
            additional_args={
                "complete_input_dict": data,
                "api_base": api_base,
                "headers": headers,
            },
        )

        http_client = client or HTTPHandler()
        response = http_client.post(
            f"{api_base}/alpha/generate",
            headers=headers,
            data=json.dumps(data),
            stream=True,
            timeout=timeout,
        )

        if response.status_code != 200:
            raise self.config.get_error_class(
                error_message=response.text,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

        stream_processor = CommandCodeStreamProcessor(response.iter_lines())
        if stream:
            return litellm.CustomStreamWrapper(
                completion_stream=stream_processor,
                model=model,
                custom_llm_provider="commandcode",
                logging_obj=logging_obj,
            )

        content, finish_reason, usage, tool_calls = stream_processor.collect()
        return self._model_response(
            model=model,
            content=content,
            finish_reason=finish_reason,
            usage=usage,
            tool_calls=tool_calls,
        )

    async def acompletion(
        self,
        model: str,
        messages: List[AllMessageValues],
        api_base: Optional[str],
        api_key: Optional[str],
        model_response: ModelResponse,
        print_verbose,
        encoding,
        logging_obj,
        optional_params: dict,
        litellm_params: dict,
        timeout: Union[float, httpx.Timeout],
        client: Optional[AsyncHTTPHandler] = None,
    ) -> Union[ModelResponse, "CustomStreamWrapper"]:
        api_base, api_key = self._get_api_base_and_key(api_base, api_key)
        stream = optional_params.get("stream", False)
        data = self.config.transform_request(
            model=model,
            messages=messages,
            optional_params=optional_params,
            api_base=api_base,
        )
        headers = self._headers(api_key)

        logging_obj.pre_call(
            input=messages,
            api_key=api_key,
            additional_args={
                "complete_input_dict": data,
                "api_base": api_base,
                "headers": headers,
            },
        )

        http_client = client or AsyncHTTPHandler()
        response = await http_client.post(
            f"{api_base}/alpha/generate",
            headers=headers,
            data=json.dumps(data),
            stream=True,
            timeout=timeout,
        )

        if response.status_code != 200:
            error_body = (await response.aread()).decode("utf-8", errors="replace")
            raise self.config.get_error_class(
                error_message=error_body,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

        content, finish_reason, usage, tool_calls = await CommandCodeAsyncCollector(
            response.aiter_lines()
        ).collect()
        if not stream:
            return self._model_response(
                model=model,
                content=content,
                finish_reason=finish_reason,
                usage=usage,
                tool_calls=tool_calls,
            )

        async def single_chunk_generator():
            if content:
                yield GenericStreamingChunk(
                    text=content,
                    tool_use=None,
                    is_finished=False,
                    finish_reason=None,
                    usage=None,
                    index=0,
                )
            for tool_call in tool_calls:
                yield GenericStreamingChunk(
                    text="",
                    tool_use=tool_call,
                    is_finished=False,
                    finish_reason=None,
                    usage=None,
                    index=tool_call.get("index", 0),
                )
            yield GenericStreamingChunk(
                text="",
                tool_use=None,
                is_finished=True,
                finish_reason=finish_reason,
                usage=usage,
                index=0,
            )

        return litellm.CustomStreamWrapper(
            completion_stream=single_chunk_generator(),
            model=model,
            custom_llm_provider="commandcode",
            logging_obj=logging_obj,
        )

    @staticmethod
    def _headers(api_key: str) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "x-command-code-version": "0.24.1",
            "x-cli-environment": "production",
            "x-project-slug": "litellm-cc",
            "x-taste-learning": "false",
            "x-co-flag": "false",
            "x-session-id": str(uuid.uuid4()),
        }

    @staticmethod
    def _model_response(
        model: str,
        content: str,
        finish_reason: str,
        usage: Optional[ChatCompletionUsageBlock],
        tool_calls: Optional[List[ChatCompletionToolCallChunk]] = None,
    ) -> ModelResponse:
        message: Dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            message["tool_calls"] = tool_calls

        return ModelResponse(
            id=_generate_id(),
            created=int(time.time()),
            model=model,
            choices=[
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason,
                }
            ],
            usage=usage,
        )


class CommandCodeStreamProcessor:
    def __init__(self, response_iterator: Iterator[str]):
        self.response_iterator = response_iterator
        self.finished = False
        self.usage: Optional[ChatCompletionUsageBlock] = None
        self.tool_calls: List[ChatCompletionToolCallChunk] = []

    def __iter__(self):
        return self

    def __next__(self) -> GenericStreamingChunk:
        if self.finished:
            raise StopIteration

        for line in self.response_iterator:
            chunk = self._process_line(line)
            if chunk:
                return chunk

        self.finished = True
        return self._final_chunk("stop")

    def collect(
        self,
    ) -> Tuple[
        str,
        str,
        Optional[ChatCompletionUsageBlock],
        List[ChatCompletionToolCallChunk],
    ]:
        content_chunks = []
        finish_reason = "stop"
        for chunk in self:
            text = chunk.get("text")
            if text:
                content_chunks.append(text)
            tool_use = chunk.get("tool_use")
            if tool_use:
                self.tool_calls.append(tool_use)
            if chunk.get("is_finished"):
                finish_reason = chunk.get("finish_reason") or "stop"
                return (
                    "".join(content_chunks),
                    finish_reason,
                    chunk.get("usage"),
                    self.tool_calls,
                )
        return "".join(content_chunks), finish_reason, self.usage, self.tool_calls

    def _process_line(self, line: str) -> Optional[GenericStreamingChunk]:
        event = _parse_stream_event(line)
        if event is None:
            return None

        event_type = event.get("type")
        if event_type == "text-delta":
            return GenericStreamingChunk(
                text=event.get("text", ""),
                tool_use=None,
                is_finished=False,
                finish_reason=None,
                usage=None,
                index=0,
            )
        if event_type == "tool-call":
            return GenericStreamingChunk(
                text="",
                tool_use=_tool_call_from_event(event),
                is_finished=False,
                finish_reason=None,
                usage=None,
                index=0,
            )
        if event_type == "finish":
            self.usage = _usage_from_event(event)
            return self._final_chunk(
                CommandCodeConfig._map_finish_reason(event.get("finishReason", "stop"))
            )
        if event_type == "error":
            error_msg = event.get("error", {}).get("message", "Unknown error")
            raise CommandCodeError(status_code=500, message=error_msg)
        return None

    def _final_chunk(self, finish_reason: str) -> GenericStreamingChunk:
        self.finished = True
        return GenericStreamingChunk(
            text="",
            tool_use=None,
            is_finished=True,
            finish_reason=finish_reason,
            usage=self.usage,
            index=0,
        )


class CommandCodeAsyncCollector:
    def __init__(self, response_iterator: Any):
        self.response_iterator = response_iterator

    async def collect(
        self,
    ) -> Tuple[
        str,
        str,
        Optional[ChatCompletionUsageBlock],
        List[ChatCompletionToolCallChunk],
    ]:
        content_chunks = []
        finish_reason = "stop"
        usage = None
        tool_calls: List[ChatCompletionToolCallChunk] = []

        async for line in self.response_iterator:
            event = _parse_stream_event(line)
            if event is None:
                continue
            event_type = event.get("type")
            if event_type == "text-delta":
                content_chunks.append(event.get("text", ""))
            elif event_type == "tool-call":
                tool_calls.append(_tool_call_from_event(event))
            elif event_type == "finish":
                finish_reason = CommandCodeConfig._map_finish_reason(
                    event.get("finishReason", "stop")
                )
                usage = _usage_from_event(event)
            elif event_type == "error":
                error_msg = event.get("error", {}).get("message", "Unknown error")
                raise CommandCodeError(status_code=500, message=error_msg)

        return "".join(content_chunks), finish_reason, usage, tool_calls


def _tool_call_from_event(event: Dict[str, Any]) -> ChatCompletionToolCallChunk:
    input_value = event.get("input", {})
    arguments = (
        json.dumps(input_value, ensure_ascii=False)
        if isinstance(input_value, (dict, list))
        else str(input_value)
    )
    return ChatCompletionToolCallChunk(
        id=event.get("toolCallId") or event.get("id"),
        type="function",
        function={
            "name": event.get("toolName", ""),
            "arguments": arguments,
        },
        index=0,
    )


def _parse_stream_event(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line or line.startswith(":") or line.startswith("event:"):
        return None
    if line.startswith("data:"):
        line = line[5:].strip()
    if not line or line == "[DONE]":
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _usage_from_event(event: Dict[str, Any]) -> ChatCompletionUsageBlock:
    total_usage = event.get("totalUsage", {})
    details = total_usage.get("inputTokenDetails", {})
    input_tokens = total_usage.get("inputTokens", 0)
    output_tokens = total_usage.get("outputTokens", 0)
    return ChatCompletionUsageBlock(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        total_tokens=input_tokens
        + output_tokens
        + details.get("cacheReadTokens", 0)
        + details.get("cacheWriteTokens", 0),
    )
