import unittest
from unittest.mock import Mock, patch

from backend.app.bibliographic_config import (
    BibliographicSourceConfig,
    SOURCE_OPENALEX,
    SOURCE_LABELS,
)
from backend.coleta.coleta_openalex import recolher_artigos_openalex
from backend.coleta.http_utils import safe_request_error


class BibliographicCollectorTests(unittest.TestCase):
    def test_erro_http_remove_chave_da_mensagem(self):
        segredo = "chave-na-url"
        mensagem = safe_request_error(
            RuntimeError(f"Falha em https://api.exemplo/?api_key={segredo}"),
            segredo,
        )

        self.assertNotIn(segredo, mensagem)
        self.assertIn("[REDACTED]", mensagem)

    @patch("backend.coleta.coleta_openalex.get_with_retry")
    @patch("backend.coleta.coleta_openalex.get_source_config")
    def test_fonte_desativada_nao_realiza_chamada_http(self, get_config, get_with_retry):
        get_config.return_value = BibliographicSourceConfig(
            source_code=SOURCE_OPENALEX,
            label=SOURCE_LABELS[SOURCE_OPENALEX],
            enabled=False,
            api_key=None,
            contact_email=None,
            tool_name="rag-teste",
            timeout_seconds=30,
            max_retries=3,
        )

        resultado = recolher_artigos_openalex("teste", max_resultados=1)

        self.assertEqual(resultado, [])
        get_with_retry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
