import unittest
from unittest.mock import Mock, patch

from backend.app.bibliographic_admin_service import inspect_source_access
from backend.app.bibliographic_config import (
    BibliographicSourceConfig,
    SOURCE_OPENALEX,
    SOURCE_PUBMED,
    SOURCE_SEMANTIC_SCHOLAR,
    SOURCE_LABELS,
)


def _config(source_code):
    return BibliographicSourceConfig(
        source_code=source_code,
        label=SOURCE_LABELS[source_code],
        enabled=True,
        api_key=None,
        contact_email="pesquisa@instituicao.br",
        tool_name="rag-teste",
        timeout_seconds=15,
        max_retries=2,
    )


class BibliographicAdminServiceTests(unittest.TestCase):
    @patch("backend.app.bibliographic_admin_service.requests.get")
    def test_parametros_de_autenticacao_por_fonte(self, requests_get):
        resposta = Mock(status_code=200)
        resposta.raise_for_status.return_value = None
        requests_get.return_value = resposta

        resposta.json.return_value = {"results": []}
        inspect_source_access(SOURCE_OPENALEX, "chave-oa", _config(SOURCE_OPENALEX))
        chamada = requests_get.call_args.kwargs
        self.assertEqual(chamada["params"]["api_key"], "chave-oa")
        self.assertEqual(chamada["params"]["mailto"], "pesquisa@instituicao.br")

        resposta.json.return_value = {"data": []}
        inspect_source_access(
            SOURCE_SEMANTIC_SCHOLAR,
            "chave-s2",
            _config(SOURCE_SEMANTIC_SCHOLAR),
        )
        chamada = requests_get.call_args.kwargs
        self.assertEqual(chamada["headers"]["x-api-key"], "chave-s2")
        self.assertNotIn("api_key", chamada["params"])

        resposta.json.return_value = {"esearchresult": {"idlist": []}}
        inspect_source_access(SOURCE_PUBMED, "chave-ncbi", _config(SOURCE_PUBMED))
        chamada = requests_get.call_args.kwargs
        self.assertEqual(chamada["params"]["api_key"], "chave-ncbi")
        self.assertEqual(chamada["params"]["tool"], "rag-teste")

    @patch("backend.app.bibliographic_admin_service.requests.get")
    def test_erro_de_validacao_remove_chave_da_mensagem(self, requests_get):
        segredo = "chave-que-nao-pode-vazar"
        requests_get.side_effect = RuntimeError(f"Falha ao usar {segredo}")

        with self.assertRaises(RuntimeError) as contexto:
            inspect_source_access(SOURCE_OPENALEX, segredo, _config(SOURCE_OPENALEX))

        self.assertNotIn(segredo, str(contexto.exception))
        self.assertIn("[REDACTED]", str(contexto.exception))


if __name__ == "__main__":
    unittest.main()
