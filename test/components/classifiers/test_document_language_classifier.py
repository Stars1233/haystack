# SPDX-FileCopyrightText: 2022-present deepset GmbH <info@deepset.ai>
#
# SPDX-License-Identifier: Apache-2.0

import logging

import pytest

from haystack import Document
from haystack.components.classifiers import DocumentLanguageClassifier


class TestDocumentLanguageClassifier:
    def test_init(self):
        component = DocumentLanguageClassifier()
        assert component.languages == ["en"]

    def test_non_document_input(self):
        with pytest.raises(TypeError, match="DocumentLanguageClassifier expects a list of Document as input."):
            classifier = DocumentLanguageClassifier()
            classifier.run(documents="This is an english sentence.")

    def test_single_document(self):
        with pytest.raises(TypeError, match="DocumentLanguageClassifier expects a list of Document as input."):
            classifier = DocumentLanguageClassifier()
            classifier.run(documents=Document(content="This is an english sentence."))

    def test_empty_list(self):
        classifier = DocumentLanguageClassifier()
        result = classifier.run(documents=[])
        assert result == {"documents": []}

    def test_detect_language(self):
        classifier = DocumentLanguageClassifier()
        detected_language = classifier._detect_language(Document(content="This is an english sentence."))
        assert detected_language == "en"

    def test_classify_as_en_and_unmatched(self):
        classifier = DocumentLanguageClassifier()
        english_document = Document(content="This is an english sentence.")
        german_document = Document(content="Ein deutscher Satz ohne Verb.")
        result = classifier.run(documents=[english_document, german_document])
        assert result["documents"][0].meta["language"] == "en"
        assert result["documents"][1].meta["language"] == "unmatched"

    def test_warning_if_no_language_detected(self, caplog):
        with caplog.at_level(logging.WARNING):
            classifier = DocumentLanguageClassifier()
            classifier.run(documents=[Document(content=".")])
            assert "Langdetect cannot detect the language of Document with id" in caplog.text
