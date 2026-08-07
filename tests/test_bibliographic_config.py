import os
import unittest
from unittest.mock import patch

from backend.app.bibliographic_config import (
    SOURCE_OPENALEX,
    SOURCE_PUBMED,
    _apply_database_overrides,
    get_environment_bibliographic_settings,
)


class BibliographicConfigTests(unittest.TestCase):
    def test_ambiente_configura_fontes_sem_expor_chave(self):
        segredo = "chave-bibliografica-secreta"
        with patch.dict(
            os.environ,
            {
                "OPENALEX_API_KEY": segredo,
                "OPENALEX_EMAIL": "pesquisa@instituicao.br",
                "PUBMED_ENABLED": "false",
                "BIBLIOGRAPHIC_TIMEOUT_SECONDS": "45",
                "BIBLIOGRAPHIC_MAX_RETRIES": "4",
            },
            clear=True,
        ):
            settings = get_environment_bibliographic_settings()

        openalex = settings[SOURCE_OPENALEX]
        self.assertEqual(openalex.api_key, segredo)
        self.assertEqual(openalex.contact_email, "pesquisa@instituicao.br")
        self.assertEqual(openalex.timeout_seconds, 45)
        self.assertEqual(openalex.max_retries, 4)
        self.assertFalse(settings[SOURCE_PUBMED].enabled)
        self.assertNotIn(segredo, repr(openalex))
        self.assertNotIn("api_key", openalex.public_metadata())

    @patch("backend.app.secret_store.decrypt_secret", return_value="chave-do-banco")
    @patch("backend.app.bibliographic_config_repository.get_installation_credentials")
    @patch("backend.app.bibliographic_config_repository.get_installation_source_settings")
    @patch("backend.app.bibliographic_config_repository.bibliographic_tables_available", return_value=True)
    def test_banco_sobrescreve_configuracao_e_credencial(
        self,
        tables_available,
        get_settings,
        get_credentials,
        decrypt_secret,
    ):
        with patch.dict(os.environ, {}, clear=True):
            base = get_environment_bibliographic_settings()
        get_settings.return_value = {
            SOURCE_OPENALEX: {
                "is_enabled": False,
                "contact_email": "banco@instituicao.br",
                "tool_name": "aplicacao-banco",
                "request_timeout_seconds": 20,
                "max_retries": 2,
            }
        }
        get_credentials.return_value = {
            SOURCE_OPENALEX: {"encrypted_secret": "conteudo-cifrado"}
        }

        resultado = _apply_database_overrides(base)[SOURCE_OPENALEX]

        self.assertFalse(resultado.enabled)
        self.assertEqual(resultado.api_key, "chave-do-banco")
        self.assertEqual(resultado.source, "database")
        self.assertEqual(resultado.credential_source, "encrypted_database")


if __name__ == "__main__":
    unittest.main()
