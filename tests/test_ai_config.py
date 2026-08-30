import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.app.ai_config import (
    TASK_EXTRACTION,
    TASK_RERANKING,
    TASK_REPORT,
    clear_ai_settings_cache,
    get_ai_settings,
    get_generation_config,
    get_provider_api_key,
)
from backend.app.ai_config_repository import SUPPORTED_TASKS
from backend.app.ai_service import generate_content


def test_historical_reranking_migration_accepts_every_supported_task():
    migration = (
        Path(__file__).resolve().parents[1]
        / "database"
        / "scripts"
        / "008_reranking_configuration.sql"
    ).read_text(encoding="utf-8")

    for task in SUPPORTED_TASKS:
        assert f"'{task}'" in migration


class AIConfigTests(unittest.TestCase):
    def tearDown(self):
        clear_ai_settings_cache()

    def test_modelo_padrao_e_override_por_funcao(self):
        ambiente = {
            "AI_CONFIG_DATABASE_ENABLED": "false",
            "AI_PROVIDER": "gemini",
            "AI_DEFAULT_GENERATION_MODEL": "modelo-padrao",
            "AI_EXTRACTION_MODEL": "modelo-extrator",
            "AI_EMBEDDING_MODEL": "embedding-teste",
            "AI_EMBEDDING_DIMENSIONS": "768",
        }
        with patch.dict(os.environ, ambiente, clear=True):
            clear_ai_settings_cache()
            self.assertEqual(get_generation_config(TASK_REPORT).model, "modelo-padrao")
            self.assertEqual(get_generation_config(TASK_EXTRACTION).model, "modelo-extrator")
            self.assertEqual(get_ai_settings().provider, "google_gemini")

    def test_modelo_novo_remove_temperatura_incompativel(self):
        with patch.dict(
            os.environ,
            {
                "AI_CONFIG_DATABASE_ENABLED": "false",
                "AI_DEFAULT_GENERATION_MODEL": "gemini-3.6-flash",
                "AI_REPORT_TEMPERATURE": "0.2",
            },
            clear=True,
        ):
            clear_ai_settings_cache()
            config = get_generation_config(TASK_REPORT)
            self.assertIsNone(config.effective_temperature)
            self.assertIsNone(config.metadata()["temperature"])

    def test_chave_nao_aparece_na_representacao_ou_metadados(self):
        segredo = "chave-super-secreta"
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": segredo, "AI_CONFIG_DATABASE_ENABLED": "false"},
            clear=True,
        ):
            clear_ai_settings_cache()
            settings = get_ai_settings()
            self.assertNotIn(segredo, repr(settings))
            self.assertNotIn(segredo, str(get_generation_config(TASK_REPORT).metadata()))

    @patch("backend.app.ai_service.get_gemini_client")
    def test_servico_aplica_modelo_e_parametros_centrais(self, cliente_mock):
        with patch.dict(
            os.environ,
            {
                "AI_CONFIG_DATABASE_ENABLED": "false",
                "AI_REPORT_MODEL": "gemini-2.5-flash",
                "AI_REPORT_TEMPERATURE": "0.35",
            },
            clear=True,
        ):
            clear_ai_settings_cache()
            cliente = Mock()
            cliente.models.generate_content.return_value = Mock(text="resultado")
            cliente_mock.return_value = cliente

            resposta = generate_content(TASK_REPORT, "conteúdo")

            self.assertEqual(resposta.text, "resultado")
            chamada = cliente.models.generate_content.call_args.kwargs
            self.assertEqual(chamada["model"], "gemini-2.5-flash")
            self.assertEqual(chamada["config"].temperature, 0.35)

    def test_dimensao_invalida_e_rejeitada(self):
        with patch.dict(
            os.environ,
            {"AI_EMBEDDING_DIMENSIONS": "zero", "AI_CONFIG_DATABASE_ENABLED": "false"},
            clear=True,
        ):
            clear_ai_settings_cache()
            with self.assertRaisesRegex(RuntimeError, "número inteiro"):
                get_ai_settings()

    def test_reranking_pode_ser_configurado_pelo_ambiente(self):
        with patch.dict(
            os.environ,
            {
                "AI_CONFIG_DATABASE_ENABLED": "false",
                "AI_RERANKING_ENABLED": "false",
                "AI_RERANKING_CANDIDATE_LIMIT": "10",
                "AI_RERANKING_FINAL_LIMIT": "3",
                "AI_RERANKING_RRF_WEIGHT": "0.65",
            },
            clear=True,
        ):
            clear_ai_settings_cache()
            config = get_generation_config(TASK_RERANKING)

            self.assertFalse(config.enabled)
            self.assertEqual(config.candidate_limit, 10)
            self.assertEqual(config.final_limit, 3)
            self.assertEqual(config.rrf_weight, 0.65)
            self.assertEqual(config.metadata()["candidate_limit"], 10)
            self.assertEqual(config.metadata()["rrf_weight"], 0.65)

    def test_peso_rrf_fora_do_intervalo_e_rejeitado(self):
        with patch.dict(
            os.environ,
            {
                "AI_CONFIG_DATABASE_ENABLED": "false",
                "AI_RERANKING_RRF_WEIGHT": "1.2",
            },
            clear=True,
        ):
            clear_ai_settings_cache()
            with self.assertRaisesRegex(RuntimeError, "entre 0 e 1"):
                get_generation_config(TASK_RERANKING)

    def test_banco_sobrescreve_modelo_e_chave_sem_expor_segredo(self):
        modelos = {
            "report": {
                "task_type": "report",
                "provider_code": "google_gemini",
                "credential_id": "cred-1",
                "model_name": "modelo-do-banco",
                "parameters_jsonb": {"temperature": 0.4},
                "embedding_dimensions": None,
            },
            "embedding": {
                "task_type": "embedding",
                "provider_code": "google_gemini",
                "credential_id": "cred-1",
                "model_name": "embedding-do-banco",
                "parameters_jsonb": {},
                "embedding_dimensions": 768,
            },
        }
        credencial = {
            "id": "cred-1",
            "provider_code": "google_gemini",
            "encrypted_secret": "cifrado",
        }
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "chave-env", "AI_CONFIG_DATABASE_ENABLED": "true"},
            clear=True,
        ), patch(
            "backend.app.ai_config_repository.configuration_tables_available",
            return_value=True,
        ), patch(
            "backend.app.ai_config_repository.get_installation_model_settings",
            return_value=modelos,
        ), patch(
            "backend.app.ai_config_repository.get_installation_credential",
            return_value=credencial,
        ), patch(
            "backend.app.secret_store.decrypt_secret",
            return_value="chave-decifrada",
        ):
            clear_ai_settings_cache()
            settings = get_ai_settings()

            self.assertEqual(settings.api_key, "chave-decifrada")
            self.assertEqual(settings.credential_source, "encrypted_database")
            self.assertEqual(settings.generation[TASK_REPORT].model, "modelo-do-banco")
            self.assertEqual(settings.generation[TASK_REPORT].source, "database")
            self.assertEqual(settings.embedding.model, "embedding-do-banco")
            self.assertNotIn("chave-decifrada", repr(settings))

    def test_credencial_openai_cifrada_tem_precedencia_sobre_ambiente(self):
        credential = {
            "id": "cred-openai",
            "provider_code": "openai",
            "encrypted_secret": "segredo-cifrado",
        }
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "chave-env",
                "AI_CONFIG_DATABASE_ENABLED": "true",
            },
            clear=True,
        ), patch(
            "backend.app.ai_config_repository.configuration_tables_available",
            return_value=True,
        ), patch(
            "backend.app.ai_config_repository.get_installation_credential",
            return_value=credential,
        ), patch(
            "backend.app.secret_store.decrypt_secret",
            return_value="chave-openai-decifrada",
        ):
            clear_ai_settings_cache()
            try:
                self.assertEqual(
                    get_provider_api_key("openai"),
                    "chave-openai-decifrada",
                )
            finally:
                clear_ai_settings_cache()


if __name__ == "__main__":
    unittest.main()
