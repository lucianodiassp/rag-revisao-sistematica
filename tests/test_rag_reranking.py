import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.agentes.agente_rag import (
    _buscar_contexto_hibrido_detalhado,
    buscar_contexto_hibrido,
    buscar_contexto_reranqueado,
    responder_com_rag,
)
from backend.app.ai_config import GenerationTaskConfig, TASK_RAG, TASK_RERANKING


class RagRerankingIntegrationTests(unittest.TestCase):
    @patch("backend.agentes.agente_rag.get_conexao")
    @patch("backend.agentes.agente_rag.get_embedding_config")
    @patch("backend.agentes.agente_rag.generate_embedding", return_value=[0.1, 0.2])
    def test_busca_detalhada_exige_pdf_e_propaga_pagina(
        self,
        _embedding,
        get_embedding_config,
        get_conexao,
    ):
        get_embedding_config.return_value = SimpleNamespace(
            model="embedding-test",
            dimensions=768,
        )
        cursor = Mock()
        cursor.fetchall.return_value = [
            (
                "chunk-1",
                "74000000-0000-0000-0000-000000000001",
                "Artigo de teste",
                "Trecho rastreável",
                9,
                0.031,
            )
        ]
        connection = Mock()
        connection.cursor.return_value = cursor
        get_conexao.return_value = connection

        resultado = _buscar_contexto_hibrido_detalhado(
            "Pergunta",
            "project-1",
            limite=5,
        )

        sql = cursor.execute.call_args.args[0]
        self.assertIn("metadata_jsonb->>'source_type' = 'pdf'", sql)
        self.assertIn("metadata_jsonb ? 'page_start'", sql)
        self.assertEqual(resultado[0]["page_number"], 9)
        self.assertEqual(resultado[0]["paper_title"], "Artigo de teste")

    @patch("backend.agentes.agente_rag._buscar_contexto_hibrido_detalhado")
    def test_interface_historica_da_busca_hibrida_e_preservada(self, busca):
        busca.return_value = [
            {
                "candidate_id": "c1",
                "chunk_id": "chunk-1",
                "paper_id": "paper-1",
                "page_number": 4,
                "text": "Trecho",
                "rrf_score": 0.03,
                "original_rank": 1,
            }
        ]

        resultado = buscar_contexto_hibrido("Pergunta", "project-1", limite=3)

        self.assertEqual(resultado, [("paper-1", "Trecho", 0.03)])

    @patch("backend.agentes.agente_rag.reranquear_candidatos")
    @patch("backend.agentes.agente_rag._buscar_contexto_hibrido_detalhado")
    @patch("backend.agentes.agente_rag.get_reranking_config")
    def test_busca_recupera_total_configurado_antes_do_reranking(
        self,
        get_config,
        busca,
        reranquear,
    ):
        config = GenerationTaskConfig(
            task=TASK_RERANKING,
            provider="google_gemini",
            model="modelo",
            temperature=0.0,
            candidate_limit=10,
            final_limit=3,
        )
        get_config.return_value = config
        busca.return_value = [{"candidate_id": "c1"}]
        reranquear.return_value = ([{"candidate_id": "c1"}], {"status": "success"})

        buscar_contexto_reranqueado("Pergunta", "project-1")

        self.assertEqual(busca.call_args.kwargs["limite"], 10)
        self.assertIs(reranquear.call_args.kwargs["config"], config)

    @patch("backend.agentes.agente_rag.get_generation_config")
    @patch("backend.agentes.agente_rag.log_interacao_agente")
    @patch("backend.agentes.agente_rag.generate_content")
    @patch("backend.agentes.agente_rag.buscar_contexto_reranqueado")
    def test_resposta_detalhada_preserva_scores_e_status(
        self,
        buscar,
        gerar,
        logar,
        get_config,
    ):
        paper_id = "74000000-0000-0000-0000-000000000002"
        evidencia = {
            "candidate_id": "c2",
            "chunk_id": "chunk-2",
            "paper_id": paper_id,
            "page_number": 7,
            "text": "Evidência direta.",
            "rrf_score": 0.029,
            "original_rank": 2,
            "rerank_rank": 1,
            "rerank_score": 97.0,
            "rerank_reason": "Resposta direta.",
        }
        trace = {"status": "success", "final_ranking": []}
        buscar.return_value = ([evidencia], trace)
        gerar.return_value = SimpleNamespace(
            text=f"Resposta fundamentada [{paper_id}, p. 7]."
        )
        get_config.return_value = GenerationTaskConfig(
            task=TASK_RAG,
            provider="google_gemini",
            model="modelo-rag",
            temperature=0.1,
        )

        resultado = responder_com_rag("Pergunta", "project-1", return_details=True)

        self.assertEqual(
            resultado["answer"],
            f"Resposta fundamentada [{paper_id}, p. 7].",
        )
        self.assertIs(resultado["reranking"], trace)
        output = logar.call_args.args[3]
        self.assertEqual(output["reranking_status"], "success")
        self.assertEqual(output["supporting_evidence"][0]["rerank_score"], 97.0)
        self.assertEqual(output["supporting_evidence"][0]["page_number"], 7)
        self.assertEqual(
            output["citation_validation"]["valid_citations"],
            [f"[{paper_id}, p. 7]"],
        )


if __name__ == "__main__":
    unittest.main()
