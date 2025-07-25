# SPDX-FileCopyrightText: 2022-present deepset GmbH <info@deepset.ai>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from unittest.mock import Mock, patch

import pytest

from haystack import Document
from haystack.components.converters.pypdf import PyPDFExtractionMode, PyPDFToDocument
from haystack.components.preprocessors import DocumentSplitter
from haystack.dataclasses import ByteStream


@pytest.fixture
def pypdf_component():
    return PyPDFToDocument()


class TestPyPDFToDocument:
    def test_init(self, pypdf_component):
        assert pypdf_component.extraction_mode == PyPDFExtractionMode.PLAIN
        assert pypdf_component.plain_mode_orientations == (0, 90, 180, 270)
        assert pypdf_component.plain_mode_space_width == 200.0
        assert pypdf_component.layout_mode_space_vertically is True
        assert pypdf_component.layout_mode_scale_weight == 1.25
        assert pypdf_component.layout_mode_strip_rotated is True
        assert pypdf_component.layout_mode_font_height_weight == 1.0

    def test_init_custom_params(self):
        pypdf_component = PyPDFToDocument(
            extraction_mode="layout",
            plain_mode_orientations=(0, 90),
            plain_mode_space_width=150.0,
            layout_mode_space_vertically=False,
            layout_mode_scale_weight=2.0,
            layout_mode_strip_rotated=False,
            layout_mode_font_height_weight=0.5,
        )

        assert pypdf_component.extraction_mode == PyPDFExtractionMode.LAYOUT
        assert pypdf_component.plain_mode_orientations == (0, 90)
        assert pypdf_component.plain_mode_space_width == 150.0
        assert pypdf_component.layout_mode_space_vertically is False
        assert pypdf_component.layout_mode_scale_weight == 2.0
        assert pypdf_component.layout_mode_strip_rotated is False
        assert pypdf_component.layout_mode_font_height_weight == 0.5

    def test_init_invalid_extraction_mode(self):
        with pytest.raises(ValueError):
            PyPDFToDocument(extraction_mode="invalid")

    def test_to_dict(self, pypdf_component):
        data = pypdf_component.to_dict()
        assert data == {
            "type": "haystack.components.converters.pypdf.PyPDFToDocument",
            "init_parameters": {
                "extraction_mode": "plain",
                "plain_mode_orientations": (0, 90, 180, 270),
                "plain_mode_space_width": 200.0,
                "layout_mode_space_vertically": True,
                "layout_mode_scale_weight": 1.25,
                "layout_mode_strip_rotated": True,
                "layout_mode_font_height_weight": 1.0,
                "store_full_path": False,
            },
        }

    def test_from_dict(self):
        data = {
            "type": "haystack.components.converters.pypdf.PyPDFToDocument",
            "init_parameters": {
                "extraction_mode": "plain",
                "plain_mode_orientations": (0, 90, 180, 270),
                "plain_mode_space_width": 200.0,
                "layout_mode_space_vertically": True,
                "layout_mode_scale_weight": 1.25,
                "layout_mode_strip_rotated": True,
                "layout_mode_font_height_weight": 1.0,
            },
        }

        instance = PyPDFToDocument.from_dict(data)
        assert isinstance(instance, PyPDFToDocument)
        assert instance.extraction_mode == PyPDFExtractionMode.PLAIN
        assert instance.plain_mode_orientations == (0, 90, 180, 270)
        assert instance.plain_mode_space_width == 200.0
        assert instance.layout_mode_space_vertically is True
        assert instance.layout_mode_scale_weight == 1.25
        assert instance.layout_mode_strip_rotated is True
        assert instance.layout_mode_font_height_weight == 1.0

    def test_from_dict_defaults(self):
        data = {"type": "haystack.components.converters.pypdf.PyPDFToDocument", "init_parameters": {}}
        instance = PyPDFToDocument.from_dict(data)
        assert isinstance(instance, PyPDFToDocument)
        assert instance.extraction_mode == PyPDFExtractionMode.PLAIN

    def test_default_convert(self):
        mock_page1 = Mock()
        mock_page2 = Mock()
        mock_page1.extract_text.return_value = "Page 1 content"
        mock_page2.extract_text.return_value = "Page 2 content"
        mock_reader = Mock()
        mock_reader.pages = [mock_page1, mock_page2]

        converter = PyPDFToDocument(
            extraction_mode="layout",
            plain_mode_orientations=(0, 90),
            plain_mode_space_width=150.0,
            layout_mode_space_vertically=False,
            layout_mode_scale_weight=2.0,
            layout_mode_strip_rotated=False,
            layout_mode_font_height_weight=1.5,
        )

        text = converter._default_convert(mock_reader)
        assert text == "Page 1 content\fPage 2 content"

        expected_params = {
            "extraction_mode": "layout",
            "orientations": (0, 90),
            "space_width": 150.0,
            "layout_mode_space_vertically": False,
            "layout_mode_scale_weight": 2.0,
            "layout_mode_strip_rotated": False,
            "layout_mode_font_height_weight": 1.5,
        }
        for mock_page in mock_reader.pages:
            mock_page.extract_text.assert_called_once_with(**expected_params)

    @pytest.mark.integration
    def test_run(self, test_files_path, pypdf_component):
        """
        Test if the component runs correctly.
        """
        paths = [test_files_path / "pdf" / "sample_pdf_1.pdf"]
        output = pypdf_component.run(sources=paths)
        docs = output["documents"]
        assert len(docs) == 1
        assert "History" in docs[0].content

    @pytest.mark.integration
    def test_page_breaks_added(self, test_files_path, pypdf_component):
        paths = [test_files_path / "pdf" / "sample_pdf_1.pdf"]
        output = pypdf_component.run(sources=paths)
        docs = output["documents"]
        assert len(docs) == 1
        assert docs[0].content.count("\f") == 3

    def test_run_with_meta(self, test_files_path, pypdf_component):
        bytestream = ByteStream(data=b"test", meta={"author": "test_author", "language": "en"})

        with patch("haystack.components.converters.pypdf.PdfReader"):
            output = pypdf_component.run(
                sources=[bytestream, test_files_path / "pdf" / "sample_pdf_1.pdf"], meta={"language": "it"}
            )

        # check that the metadata from the bytestream is merged with that from the meta parameter
        assert output["documents"][0].meta["author"] == "test_author"
        assert output["documents"][0].meta["language"] == "it"
        assert output["documents"][1].meta["language"] == "it"

    def test_run_with_store_full_path_false(self, test_files_path):
        """
        Test if the component runs correctly with store_full_path=False
        """
        sources = [test_files_path / "pdf" / "sample_pdf_1.pdf"]
        converter = PyPDFToDocument(store_full_path=True)
        results = converter.run(sources=sources)
        docs = results["documents"]

        assert len(docs) == 1
        assert docs[0].meta["file_path"] == str(sources[0])

        converter = PyPDFToDocument(store_full_path=False)
        results = converter.run(sources=sources)
        docs = results["documents"]

        assert len(docs) == 1
        assert docs[0].meta["file_path"] == "sample_pdf_1.pdf"

    def test_run_error_handling(self, test_files_path, pypdf_component, caplog):
        """
        Test if the component correctly handles errors.
        """
        paths = ["non_existing_file.pdf"]
        with caplog.at_level(logging.WARNING):
            pypdf_component.run(sources=paths)
            assert "Could not read non_existing_file.pdf" in caplog.text

    @pytest.mark.integration
    def test_mixed_sources_run(self, test_files_path, pypdf_component):
        """
        Test if the component runs correctly when mixed sources are provided.
        """
        paths = [test_files_path / "pdf" / "sample_pdf_1.pdf"]
        with open(test_files_path / "pdf" / "sample_pdf_1.pdf", "rb") as f:
            paths.append(ByteStream(f.read()))

        output = pypdf_component.run(sources=paths)
        docs = output["documents"]
        assert len(docs) == 2
        assert "History and standardization" in docs[0].content
        assert "History and standardization" in docs[1].content

    def test_run_empty_document(self, caplog, test_files_path):
        paths = [test_files_path / "pdf" / "non_text_searchable.pdf"]
        with caplog.at_level(logging.WARNING):
            output = PyPDFToDocument().run(sources=paths)
            assert "PyPDFToDocument could not extract text from the file" in caplog.text
            assert output["documents"][0].content == ""

            # Check that meta is used when the returned document is initialized and thus when doc id is generated
            assert output["documents"][0].meta["file_path"] == "non_text_searchable.pdf"
            assert output["documents"][0].id != Document(content="").id

    def test_run_detect_paragraphs_to_be_used_in_split_passage(self, test_files_path):
        converter = PyPDFToDocument(extraction_mode=PyPDFExtractionMode.LAYOUT)
        sources = [test_files_path / "pdf" / "sample_pdf_2.pdf"]
        pdf_doc = converter.run(sources=sources)
        splitter = DocumentSplitter(split_length=1, split_by="passage")
        docs = splitter.run(pdf_doc["documents"])

        assert len(docs["documents"]) == 51

        expected = (
            "A wiki (/ˈwɪki/ (About this soundlisten) WIK-ee) is a hypertext publication collaboratively\n"
            "edited and managed by its own audience directly using a web browser. A typical wiki\ncontains "
            "multiple pages for the subjects or scope of the project and may be either open\nto the public or "
            "limited to use within an organization for maintaining its internal knowledge\nbase. Wikis are "
            "enabled by wiki software, otherwise known as wiki engines. A wiki engine,\nbeing a form of a "
            "content management system, diﬀers from other web-based systems\nsuch as blog software, in that "
            "the content is created without any deﬁned owner or leader,\nand wikis have little inherent "
            "structure, allowing structure to emerge according to the\nneeds of the users.[1]\n\n"
        )
        assert docs["documents"][2].content == expected
