# SPDX-FileCopyrightText: 2022-present deepset GmbH <info@deepset.ai>
#
# SPDX-License-Identifier: Apache-2.0

import json
from datetime import datetime
from typing import Any, AsyncIterable, Dict, Iterable, List, Optional, Union

from haystack import component, default_from_dict, default_to_dict, logging
from haystack.components.generators.utils import _convert_streaming_chunks_to_chat_message
from haystack.dataclasses import (
    AsyncStreamingCallbackT,
    ChatMessage,
    ComponentInfo,
    StreamingCallbackT,
    StreamingChunk,
    SyncStreamingCallbackT,
    ToolCall,
    select_streaming_callback,
)
from haystack.dataclasses.streaming_chunk import FinishReason
from haystack.lazy_imports import LazyImport
from haystack.tools import (
    Tool,
    Toolset,
    _check_duplicate_tool_names,
    deserialize_tools_or_toolset_inplace,
    serialize_tools_or_toolset,
)
from haystack.utils import Secret, deserialize_callable, deserialize_secrets_inplace, serialize_callable
from haystack.utils.hf import HFGenerationAPIType, HFModelType, check_valid_model, convert_message_to_hf_format
from haystack.utils.url_validation import is_valid_http_url

logger = logging.getLogger(__name__)

with LazyImport(message="Run 'pip install \"huggingface_hub[inference]>=0.27.0\"'") as huggingface_hub_import:
    from huggingface_hub import (
        AsyncInferenceClient,
        ChatCompletionInputFunctionDefinition,
        ChatCompletionInputStreamOptions,
        ChatCompletionInputTool,
        ChatCompletionOutput,
        ChatCompletionOutputToolCall,
        ChatCompletionStreamOutput,
        ChatCompletionStreamOutputChoice,
        InferenceClient,
    )


def _convert_hfapi_tool_calls(hfapi_tool_calls: Optional[List["ChatCompletionOutputToolCall"]]) -> List[ToolCall]:
    """
    Convert HuggingFace API tool calls to a list of Haystack ToolCall.

    :param hfapi_tool_calls: The HuggingFace API tool calls to convert.
    :returns: A list of ToolCall objects.

    """
    if not hfapi_tool_calls:
        return []

    tool_calls = []

    for hfapi_tc in hfapi_tool_calls:
        hf_arguments = hfapi_tc.function.arguments

        arguments = None
        if isinstance(hf_arguments, dict):
            arguments = hf_arguments
        elif isinstance(hf_arguments, str):
            try:
                arguments = json.loads(hf_arguments)
            except json.JSONDecodeError:
                logger.warning(
                    "HuggingFace API returned a malformed JSON string for tool call arguments. This tool call "
                    "will be skipped. Tool call ID: {_id}, Tool name: {_name}, Arguments: {_arguments}",
                    _id=hfapi_tc.id,
                    _name=hfapi_tc.function.name,
                    _arguments=hf_arguments,
                )
        else:
            logger.warning(
                "HuggingFace API returned tool call arguments of type {_type}. Valid types are dict and str. This tool "
                "call will be skipped. Tool call ID: {_id}, Tool name: {_name}, Arguments: {_arguments}",
                _id=hfapi_tc.id,
                _name=hfapi_tc.function.name,
                _arguments=hf_arguments,
            )

        if arguments:
            tool_calls.append(ToolCall(tool_name=hfapi_tc.function.name, arguments=arguments, id=hfapi_tc.id))

    return tool_calls


def _convert_tools_to_hfapi_tools(
    tools: Optional[Union[List[Tool], Toolset]],
) -> Optional[List["ChatCompletionInputTool"]]:
    if not tools:
        return None

    # huggingface_hub<0.31.0 uses "arguments", huggingface_hub>=0.31.0 uses "parameters"
    parameters_name = "arguments" if hasattr(ChatCompletionInputFunctionDefinition, "arguments") else "parameters"

    hf_tools = []
    for tool in tools:
        hf_tools_args = {"name": tool.name, "description": tool.description, parameters_name: tool.parameters}

        hf_tools.append(
            ChatCompletionInputTool(function=ChatCompletionInputFunctionDefinition(**hf_tools_args), type="function")
        )

    return hf_tools


