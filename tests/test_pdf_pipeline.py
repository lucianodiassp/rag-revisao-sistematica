import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.processamento.leitor_pdf import (
    criar_chunks,
    processar_pdfs,
    resumir_status_fluxo,
    sanitizar_texto_pdf,
)


class PdfPipelineStatusTests(unittest.TestCase):
    def test_sanitizacao_remove_nul_sem_alterar_acentuacao(self):
        texto = "Mét\x00odo e limita\x00ções"

        sanitizado = sanitizar_texto_pdf(texto)
        chunks = criar_chunks(sanitizado)

        self.assertEqual(sanitizado, "Método e limitações")
        self.assertNotIn("\x00", chunks[0])

    def test_funil_separa_indexacao_extracao_e_revisao(self):
        status = [
            {
                "pdf_associado": True,
                "indexado": True,
                "schema_version": "traceable-v1",
                "human_review_status": "pending",
            },
            {
                "pdf_associado": True,
                "indexado": True,
                "schema_version": None,
                "human_review_status": None,
            },
            {
                "pdf_associado": True,
                "indexado": False,
                "schema_version": None,
                "human_review_status": None,
            },
            {
                "pdf_associado": False,
                "indexado": False,
                "schema_version": None,
                "human_review_status": None,
            },
        ]

        resumo = resumir_status_fluxo(status)

        self.assertEqual(resumo["incluidos"], 4)
        self.assertEqual(resumo["pdfs_associados"], 3)
        self.assertEqual(resumo["indexados"], 2)
        self.assertEqual(resumo["extraidos"], 1)
        self.assertEqual(resumo["aguardando_indexacao"], 1)
        self.assertEqual(resumo["aguardando_extracao"], 1)
        self.assertEqual(resumo["sem_pdf"], 1)
        self.assertEqual(resumo["revisados"], 0)

    @patch("backend.processamento.leitor_pdf.generate_embedding")
    @patch("backend.processamento.leitor_pdf.criar_chunks_por_pagina")
    @patch("backend.processamento.leitor_pdf.extrair_paginas_pdf")
    @patch("backend.processamento.leitor_pdf.os.listdir")
    @patch("backend.processamento.leitor_pdf.os.path.exists")
    @patch("backend.processamento.leitor_pdf.get_embedding_config")
    @patch("backend.processamento.leitor_pdf.get_conexao")
    @patch("backend.processamento.leitor_pdf.resolver_project_id")
    def test_falha_de_embedding_e_reportada_sem_falso_sucesso(
        self,
        resolver_project_id,
        get_conexao,
        get_embedding_config,
        path_exists,
        listdir,
        extrair_paginas_pdf,
        criar_chunks_por_pagina,
        generate_embedding,
    ):
        resolver_project_id.return_value = "project-1"
        get_embedding_config.return_value = SimpleNamespace(
            provider="google_gemini",
            model="embedding-model",
            dimensions=768,
        )
        path_exists.return_value = True
        listdir.return_value = ["paper-1.pdf"]
        extrair_paginas_pdf.return_value = [{"page_number": 1, "text": "texto"}]
        criar_chunks_por_pagina.return_value = [
            {"chunk_text": "texto", "page_number": 1, "page_chunk_index": 1}
        ]
        generate_embedding.side_effect = RuntimeError("cota temporariamente indisponível")

        conexao = Mock()
        cursor = Mock()
        conexao.cursor.return_value = cursor
        cursor.fetchall.return_value = [("paper-1", "Artigo de teste")]
        cursor.fetchone.return_value = (0, 0, 0)
        get_conexao.return_value = conexao

        resumo = processar_pdfs("project-1")

        self.assertEqual(resumo["processados"], 0)
        self.assertEqual(resumo["falhas"], 1)
        self.assertEqual(resumo["resultados"][0]["status"], "failed")
        self.assertIn("cota", resumo["resultados"][0]["error"])
        conexao.rollback.assert_called_once()
        conexao.commit.assert_not_called()

    @patch("backend.processamento.leitor_pdf.os.listdir", return_value=["paper-1.pdf"])
    @patch("backend.processamento.leitor_pdf.os.path.exists", return_value=True)
    @patch("backend.processamento.leitor_pdf.get_embedding_config")
    @patch("backend.processamento.leitor_pdf.get_conexao")
    @patch("backend.processamento.leitor_pdf.resolver_project_id", return_value="project-1")
    def test_indice_compativel_e_identificado_como_ja_processado(
        self,
        resolver_project_id,
        get_conexao,
        get_embedding_config,
        path_exists,
        listdir,
    ):
        get_embedding_config.return_value = SimpleNamespace(
            provider="google_gemini",
            model="embedding-model",
            dimensions=768,
        )
        conexao = Mock()
        cursor = Mock()
        conexao.cursor.return_value = cursor
        cursor.fetchall.return_value = [("paper-1", "Artigo de teste")]
        cursor.fetchone.return_value = (2, 2, 2)
        get_conexao.return_value = conexao

        resumo = processar_pdfs("project-1")

        self.assertEqual(resumo["ignorados"], 1)
        self.assertEqual(resumo["falhas"], 0)
        self.assertEqual(resumo["resultados"][0]["status"], "already_indexed")


if __name__ == "__main__":
    unittest.main()
