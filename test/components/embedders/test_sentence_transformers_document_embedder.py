# SPDX-FileCopyrightText: 2022-present deepset GmbH <info@deepset.ai>
#
# SPDX-License-Identifier: Apache-2.0

import random
from unittest.mock import MagicMock, patch

import pytest
import torch

from haystack import Document
from haystack.components.embedders.sentence_transformers_document_embedder import SentenceTransformersDocumentEmbedder
from haystack.utils import ComponentDevice, Secret


class TestSentenceTransformersDocumentEmbedder:
    def test_init_default(self):
        embedder = SentenceTransformersDocumentEmbedder(model="model")
        assert embedder.model == "model"
        assert embedder.device == ComponentDevice.resolve_device(None)
        assert embedder.token == Secret.from_env_var(["HF_API_TOKEN", "HF_TOKEN"], strict=False)
        assert embedder.prefix == ""
        assert embedder.suffix == ""
        assert embedder.batch_size == 32
        assert embedder.progress_bar is True
        assert embedder.normalize_embeddings is False
        assert embedder.meta_fields_to_embed == []
        assert embedder.embedding_separator == "\n"
        assert embedder.trust_remote_code is False
        assert embedder.local_files_only is False
        assert embedder.truncate_dim is None
        assert embedder.precision == "float32"

    def test_init_with_parameters(self):
        embedder = SentenceTransformersDocumentEmbedder(
            model="model",
            device=ComponentDevice.from_str("cuda:0"),
            token=Secret.from_token("fake-api-token"),
            prefix="prefix",
            suffix="suffix",
            batch_size=64,
            progress_bar=False,
            normalize_embeddings=True,
            meta_fields_to_embed=["test_field"],
            embedding_separator=" | ",
            trust_remote_code=True,
            local_files_only=True,
            truncate_dim=256,
            precision="int8",
        )
        assert embedder.model == "model"
        assert embedder.device == ComponentDevice.from_str("cuda:0")
        assert embedder.token == Secret.from_token("fake-api-token")
        assert embedder.prefix == "prefix"
        assert embedder.suffix == "suffix"
        assert embedder.batch_size == 64
        assert embedder.progress_bar is False
        assert embedder.normalize_embeddings is True
        assert embedder.meta_fields_to_embed == ["test_field"]
        assert embedder.embedding_separator == " | "
        assert embedder.trust_remote_code
        assert embedder.local_files_only
        assert embedder.truncate_dim == 256
        assert embedder.precision == "int8"

    def test_to_dict(self):
        component = SentenceTransformersDocumentEmbedder(model="model", device=ComponentDevice.from_str("cpu"))
        data = component.to_dict()
        assert data == {
            "type": "haystack.components.embedders.sentence_transformers_document_embedder.SentenceTransformersDocumentEmbedder",  # noqa: E501
            "init_parameters": {
                "model": "model",
                "device": ComponentDevice.from_str("cpu").to_dict(),
                "token": {"env_vars": ["HF_API_TOKEN", "HF_TOKEN"], "strict": False, "type": "env_var"},
                "prefix": "",
                "suffix": "",
                "batch_size": 32,
                "progress_bar": True,
                "normalize_embeddings": False,
                "embedding_separator": "\n",
                "meta_fields_to_embed": [],
                "trust_remote_code": False,
                "local_files_only": False,
                "truncate_dim": None,
                "model_kwargs": None,
                "tokenizer_kwargs": None,
                "encode_kwargs": None,
                "config_kwargs": None,
                "precision": "float32",
                "backend": "torch",
            },
        }

    def test_to_dict_with_custom_init_parameters(self):
        component = SentenceTransformersDocumentEmbedder(
            model="model",
            device=ComponentDevice.from_str("cuda:0"),
            token=Secret.from_env_var("ENV_VAR", strict=False),
            prefix="prefix",
            suffix="suffix",
            batch_size=64,
            progress_bar=False,
            normalize_embeddings=True,
            meta_fields_to_embed=["meta_field"],
            embedding_separator=" - ",
            trust_remote_code=True,
            local_files_only=True,
            truncate_dim=256,
            model_kwargs={"torch_dtype": torch.float32},
            tokenizer_kwargs={"model_max_length": 512},
            config_kwargs={"use_memory_efficient_attention": True},
            precision="int8",
            encode_kwargs={"task": "clustering"},
        )
        data = component.to_dict()

        assert data == {
            "type": "haystack.components.embedders.sentence_transformers_document_embedder.SentenceTransformersDocumentEmbedder",  # noqa: E501
            "init_parameters": {
                "model": "model",
                "device": ComponentDevice.from_str("cuda:0").to_dict(),
                "token": {"env_vars": ["ENV_VAR"], "strict": False, "type": "env_var"},
                "prefix": "prefix",
                "suffix": "suffix",
                "batch_size": 64,
                "progress_bar": False,
                "normalize_embeddings": True,
                "embedding_separator": " - ",
                "trust_remote_code": True,
                "local_files_only": True,
                "meta_fields_to_embed": ["meta_field"],
                "truncate_dim": 256,
                "model_kwargs": {"torch_dtype": "torch.float32"},
                "tokenizer_kwargs": {"model_max_length": 512},
                "config_kwargs": {"use_memory_efficient_attention": True},
                "precision": "int8",
                "encode_kwargs": {"task": "clustering"},
                "backend": "torch",
            },
        }

    def test_from_dict(self):
        init_parameters = {
            "model": "model",
            "device": ComponentDevice.from_str("cuda:0").to_dict(),
            "token": {"env_vars": ["ENV_VAR"], "strict": False, "type": "env_var"},
            "prefix": "prefix",
            "suffix": "suffix",
            "batch_size": 64,
            "progress_bar": False,
            "normalize_embeddings": True,
            "embedding_separator": " - ",
            "meta_fields_to_embed": ["meta_field"],
            "trust_remote_code": True,
            "local_files_only": True,
            "truncate_dim": 256,
            "model_kwargs": {"torch_dtype": "torch.float32"},
            "tokenizer_kwargs": {"model_max_length": 512},
            "config_kwargs": {"use_memory_efficient_attention": True},
            "precision": "int8",
        }
        component = SentenceTransformersDocumentEmbedder.from_dict(
            {
                "type": "haystack.components.embedders.sentence_transformers_document_embedder.SentenceTransformersDocumentEmbedder",  # noqa: E501
                "init_parameters": init_parameters,
            }
        )
        assert component.model == "model"
        assert component.device == ComponentDevice.from_str("cuda:0")
        assert component.token == Secret.from_env_var("ENV_VAR", strict=False)
        assert component.prefix == "prefix"
        assert component.suffix == "suffix"
        assert component.batch_size == 64
        assert component.progress_bar is False
        assert component.normalize_embeddings is True
        assert component.embedding_separator == " - "
        assert component.trust_remote_code
        assert component.local_files_only
        assert component.meta_fields_to_embed == ["meta_field"]
        assert component.truncate_dim == 256
        assert component.model_kwargs == {"torch_dtype": torch.float32}
        assert component.tokenizer_kwargs == {"model_max_length": 512}
        assert component.config_kwargs == {"use_memory_efficient_attention": True}
        assert component.precision == "int8"

    def test_from_dict_no_default_parameters(self):
        component = SentenceTransformersDocumentEmbedder.from_dict(
            {
                "type": "haystack.components.embedders.sentence_transformers_document_embedder.SentenceTransformersDocumentEmbedder",  # noqa: E501
                "init_parameters": {},
            }
        )
        assert component.model == "sentence-transformers/all-mpnet-base-v2"
        assert component.device == ComponentDevice.resolve_device(None)
        assert component.token == Secret.from_env_var(["HF_API_TOKEN", "HF_TOKEN"], strict=False)
        assert component.prefix == ""
        assert component.suffix == ""
        assert component.batch_size == 32
        assert component.progress_bar is True
        assert component.normalize_embeddings is False
        assert component.embedding_separator == "\n"
        assert component.trust_remote_code is False
        assert component.local_files_only is False
        assert component.meta_fields_to_embed == []
        assert component.truncate_dim is None
        assert component.precision == "float32"

    def test_from_dict_none_device(self):
        init_parameters = {
            "model": "model",
            "device": None,
            "token": {"env_vars": ["ENV_VAR"], "strict": False, "type": "env_var"},
            "prefix": "prefix",
            "suffix": "suffix",
            "batch_size": 64,
            "progress_bar": False,
            "normalize_embeddings": True,
            "embedding_separator": " - ",
            "meta_fields_to_embed": ["meta_field"],
            "trust_remote_code": True,
            "local_files_only": False,
            "truncate_dim": None,
            "precision": "float32",
        }
        component = SentenceTransformersDocumentEmbedder.from_dict(
            {
                "type": "haystack.components.embedders.sentence_transformers_document_embedder.SentenceTransformersDocumentEmbedder",  # noqa: E501
                "init_parameters": init_parameters,
            }
        )
        assert component.model == "model"
        assert component.device == ComponentDevice.resolve_device(None)
        assert component.token == Secret.from_env_var("ENV_VAR", strict=False)
        assert component.prefix == "prefix"
        assert component.suffix == "suffix"
        assert component.batch_size == 64
        assert component.progress_bar is False
        assert component.normalize_embeddings is True
        assert component.embedding_separator == " - "
        assert component.trust_remote_code
        assert component.local_files_only is False
        assert component.meta_fields_to_embed == ["meta_field"]
        assert component.truncate_dim is None
        assert component.precision == "float32"

    @patch(
        "haystack.components.embedders.sentence_transformers_document_embedder._SentenceTransformersEmbeddingBackendFactory"
    )
    def test_warmup(self, mocked_factory):
        embedder = SentenceTransformersDocumentEmbedder(
            model="model",
            token=None,
            device=ComponentDevice.from_str("cpu"),
            tokenizer_kwargs={"model_max_length": 512},
            config_kwargs={"use_memory_efficient_attention": True},
        )
        mocked_factory.get_embedding_backend.assert_not_called()
        embedder.warm_up()
        embedder.embedding_backend.model.max_seq_length = 512
        mocked_factory.get_embedding_backend.assert_called_once_with(
            model="model",
            device="cpu",
            auth_token=None,
            trust_remote_code=False,
            local_files_only=False,
            truncate_dim=None,
            model_kwargs=None,
            tokenizer_kwargs={"model_max_length": 512},
            config_kwargs={"use_memory_efficient_attention": True},
            backend="torch",
        )

    @patch(
        "haystack.components.embedders.sentence_transformers_document_embedder._SentenceTransformersEmbeddingBackendFactory"
    )
    def test_warmup_doesnt_reload(self, mocked_factory):
        embedder = SentenceTransformersDocumentEmbedder(model="model")
        mocked_factory.get_embedding_backend.assert_not_called()
        embedder.warm_up()
        embedder.warm_up()
        mocked_factory.get_embedding_backend.assert_called_once()

    def test_run(self):
        embedder = SentenceTransformersDocumentEmbedder(model="model")
        embedder.embedding_backend = MagicMock()
        embedder.embedding_backend.embed = lambda x, **kwargs: [
            [random.random() for _ in range(16)] for _ in range(len(x))
        ]

        documents = [Document(content=f"document number {i}") for i in range(5)]

        result = embedder.run(documents=documents)

        assert isinstance(result["documents"], list)
        assert len(result["documents"]) == len(documents)
        for doc in result["documents"]:
            assert isinstance(doc, Document)
            assert isinstance(doc.embedding, list)
            assert isinstance(doc.embedding[0], float)

    def test_run_wrong_input_format(self):
        embedder = SentenceTransformersDocumentEmbedder(model="model")

        string_input = "text"
        list_integers_input = [1, 2, 3]

        with pytest.raises(
            TypeError, match="SentenceTransformersDocumentEmbedder expects a list of Documents as input"
        ):
            embedder.run(documents=string_input)

        with pytest.raises(
            TypeError, match="SentenceTransformersDocumentEmbedder expects a list of Documents as input"
        ):
            embedder.run(documents=list_integers_input)

    def test_embed_metadata(self):
        embedder = SentenceTransformersDocumentEmbedder(
            model="model", meta_fields_to_embed=["meta_field"], embedding_separator="\n"
        )
        embedder.embedding_backend = MagicMock()
        documents = [Document(content=f"document number {i}", meta={"meta_field": f"meta_value {i}"}) for i in range(5)]
        embedder.run(documents=documents)
        embedder.embedding_backend.embed.assert_called_once_with(
            [
                "meta_value 0\ndocument number 0",
                "meta_value 1\ndocument number 1",
                "meta_value 2\ndocument number 2",
                "meta_value 3\ndocument number 3",
                "meta_value 4\ndocument number 4",
            ],
            batch_size=32,
            show_progress_bar=True,
            normalize_embeddings=False,
            precision="float32",
        )

    def test_embed_encode_kwargs(self):
        embedder = SentenceTransformersDocumentEmbedder(model="model", encode_kwargs={"task": "retrieval.passage"})
        embedder.embedding_backend = MagicMock()
        documents = [Document(content=f"document number {i}") for i in range(5)]
        embedder.run(documents=documents)
        embedder.embedding_backend.embed.assert_called_once_with(
            ["document number 0", "document number 1", "document number 2", "document number 3", "document number 4"],
            batch_size=32,
            show_progress_bar=True,
            normalize_embeddings=False,
            precision="float32",
            task="retrieval.passage",
        )

    def test_prefix_suffix(self):
        embedder = SentenceTransformersDocumentEmbedder(
            model="model",
            prefix="my_prefix ",
            suffix=" my_suffix",
            meta_fields_to_embed=["meta_field"],
            embedding_separator="\n",
        )
        embedder.embedding_backend = MagicMock()
        documents = [Document(content=f"document number {i}", meta={"meta_field": f"meta_value {i}"}) for i in range(5)]
        embedder.run(documents=documents)
        embedder.embedding_backend.embed.assert_called_once_with(
            [
                "my_prefix meta_value 0\ndocument number 0 my_suffix",
                "my_prefix meta_value 1\ndocument number 1 my_suffix",
                "my_prefix meta_value 2\ndocument number 2 my_suffix",
                "my_prefix meta_value 3\ndocument number 3 my_suffix",
                "my_prefix meta_value 4\ndocument number 4 my_suffix",
            ],
            batch_size=32,
            show_progress_bar=True,
            normalize_embeddings=False,
            precision="float32",
        )

    @patch(
        "haystack.components.embedders.sentence_transformers_document_embedder._SentenceTransformersEmbeddingBackendFactory"
    )
    def test_model_onnx_backend(self, mocked_factory):
        onnx_embedder = SentenceTransformersDocumentEmbedder(
            model="sentence-transformers/all-MiniLM-L6-v2",
            token=None,
            device=ComponentDevice.from_str("cpu"),
            # setting the path isn't necessary if the repo contains a "onnx/model.onnx" file but this is to prevent
            # a HF warning
            model_kwargs={"file_name": "onnx/model.onnx"},
            backend="onnx",
        )
        onnx_embedder.warm_up()

        mocked_factory.get_embedding_backend.assert_called_once_with(
            model="sentence-transformers/all-MiniLM-L6-v2",
            device="cpu",
            auth_token=None,
            trust_remote_code=False,
            local_files_only=False,
            truncate_dim=None,
            model_kwargs={"file_name": "onnx/model.onnx"},
            tokenizer_kwargs=None,
            config_kwargs=None,
            backend="onnx",
        )

    @patch(
        "haystack.components.embedders.sentence_transformers_document_embedder._SentenceTransformersEmbeddingBackendFactory"
    )
    def test_model_openvino_backend(self, mocked_factory):
        openvino_embedder = SentenceTransformersDocumentEmbedder(
            model="sentence-transformers/all-MiniLM-L6-v2",
            token=None,
            device=ComponentDevice.from_str("cpu"),
            # setting the path isn't necessary if the repo contains a "openvino/openvino_model.xml" file but this is
            # to prevent a HF warning
            model_kwargs={"file_name": "openvino/openvino_model.xml"},
            backend="openvino",
        )
        openvino_embedder.warm_up()

        mocked_factory.get_embedding_backend.assert_called_once_with(
            model="sentence-transformers/all-MiniLM-L6-v2",
            device="cpu",
            auth_token=None,
            trust_remote_code=False,
            local_files_only=False,
            truncate_dim=None,
            model_kwargs={"file_name": "openvino/openvino_model.xml"},
            tokenizer_kwargs=None,
            config_kwargs=None,
            backend="openvino",
        )

    @patch(
        "haystack.components.embedders.sentence_transformers_document_embedder._SentenceTransformersEmbeddingBackendFactory"
    )
    @pytest.mark.parametrize("model_kwargs", [{"torch_dtype": "bfloat16"}, {"torch_dtype": "float16"}])
    def test_dtype_on_gpu(self, mocked_factory, model_kwargs):
        torch_dtype_embedder = SentenceTransformersDocumentEmbedder(
            model="sentence-transformers/all-MiniLM-L6-v2",
            token=None,
            device=ComponentDevice.from_str("cuda:0"),
            model_kwargs=model_kwargs,
        )
        torch_dtype_embedder.warm_up()

        mocked_factory.get_embedding_backend.assert_called_once_with(
            model="sentence-transformers/all-MiniLM-L6-v2",
            device="cuda:0",
            auth_token=None,
            trust_remote_code=False,
            local_files_only=False,
            truncate_dim=None,
            model_kwargs=model_kwargs,
            tokenizer_kwargs=None,
            config_kwargs=None,
            backend="torch",
        )
