import os
import unittest
from unittest.mock import Mock, patch

from backend.app.ai_config import (
    TASK_EXTRACTION,
    TASK_REPORT,
    clear_ai_settings_cache,
    get_ai_settings,
    get_generation_config,
)
from backend.app.ai_service import generate_content


class AIConfigTests(unittest.TestCase):
    def tearDown(self):
        clear_ai_settings_cache()

    def test_modelo_padrao_e_override_por_funcao(self):
        ambiente = {
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
        with patch.dict(os.environ, {"GEMINI_API_KEY": segredo}, clear=True):
            clear_ai_settings_cache()
            settings = get_ai_settings()
            self.assertNotIn(segredo, repr(settings))
            self.assertNotIn(segredo, str(get_generation_config(TASK_REPORT).metadata()))

    @patch("backend.app.ai_service.get_gemini_client")
    def test_servico_aplica_modelo_e_parametros_centrais(self, cliente_mock):
        with patch.dict(
            os.environ,
            {
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
        with patch.dict(os.environ, {"AI_EMBEDDING_DIMENSIONS": "zero"}, clear=True):
            clear_ai_settings_cache()
            with self.assertRaisesRegex(RuntimeError, "número inteiro"):
                get_ai_settings()


if __name__ == "__main__":
    unittest.main()
