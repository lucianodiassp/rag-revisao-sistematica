import unittest
from unittest.mock import Mock

from backend.processamento.ocr_pdf import PdfOcrConfig, extract_pdf_document


class FakeDocument:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def __len__(self):
        return len(self.pages)

    def __iter__(self):
        return iter(self.pages)


class PdfOcrTests(unittest.TestCase):
    def setUp(self):
        self.config = PdfOcrConfig(
            enabled=True,
            languages="por+eng",
            dpi=300,
            min_native_characters=20,
        )

    def test_texto_nativo_suficiente_nao_aciona_ocr(self):
        page = Mock()
        page.get_text.return_value = "Texto nativo suficiente para esta página."

        result = extract_pdf_document(
            "artigo.pdf",
            config=self.config,
            document_opener=lambda _: FakeDocument([page]),
        )

        page.get_textpage_ocr.assert_not_called()
        self.assertEqual(result["ocr_attempted_pages"], 0)
        self.assertEqual(result["pages"][0]["text_extraction_method"], "native")

    def test_pagina_sem_texto_usa_ocr_e_registra_proveniencia(self):
        page = Mock()
        text_page = object()
        page.get_text.side_effect = ["", "Conteúdo reconhecido da imagem do artigo."]
        page.get_textpage_ocr.return_value = text_page

        result = extract_pdf_document(
            "digitalizado.pdf",
            config=self.config,
            document_opener=lambda _: FakeDocument([page]),
        )

        page.get_textpage_ocr.assert_called_once_with(
            language="por+eng",
            dpi=300,
            full=True,
            tessdata=None,
        )
        page.get_text.assert_called_with("text", textpage=text_page)
        self.assertEqual(result["ocr_pages"], 1)
        self.assertEqual(result["pages"][0]["text_extraction_method"], "ocr")
        self.assertEqual(result["pages"][0]["ocr_languages"], "por+eng")
        self.assertEqual(result["pages"][0]["ocr_dpi"], 300)

    def test_falha_de_ocr_preserva_texto_nativo_curto_e_emite_aviso(self):
        page = Mock()
        page.get_text.return_value = "Fig. 1"
        page.get_textpage_ocr.side_effect = RuntimeError("idioma indisponível")

        result = extract_pdf_document(
            "artigo.pdf",
            config=self.config,
            document_opener=lambda _: FakeDocument([page]),
        )

        self.assertEqual(result["ocr_failed_pages"], 1)
        self.assertEqual(result["pages"][0]["text"], "Fig. 1")
        self.assertEqual(
            result["pages"][0]["text_extraction_method"], "native_low_text"
        )
        self.assertIn("idioma indisponível", result["warnings"][0]["message"])


if __name__ == "__main__":
    unittest.main()
