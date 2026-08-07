import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.app.ai_admin_service import inspect_gemini_key


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


if __name__ == "__main__":
    unittest.main()