def _map_hf_finish_reason_to_haystack(choice: "ChatCompletionStreamOutputChoice") -> Optional[FinishReason]:
    """
    Map HuggingFace finish reasons to Haystack FinishReason literals.

    Uses the full choice object to detect tool calls and provide accurate mapping.

    HuggingFace finish reasons (can be found here https://huggingface.github.io/text-generation-inference/ under
    FinishReason):
    - "length": number of generated tokens == `max_new_tokens`
    - "eos_token": the model generated its end of sequence token
    - "stop_sequence": the model generated a text included in `stop_sequences`

    Additionally detects tool calls from delta.tool_calls or delta.tool_call_id.

    :param choice: The HuggingFace ChatCompletionStreamOutputChoice object.
    :returns: The corresponding Haystack FinishReason or None.
    """
    if choice.finish_reason is None:
        return None

    # Check if this choice contains tool call information
    has_tool_calls = choice.delta.tool_calls is not None or choice.delta.tool_call_id is not None

    # If we detect tool calls, override the finish reason
    if has_tool_calls:
        return "tool_calls"

    # Map HuggingFace finish reasons to Haystack standard ones
    mapping: Dict[str, FinishReason] = {
        "length": "length",  # Direct match
        "eos_token": "stop",  # EOS token means natural stop
        "stop_sequence": "stop",  # Stop sequence means natural stop
    }

    return mapping.get(choice.finish_reason, "stop")  # Default to "stop" for unknown reasons


def _convert_chat_completion_stream_output_to_streaming_chunk(
    chunk: "ChatCompletionStreamOutput",
    previous_chunks: List[StreamingChunk],
    component_info: Optional[ComponentInfo] = None,
) -> StreamingChunk:
    """
    Converts the Hugging Face API ChatCompletionStreamOutput to a StreamingChunk.
    """
    # Choices is empty if include_usage is set to True where the usage information is returned.
    if len(chunk.choices) == 0:
        usage = None
        if chunk.usage:
            usage = {"prompt_tokens": chunk.usage.prompt_tokens, "completion_tokens": chunk.usage.completion_tokens}
        return StreamingChunk(
            content="",
            meta={"model": chunk.model, "received_at": datetime.now().isoformat(), "usage": usage},
            component_info=component_info,
        )

    # n is unused, so the API always returns only one choice
    # the argument is probably allowed for compatibility with OpenAI
    # see https://huggingface.co/docs/huggingface_hub/package_reference/inference_client#huggingface_hub.InferenceClient.chat_completion.n
    choice = chunk.choices[0]
    mapped_finish_reason = _map_hf_finish_reason_to_haystack(choice) if choice.finish_reason else None
    stream_chunk = StreamingChunk(
        content=choice.delta.content or "",
        meta={"model": chunk.model, "received_at": datetime.now().isoformat(), "finish_reason": choice.finish_reason},
        component_info=component_info,
        # Index must always be 0 since we don't allow tool calls in streaming mode.
        index=0 if choice.finish_reason is None else None,
        # start is True at the very beginning since first chunk contains role information + first part of the answer.
        start=len(previous_chunks) == 0,
        finish_reason=mapped_finish_reason,
    )
    return stream_chunk


