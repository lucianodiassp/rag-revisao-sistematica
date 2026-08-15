import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.app.ai_admin_service import inspect_gemini_key, save_ai_models
from backend.app.ai_config import GENERATION_TASKS, TASK_RERANKING


class AIAdminServiceTests(unittest.TestCase):
    @patch("backend.app.ai_admin_service.genai.Client")
    def test_listagem_classifica_modelos_sem_gerar_conteudo(self, client_class):
        cliente = Mock()
        cliente.models.list.return_value = [
            SimpleNamespace(
                name="models/gemini-modelo-texto",
                supported_actions=["generateContent", "countTokens"],
            ),
            SimpleNamespace(
                name="models/gemini-embedding-modelo",
                supported_actions=["embedContent"],
            ),
        ]
        client_class.return_value = cliente

        catalogo = inspect_gemini_key("chave-de-teste")

        self.assertEqual(catalogo["generative"], ["gemini-modelo-texto"])
        self.assertEqual(catalogo["embedding"], ["gemini-embedding-modelo"])
        cliente.models.generate_content.assert_not_called()

    @patch("backend.app.ai_admin_service.genai.Client")
    def test_erro_de_validacao_remove_chave_da_mensagem(self, client_class):
        segredo = "chave-que-nao-pode-vazar"
        cliente = Mock()
        cliente.models.list.side_effect = RuntimeError(f"Falha para {segredo}")
        client_class.return_value = cliente

        with self.assertRaises(RuntimeError) as contexto:
            inspect_gemini_key(segredo)

        self.assertNotIn(segredo, str(contexto.exception))
        self.assertIn("[REDACTED]", str(contexto.exception))

    @patch("backend.app.ai_admin_service.reload_ai_runtime")
    @patch("backend.app.ai_admin_service.save_installation_model_settings")
    @patch("backend.app.ai_admin_service.get_installation_credential", return_value=None)
    def test_salva_parametros_especificos_do_reranking(
        self,
        _credential,
        save_settings,
        _reload,
    ):
        generation = {
            task: {"model_name": "gemini-test", "temperature": 0.0}
            for task in GENERATION_TASKS
        }
        generation[TASK_RERANKING].update(
            {
                "enabled": True,
                "candidate_limit": 12,
                "final_limit": 4,
                "rrf_weight": 0.35,
            }
        )

        save_ai_models(generation, "embedding-test", 768)

        configuracoes = save_settings.call_args.args[2]
        self.assertEqual(configuracoes[TASK_RERANKING]["parameters"]["candidate_limit"], 12)
        self.assertEqual(configuracoes[TASK_RERANKING]["parameters"]["final_limit"], 4)
        self.assertEqual(configuracoes[TASK_RERANKING]["parameters"]["rrf_weight"], 0.35)
        self.assertTrue(configuracoes[TASK_RERANKING]["parameters"]["enabled"])

    def test_rejeita_limites_inconsistentes_do_reranking(self):
        generation = {
            task: {"model_name": "gemini-test", "temperature": 0.0}
            for task in GENERATION_TASKS
        }
        generation[TASK_RERANKING].update(
            {"enabled": True, "candidate_limit": 4, "final_limit": 5}
        )

        with self.assertRaisesRegex(ValueError, "não pode superar"):
            save_ai_models(generation, "embedding-test", 768)

    def test_rejeita_peso_rrf_fora_do_intervalo(self):
        generation = {
            task: {"model_name": "gemini-test", "temperature": 0.0}
            for task in GENERATION_TASKS
        }
        generation[TASK_RERANKING].update(
            {
                "enabled": True,
                "candidate_limit": 12,
                "final_limit": 4,
                "rrf_weight": -0.1,
            }
        )

        with self.assertRaisesRegex(ValueError, "peso RRF"):
            save_ai_models(generation, "embedding-test", 768)


if __name__ == "__main__":
    unittest.main()
