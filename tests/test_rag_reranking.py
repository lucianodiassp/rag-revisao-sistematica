import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.agentes.agente_rag import (
    _buscar_contexto_hibrido_detalhado,
    buscar_contexto_hibrido,
    buscar_contexto_reranqueado,
    responder_com_rag,
)
from backend.app.rag_citations import RESPOSTA_SEM_CONTEXTO
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

    @patch("backend.agentes.agente_rag.get_generation_config")
    @patch("backend.agentes.agente_rag.log_interacao_agente")
    @patch("backend.agentes.agente_rag.generate_content")
    @patch("backend.agentes.agente_rag.buscar_contexto_reranqueado")
    def test_reavalia_recusa_quando_reranking_indica_evidencia_forte(
        self,
        buscar,
        gerar,
        logar,
        get_config,
    ):
        paper_id = "74000000-0000-0000-0000-000000000003"
        evidencia = {
            "candidate_id": "c1",
            "chunk_id": "chunk-1",
            "paper_id": paper_id,
            "paper_title": "Artigo",
            "page_number": 5,
            "text": "A restrição é garantida por uma máscara de viabilidade.",
            "rrf_score": 0.03,
            "original_rank": 1,
            "rerank_rank": 1,
            "model_rank": 1,
            "rerank_score": 95.0,
            "rerank_reason": "Evidência direta.",
        }
        buscar.return_value = ([evidencia], {"status": "success", "final_ranking": []})
        gerar.side_effect = [
            SimpleNamespace(text=RESPOSTA_SEM_CONTEXTO),
            SimpleNamespace(
                text=f"A máscara garante a viabilidade [{paper_id}, p. 5]."
            ),
        ]
        get_config.return_value = GenerationTaskConfig(
            task=TASK_RAG,
            provider="google_gemini",
            model="modelo-rag",
            temperature=0.1,
        )

        resultado = responder_com_rag("Como a viabilidade é garantida?", "project-1", True)

        self.assertEqual(gerar.call_count, 2)
        self.assertTrue(resultado["generation"]["refusal_reconsidered"])
        self.assertTrue(resultado["generation"]["refusal_recovered"])
        self.assertIn(f"[{paper_id}, p. 5]", resultado["answer"])
        self.assertTrue(logar.call_args.args[3]["generation"]["refusal_recovered"])

    @patch("backend.agentes.agente_rag.get_generation_config")
    @patch("backend.agentes.agente_rag.log_interacao_agente")
    @patch("backend.agentes.agente_rag.generate_content")
    @patch("backend.agentes.agente_rag.buscar_contexto_reranqueado")
    def test_mantem_recusa_sem_segunda_chamada_quando_scores_sao_baixos(
        self,
        buscar,
        gerar,
        _logar,
        get_config,
    ):
        evidencia = {
            "candidate_id": "c1",
            "chunk_id": "chunk-1",
            "paper_id": "paper-1",
            "paper_title": "Artigo",
            "page_number": 2,
            "text": "Trecho apenas tangencial.",
            "rrf_score": 0.03,
            "original_rank": 1,
            "rerank_rank": 1,
            "model_rank": 1,
            "rerank_score": 20.0,
            "rerank_reason": "Baixa relação.",
        }
        buscar.return_value = ([evidencia], {"status": "success", "final_ranking": []})
        gerar.return_value = SimpleNamespace(text=RESPOSTA_SEM_CONTEXTO)
        get_config.return_value = GenerationTaskConfig(
            task=TASK_RAG,
            provider="google_gemini",
            model="modelo-rag",
            temperature=0.1,
        )

        resultado = responder_com_rag("Pergunta fora do corpus", "project-1", True)

        gerar.assert_called_once()
        self.assertFalse(resultado["generation"]["refusal_reconsidered"])
        self.assertTrue(resultado["generation"]["final_refused"])

    @patch("backend.agentes.agente_rag.get_generation_config")
    @patch("backend.agentes.agente_rag.log_interacao_agente")
    @patch("backend.agentes.agente_rag.generate_content")
    @patch("backend.agentes.agente_rag.buscar_contexto_reranqueado")
    def test_reavalia_recusa_quando_fallback_nao_possui_score_da_ia(
        self,
        buscar,
        gerar,
        _logar,
        get_config,
    ):
        paper_id = "74000000-0000-0000-0000-000000000004"
        evidencia = {
            "candidate_id": "c1",
            "chunk_id": "chunk-1",
            "paper_id": paper_id,
            "paper_title": "Artigo",
            "page_number": 1,
            "text": "A limitação decorre da representação exclusivamente em grafos.",
            "rrf_score": 0.03,
            "original_rank": 1,
            "rerank_rank": 1,
            "rerank_score": None,
            "rerank_reason": "Ordem original do RRF utilizada.",
        }
        buscar.return_value = (
            [evidencia],
            {"status": "fallback_rrf", "final_ranking": [], "error": "erro"},
        )
        gerar.side_effect = [
            SimpleNamespace(text=RESPOSTA_SEM_CONTEXTO),
            SimpleNamespace(text=f"A limitação é estrutural [{paper_id}, p. 1]."),
        ]
        get_config.return_value = GenerationTaskConfig(
            task=TASK_RAG,
            provider="google_gemini",
            model="modelo-rag",
            temperature=0.1,
        )

        resultado = responder_com_rag("Qual é a limitação?", "project-1", True)

        self.assertEqual(gerar.call_count, 2)
        self.assertEqual(
            resultado["generation"]["reconsideration_reason"],
            "unscored_ranking",
        )
        self.assertTrue(resultado["generation"]["refusal_recovered"])


if __name__ == "__main__":
    unittest.main()
