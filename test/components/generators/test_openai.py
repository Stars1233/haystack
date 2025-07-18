# SPDX-FileCopyrightText: 2022-present deepset GmbH <info@deepset.ai>
#
# SPDX-License-Identifier: Apache-2.0

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from openai import OpenAIError
from openai.types.chat import ChatCompletionChunk, chat_completion_chunk

from haystack.components.generators import OpenAIGenerator
from haystack.components.generators.utils import print_streaming_chunk
from haystack.dataclasses import StreamingChunk
from haystack.utils.auth import Secret


class TestOpenAIGenerator:
    def test_init_default(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
        component = OpenAIGenerator()
        assert component.client.api_key == "test-api-key"
        assert component.model == "gpt-4o-mini"
        assert component.streaming_callback is None
        assert not component.generation_kwargs
        assert component.client.timeout == 30
        assert component.client.max_retries == 5

    def test_init_fail_wo_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="None of the .* environment variables are set"):
            OpenAIGenerator()

    def test_init_with_parameters(self, monkeypatch):
        monkeypatch.setenv("OPENAI_TIMEOUT", "100")
        monkeypatch.setenv("OPENAI_MAX_RETRIES", "10")
        component = OpenAIGenerator(
            api_key=Secret.from_token("test-api-key"),
            model="gpt-4o-mini",
            streaming_callback=print_streaming_chunk,
            api_base_url="test-base-url",
            generation_kwargs={"max_tokens": 10, "some_test_param": "test-params"},
            timeout=40.0,
            max_retries=1,
        )
        assert component.client.api_key == "test-api-key"
        assert component.model == "gpt-4o-mini"
        assert component.streaming_callback is print_streaming_chunk
        assert component.generation_kwargs == {"max_tokens": 10, "some_test_param": "test-params"}
        assert component.client.timeout == 40.0
        assert component.client.max_retries == 1

    def test_to_dict_default(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
        component = OpenAIGenerator()
        data = component.to_dict()
        assert data == {
            "type": "haystack.components.generators.openai.OpenAIGenerator",
            "init_parameters": {
                "api_key": {"env_vars": ["OPENAI_API_KEY"], "strict": True, "type": "env_var"},
                "model": "gpt-4o-mini",
                "streaming_callback": None,
                "system_prompt": None,
                "api_base_url": None,
                "organization": None,
                "http_client_kwargs": None,
                "generation_kwargs": {},
            },
        }

    def test_to_dict_with_parameters(self, monkeypatch):
        monkeypatch.setenv("ENV_VAR", "test-api-key")
        component = OpenAIGenerator(
            api_key=Secret.from_env_var("ENV_VAR"),
            model="gpt-4o-mini",
            streaming_callback=print_streaming_chunk,
            api_base_url="test-base-url",
            organization="org-1234567",
            http_client_kwargs={"proxy": "http://localhost:8080"},
            generation_kwargs={"max_tokens": 10, "some_test_param": "test-params"},
        )
        data = component.to_dict()
        assert data == {
            "type": "haystack.components.generators.openai.OpenAIGenerator",
            "init_parameters": {
                "api_key": {"env_vars": ["ENV_VAR"], "strict": True, "type": "env_var"},
                "model": "gpt-4o-mini",
                "system_prompt": None,
                "api_base_url": "test-base-url",
                "organization": "org-1234567",
                "http_client_kwargs": {"proxy": "http://localhost:8080"},
                "streaming_callback": "haystack.components.generators.utils.print_streaming_chunk",
                "generation_kwargs": {"max_tokens": 10, "some_test_param": "test-params"},
            },
        }

    def test_from_dict(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-api-key")
        data = {
            "type": "haystack.components.generators.openai.OpenAIGenerator",
            "init_parameters": {
                "api_key": {"env_vars": ["OPENAI_API_KEY"], "strict": True, "type": "env_var"},
                "model": "gpt-4o-mini",
                "system_prompt": None,
                "organization": None,
                "api_base_url": "test-base-url",
                "http_client_kwargs": None,
                "streaming_callback": "haystack.components.generators.utils.print_streaming_chunk",
                "generation_kwargs": {"max_tokens": 10, "some_test_param": "test-params"},
            },
        }
        component = OpenAIGenerator.from_dict(data)
        assert component.model == "gpt-4o-mini"
        assert component.streaming_callback is print_streaming_chunk
        assert component.api_base_url == "test-base-url"
        assert component.generation_kwargs == {"max_tokens": 10, "some_test_param": "test-params"}
        assert component.api_key == Secret.from_env_var("OPENAI_API_KEY")
        assert component.http_client_kwargs is None

    def test_from_dict_fail_wo_env_var(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        data = {
            "type": "haystack.components.generators.openai.OpenAIGenerator",
            "init_parameters": {
                "api_key": {"env_vars": ["OPENAI_API_KEY"], "strict": True, "type": "env_var"},
                "model": "gpt-4o-mini",
                "api_base_url": "test-base-url",
                "streaming_callback": "haystack.components.generators.utils.print_streaming_chunk",
                "generation_kwargs": {"max_tokens": 10, "some_test_param": "test-params"},
            },
        }
        with pytest.raises(ValueError, match="None of the .* environment variables are set"):
            OpenAIGenerator.from_dict(data)

    def test_run(self, openai_mock_chat_completion):
        component = OpenAIGenerator(api_key=Secret.from_token("test-api-key"))
        response = component.run("What's Natural Language Processing?")

        # check that the component returns the correct ChatMessage response
        assert isinstance(response, dict)
        assert "replies" in response
        assert isinstance(response["replies"], list)
        assert len(response["replies"]) == 1
        assert [isinstance(reply, str) for reply in response["replies"]]

    def test_run_with_params_streaming(self, openai_mock_chat_completion_chunk):
        streaming_callback_called = False

        def streaming_callback(chunk: StreamingChunk) -> None:
            nonlocal streaming_callback_called
            streaming_callback_called = True

        component = OpenAIGenerator(api_key=Secret.from_token("test-api-key"), streaming_callback=streaming_callback)
        response = component.run("Come on, stream!")

        # check we called the streaming callback
        assert streaming_callback_called

        # check that the component still returns the correct response
        assert isinstance(response, dict)
        assert "replies" in response
        assert isinstance(response["replies"], list)
        assert len(response["replies"]) == 1
        assert "Hello" in response["replies"][0]  # see openai_mock_chat_completion_chunk

    def test_run_with_streaming_callback_in_run_method(self, openai_mock_chat_completion_chunk):
        streaming_callback_called = False

        def streaming_callback(chunk: StreamingChunk) -> None:
            nonlocal streaming_callback_called
            streaming_callback_called = True

        # pass streaming_callback to run()
        component = OpenAIGenerator(api_key=Secret.from_token("test-api-key"))
        response = component.run("Come on, stream!", streaming_callback=streaming_callback)

        # check we called the streaming callback
        assert streaming_callback_called

        # check that the component still returns the correct response
        assert isinstance(response, dict)
        assert "replies" in response
        assert isinstance(response["replies"], list)
        assert len(response["replies"]) == 1
        assert "Hello" in response["replies"][0]  # see openai_mock_chat_completion_chunk

    def test_run_with_params(self, openai_mock_chat_completion):
        component = OpenAIGenerator(
            api_key=Secret.from_token("test-api-key"), generation_kwargs={"max_tokens": 10, "temperature": 0.5}
        )
        response = component.run("What's Natural Language Processing?")

        # check that the component calls the OpenAI API with the correct parameters
        _, kwargs = openai_mock_chat_completion.call_args
        assert kwargs["max_tokens"] == 10
        assert kwargs["temperature"] == 0.5

        # check that the component returns the correct response
        assert isinstance(response, dict)
        assert "replies" in response
        assert isinstance(response["replies"], list)
        assert len(response["replies"]) == 1
        assert [isinstance(reply, str) for reply in response["replies"]]

    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY", None),
        reason="Export an env var called OPENAI_API_KEY containing the OpenAI API key to run this test.",
    )
    @pytest.mark.integration
    def test_live_run(self):
        component = OpenAIGenerator()
        results = component.run("What's the capital of France?")
        assert len(results["replies"]) == 1
        assert len(results["meta"]) == 1
        response: str = results["replies"][0]
        assert "Paris" in response

        metadata = results["meta"][0]
        assert "gpt-4o-mini" in metadata["model"]
        assert metadata["finish_reason"] == "stop"

        assert "usage" in metadata
        assert "prompt_tokens" in metadata["usage"] and metadata["usage"]["prompt_tokens"] > 0
        assert "completion_tokens" in metadata["usage"] and metadata["usage"]["completion_tokens"] > 0
        assert "total_tokens" in metadata["usage"] and metadata["usage"]["total_tokens"] > 0

    def test_run_with_wrong_model(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = OpenAIError("Invalid model name")

        generator = OpenAIGenerator(api_key=Secret.from_token("test-api-key"), model="something-obviously-wrong")

        generator.client = mock_client

        with pytest.raises(OpenAIError):
            generator.run("Whatever")

    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY", None),
        reason="Export an env var called OPENAI_API_KEY containing the OpenAI API key to run this test.",
    )
    @pytest.mark.integration
    def test_run_with_system_prompt(self):
        generator = OpenAIGenerator(model="gpt-4o-mini", system_prompt="Answer in Italian using only one word.")
        result = generator.run("What's the capital of Italy?")
        assert "roma" in result["replies"][0].lower()

    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY", None),
        reason="Export an env var called OPENAI_API_KEY containing the OpenAI API key to run this test.",
    )
    @pytest.mark.integration
    def test_live_run_streaming_with_include_usage(self):
        class Callback:
            def __init__(self):
                self.responses = ""
                self.counter = 0

            def __call__(self, chunk: StreamingChunk) -> None:
                self.counter += 1
                self.responses += chunk.content if chunk.content else ""

        callback = Callback()
        component = OpenAIGenerator(
            streaming_callback=callback, generation_kwargs={"stream_options": {"include_usage": True}}
        )
        results = component.run("What's the capital of France?")

        # Basic response validation
        assert len(results["replies"]) == 1
        assert len(results["meta"]) == 1
        response: str = results["replies"][0]
        assert "Paris" in response

        # Metadata validation
        metadata = results["meta"][0]
        assert "gpt-4o-mini" in metadata["model"]
        assert metadata["finish_reason"] == "stop"

        # Basic usage validation
        assert isinstance(metadata.get("usage"), dict), "meta.usage not a dict"
        usage = metadata["usage"]
        assert "prompt_tokens" in usage and usage["prompt_tokens"] > 0
        assert "completion_tokens" in usage and usage["completion_tokens"] > 0

        # Detailed token information validation
        assert isinstance(usage.get("completion_tokens_details"), dict), "usage.completion_tokens_details not a dict"
        assert isinstance(usage.get("prompt_tokens_details"), dict), "usage.prompt_tokens_details not a dict"

        # Streaming callback validation
        assert callback.counter > 1
        assert "Paris" in callback.responses

    def test_run_with_wrapped_stream_simulation(self, openai_mock_stream):
        streaming_callback_called = False

        def streaming_callback(chunk: StreamingChunk) -> None:
            nonlocal streaming_callback_called
            streaming_callback_called = True
            assert isinstance(chunk, StreamingChunk)

        chunk = ChatCompletionChunk(
            id="id",
            model="gpt-4",
            object="chat.completion.chunk",
            choices=[
                chat_completion_chunk.Choice(
                    index=0, delta=chat_completion_chunk.ChoiceDelta(content="Hello"), finish_reason="stop"
                )
            ],
            created=int(datetime.now().timestamp()),
        )

        # Here we wrap the OpenAI stream in a MagicMock
        # This is to simulate the behavior of some tools like Weave (https://github.com/wandb/weave)
        # which wrap the OpenAI stream in their own stream
        wrapped_openai_stream = MagicMock()
        wrapped_openai_stream.__iter__.return_value = iter([chunk])

        component = OpenAIGenerator(api_key=Secret.from_token("test-api-key"))

        with patch.object(
            component.client.chat.completions, "create", return_value=wrapped_openai_stream
        ) as mock_create:
            response = component.run(prompt="test prompt", streaming_callback=streaming_callback)

            mock_create.assert_called_once()
            assert streaming_callback_called
            assert "replies" in response
            assert "Hello" in response["replies"][0]
            assert response["meta"][0]["finish_reason"] == "stop"