@component
class HuggingFaceAPIChatGenerator:
    """
    Completes chats using Hugging Face APIs.

    HuggingFaceAPIChatGenerator uses the [ChatMessage](https://docs.haystack.deepset.ai/docs/chatmessage)
    format for input and output. Use it to generate text with Hugging Face APIs:
    - [Serverless Inference API (Inference Providers)](https://huggingface.co/docs/inference-providers)
    - [Paid Inference Endpoints](https://huggingface.co/inference-endpoints)
    - [Self-hosted Text Generation Inference](https://github.com/huggingface/text-generation-inference)

    ### Usage examples

    #### With the serverless inference API (Inference Providers) - free tier available

    ```python
    from haystack.components.generators.chat import HuggingFaceAPIChatGenerator
    from haystack.dataclasses import ChatMessage
    from haystack.utils import Secret
    from haystack.utils.hf import HFGenerationAPIType

    messages = [ChatMessage.from_system("\\nYou are a helpful, respectful and honest assistant"),
                ChatMessage.from_user("What's Natural Language Processing?")]

    # the api_type can be expressed using the HFGenerationAPIType enum or as a string
    api_type = HFGenerationAPIType.SERVERLESS_INFERENCE_API
    api_type = "serverless_inference_api" # this is equivalent to the above

    generator = HuggingFaceAPIChatGenerator(api_type=api_type,
                                            api_params={"model": "Qwen/Qwen2.5-7B-Instruct",
                                                        "provider": "together"},
                                            token=Secret.from_token("<your-api-key>"))

    result = generator.run(messages)
    print(result)
    ```

    #### With paid inference endpoints

    ```python
    from haystack.components.generators.chat import HuggingFaceAPIChatGenerator
    from haystack.dataclasses import ChatMessage
    from haystack.utils import Secret

    messages = [ChatMessage.from_system("\\nYou are a helpful, respectful and honest assistant"),
                ChatMessage.from_user("What's Natural Language Processing?")]

    generator = HuggingFaceAPIChatGenerator(api_type="inference_endpoints",
                                            api_params={"url": "<your-inference-endpoint-url>"},
                                            token=Secret.from_token("<your-api-key>"))

    result = generator.run(messages)
    print(result)

    #### With self-hosted text generation inference

    ```python
    from haystack.components.generators.chat import HuggingFaceAPIChatGenerator
    from haystack.dataclasses import ChatMessage

    messages = [ChatMessage.from_system("\\nYou are a helpful, respectful and honest assistant"),
                ChatMessage.from_user("What's Natural Language Processing?")]

    generator = HuggingFaceAPIChatGenerator(api_type="text_generation_inference",
                                            api_params={"url": "http://localhost:8080"})

    result = generator.run(messages)
    print(result)
    ```
    """

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        api_type: Union[HFGenerationAPIType, str],
        api_params: Dict[str, str],
        token: Optional[Secret] = Secret.from_env_var(["HF_API_TOKEN", "HF_TOKEN"], strict=False),
        generation_kwargs: Optional[Dict[str, Any]] = None,
        stop_words: Optional[List[str]] = None,
        streaming_callback: Optional[StreamingCallbackT] = None,
        tools: Optional[Union[List[Tool], Toolset]] = None,
    ):
        """
        Initialize the HuggingFaceAPIChatGenerator instance.

        :param api_type:
            The type of Hugging Face API to use. Available types:
            - `text_generation_inference`: See [TGI](https://github.com/huggingface/text-generation-inference).
            - `inference_endpoints`: See [Inference Endpoints](https://huggingface.co/inference-endpoints).
            - `serverless_inference_api`: See
            [Serverless Inference API - Inference Providers](https://huggingface.co/docs/inference-providers).
        :param api_params:
            A dictionary with the following keys:
            - `model`: Hugging Face model ID. Required when `api_type` is `SERVERLESS_INFERENCE_API`.
            - `provider`: Provider name. Recommended when `api_type` is `SERVERLESS_INFERENCE_API`.
            - `url`: URL of the inference endpoint. Required when `api_type` is `INFERENCE_ENDPOINTS` or
            `TEXT_GENERATION_INFERENCE`.
            - Other parameters specific to the chosen API type, such as `timeout`, `headers`, etc.
        :param token:
            The Hugging Face token to use as HTTP bearer authorization.
            Check your HF token in your [account settings](https://huggingface.co/settings/tokens).
        :param generation_kwargs:
            A dictionary with keyword arguments to customize text generation.
                Some examples: `max_tokens`, `temperature`, `top_p`.
                For details, see [Hugging Face chat_completion documentation](https://huggingface.co/docs/huggingface_hub/package_reference/inference_client#huggingface_hub.InferenceClient.chat_completion).
        :param stop_words:
            An optional list of strings representing the stop words.
        :param streaming_callback:
            An optional callable for handling streaming responses.
        :param tools:
            A list of tools or a Toolset for which the model can prepare calls.
            The chosen model should support tool/function calling, according to the model card.
            Support for tools in the Hugging Face API and TGI is not yet fully refined and you may experience
            unexpected behavior. This parameter can accept either a list of `Tool` objects or a `Toolset` instance.
        """

        huggingface_hub_import.check()

        if isinstance(api_type, str):
            api_type = HFGenerationAPIType.from_str(api_type)

        if api_type == HFGenerationAPIType.SERVERLESS_INFERENCE_API:
            model = api_params.get("model")
            if model is None:
                raise ValueError(
                    "To use the Serverless Inference API, you need to specify the `model` parameter in `api_params`."
                )
            check_valid_model(model, HFModelType.GENERATION, token)
            model_or_url = model
        elif api_type in [HFGenerationAPIType.INFERENCE_ENDPOINTS, HFGenerationAPIType.TEXT_GENERATION_INFERENCE]:
            url = api_params.get("url")
            if url is None:
                msg = (
                    "To use Text Generation Inference or Inference Endpoints, you need to specify the `url` parameter "
                    "in `api_params`."
                )
                raise ValueError(msg)
            if not is_valid_http_url(url):
                raise ValueError(f"Invalid URL: {url}")
            model_or_url = url
        else:
            msg = f"Unknown api_type {api_type}"
            raise ValueError(msg)

        if tools and streaming_callback is not None:
            raise ValueError("Using tools and streaming at the same time is not supported. Please choose one.")
        _check_duplicate_tool_names(list(tools or []))

        # handle generation kwargs setup
        generation_kwargs = generation_kwargs.copy() if generation_kwargs else {}
        generation_kwargs["stop"] = generation_kwargs.get("stop", [])
        generation_kwargs["stop"].extend(stop_words or [])
        generation_kwargs.setdefault("max_tokens", 512)

        self.api_type = api_type
        self.api_params = api_params
        self.token = token
        self.generation_kwargs = generation_kwargs
        self.streaming_callback = streaming_callback

        resolved_api_params: Dict[str, Any] = {k: v for k, v in api_params.items() if k != "model" and k != "url"}
        self._client = InferenceClient(
            model_or_url, token=token.resolve_value() if token else None, **resolved_api_params
        )
        self._async_client = AsyncInferenceClient(
            model_or_url, token=token.resolve_value() if token else None, **resolved_api_params
        )
        self.tools = tools

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize this component to a dictionary.

        :returns:
            A dictionary containing the serialized component.
        """
        callback_name = serialize_callable(self.streaming_callback) if self.streaming_callback else None
        return default_to_dict(
            self,
            api_type=str(self.api_type),
            api_params=self.api_params,
            token=self.token.to_dict() if self.token else None,
            generation_kwargs=self.generation_kwargs,
            streaming_callback=callback_name,
            tools=serialize_tools_or_toolset(self.tools),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HuggingFaceAPIChatGenerator":
        """
        Deserialize this component from a dictionary.
        """
        deserialize_secrets_inplace(data["init_parameters"], keys=["token"])
        deserialize_tools_or_toolset_inplace(data["init_parameters"], key="tools")
        init_params = data.get("init_parameters", {})
        serialized_callback_handler = init_params.get("streaming_callback")
        if serialized_callback_handler:
            data["init_parameters"]["streaming_callback"] = deserialize_callable(serialized_callback_handler)
        return default_from_dict(cls, data)

    @component.output_types(replies=List[ChatMessage])
    def run(
        self,
        messages: List[ChatMessage],
        generation_kwargs: Optional[Dict[str, Any]] = None,
        tools: Optional[Union[List[Tool], Toolset]] = None,
        streaming_callback: Optional[StreamingCallbackT] = None,
    ):
        """
        Invoke the text generation inference based on the provided messages and generation parameters.

        :param messages:
            A list of ChatMessage objects representing the input messages.
        :param generation_kwargs:
            Additional keyword arguments for text generation.
        :param tools:
            A list of tools or a Toolset for which the model can prepare calls. If set, it will override
            the `tools` parameter set during component initialization. This parameter can accept either a
            list of `Tool` objects or a `Toolset` instance.
        :param streaming_callback:
            An optional callable for handling streaming responses. If set, it will override the `streaming_callback`
            parameter set during component initialization.
        :returns: A dictionary with the following keys:
            - `replies`: A list containing the generated responses as ChatMessage objects.
        """

        # update generation kwargs by merging with the default ones
        generation_kwargs = {**self.generation_kwargs, **(generation_kwargs or {})}

        formatted_messages = [convert_message_to_hf_format(message) for message in messages]

        tools = tools or self.tools
        if tools and self.streaming_callback:
            raise ValueError("Using tools and streaming at the same time is not supported. Please choose one.")
        _check_duplicate_tool_names(list(tools or []))

        # validate and select the streaming callback
        streaming_callback = select_streaming_callback(
            self.streaming_callback, streaming_callback, requires_async=False
        )

        if streaming_callback:
            return self._run_streaming(formatted_messages, generation_kwargs, streaming_callback)

        if tools and isinstance(tools, Toolset):
            tools = list(tools)

        hf_tools = _convert_tools_to_hfapi_tools(tools)

        return self._run_non_streaming(formatted_messages, generation_kwargs, hf_tools)

    @component.output_types(replies=List[ChatMessage])
    async def run_async(
        self,
        messages: List[ChatMessage],
        generation_kwargs: Optional[Dict[str, Any]] = None,
        tools: Optional[Union[List[Tool], Toolset]] = None,
        streaming_callback: Optional[StreamingCallbackT] = None,
    ):
        """
        Asynchronously invokes the text generation inference based on the provided messages and generation parameters.

        This is the asynchronous version of the `run` method. It has the same parameters
        and return values but can be used with `await` in an async code.

        :param messages:
            A list of ChatMessage objects representing the input messages.
        :param generation_kwargs:
            Additional keyword arguments for text generation.
        :param tools:
            A list of tools or a Toolset for which the model can prepare calls. If set, it will override the `tools`
            parameter set during component initialization. This parameter can accept either a list of `Tool` objects
            or a `Toolset` instance.
        :param streaming_callback:
            An optional callable for handling streaming responses. If set, it will override the `streaming_callback`
            parameter set during component initialization.
        :returns: A dictionary with the following keys:
            - `replies`: A list containing the generated responses as ChatMessage objects.
        """

        # update generation kwargs by merging with the default ones
        generation_kwargs = {**self.generation_kwargs, **(generation_kwargs or {})}

        formatted_messages = [convert_message_to_hf_format(message) for message in messages]

        tools = tools or self.tools
        if tools and self.streaming_callback:
            raise ValueError("Using tools and streaming at the same time is not supported. Please choose one.")
        _check_duplicate_tool_names(list(tools or []))

        # validate and select the streaming callback
        streaming_callback = select_streaming_callback(self.streaming_callback, streaming_callback, requires_async=True)

        if streaming_callback:
            return await self._run_streaming_async(formatted_messages, generation_kwargs, streaming_callback)

        if tools and isinstance(tools, Toolset):
            tools = list(tools)

        hf_tools = _convert_tools_to_hfapi_tools(tools)

        return await self._run_non_streaming_async(formatted_messages, generation_kwargs, hf_tools)

    def _run_streaming(
        self,
        messages: List[Dict[str, str]],
        generation_kwargs: Dict[str, Any],
        streaming_callback: SyncStreamingCallbackT,
    ):
        api_output: Iterable[ChatCompletionStreamOutput] = self._client.chat_completion(
            messages,
            stream=True,
            stream_options=ChatCompletionInputStreamOptions(include_usage=True),
            **generation_kwargs,
        )

        component_info = ComponentInfo.from_component(self)
        streaming_chunks: List[StreamingChunk] = []
        for chunk in api_output:
            streaming_chunk = _convert_chat_completion_stream_output_to_streaming_chunk(
                chunk=chunk, previous_chunks=streaming_chunks, component_info=component_info
            )
            streaming_chunks.append(streaming_chunk)
            streaming_callback(streaming_chunk)

        message = _convert_streaming_chunks_to_chat_message(chunks=streaming_chunks)
        if message.meta.get("usage") is None:
            message.meta["usage"] = {"prompt_tokens": 0, "completion_tokens": 0}

        return {"replies": [message]}

    def _run_non_streaming(
        self,
        messages: List[Dict[str, str]],
        generation_kwargs: Dict[str, Any],
        tools: Optional[List["ChatCompletionInputTool"]] = None,
    ) -> Dict[str, List[ChatMessage]]:
        api_chat_output: ChatCompletionOutput = self._client.chat_completion(
            messages=messages, tools=tools, **generation_kwargs
        )

        if api_chat_output.choices is None or len(api_chat_output.choices) == 0:
            return {"replies": []}

        # n is unused, so the API always returns only one choice
        # the argument is probably allowed for compatibility with OpenAI
        # see https://huggingface.co/docs/huggingface_hub/package_reference/inference_client#huggingface_hub.InferenceClient.chat_completion.n
        choice = api_chat_output.choices[0]

        text = choice.message.content

        tool_calls = _convert_hfapi_tool_calls(choice.message.tool_calls)

        meta: Dict[str, Any] = {
            "model": self._client.model,
            "finish_reason": choice.finish_reason,
            "index": choice.index,
        }

        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        if api_chat_output.usage:
            usage = {
                "prompt_tokens": api_chat_output.usage.prompt_tokens,
                "completion_tokens": api_chat_output.usage.completion_tokens,
            }
        meta["usage"] = usage

        message = ChatMessage.from_assistant(text=text, tool_calls=tool_calls, meta=meta)
        return {"replies": [message]}

    async def _run_streaming_async(
        self,
        messages: List[Dict[str, str]],
        generation_kwargs: Dict[str, Any],
        streaming_callback: AsyncStreamingCallbackT,
    ):
        api_output: AsyncIterable[ChatCompletionStreamOutput] = await self._async_client.chat_completion(
            messages,
            stream=True,
            stream_options=ChatCompletionInputStreamOptions(include_usage=True),
            **generation_kwargs,
        )

        component_info = ComponentInfo.from_component(self)
        streaming_chunks: List[StreamingChunk] = []
        async for chunk in api_output:
            stream_chunk = _convert_chat_completion_stream_output_to_streaming_chunk(
                chunk=chunk, previous_chunks=streaming_chunks, component_info=component_info
            )
            streaming_chunks.append(stream_chunk)
            await streaming_callback(stream_chunk)  # type: ignore

        message = _convert_streaming_chunks_to_chat_message(chunks=streaming_chunks)
        if message.meta.get("usage") is None:
            message.meta["usage"] = {"prompt_tokens": 0, "completion_tokens": 0}

        return {"replies": [message]}

    async def _run_non_streaming_async(
        self,
        messages: List[Dict[str, str]],
        generation_kwargs: Dict[str, Any],
        tools: Optional[List["ChatCompletionInputTool"]] = None,
    ) -> Dict[str, List[ChatMessage]]:
        api_chat_output: ChatCompletionOutput = await self._async_client.chat_completion(
            messages=messages, tools=tools, **generation_kwargs
        )

        if api_chat_output.choices is None or len(api_chat_output.choices) == 0:
            return {"replies": []}

        choice = api_chat_output.choices[0]

        text = choice.message.content

        tool_calls = _convert_hfapi_tool_calls(choice.message.tool_calls)

        meta: Dict[str, Any] = {
            "model": self._async_client.model,
            "finish_reason": choice.finish_reason,
            "index": choice.index,
        }

        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        if api_chat_output.usage:
            usage = {
                "prompt_tokens": api_chat_output.usage.prompt_tokens,
                "completion_tokens": api_chat_output.usage.completion_tokens,
            }
        meta["usage"] = usage

        message = ChatMessage.from_assistant(text=text, tool_calls=tool_calls, meta=meta)
        return {"replies": [message]}
