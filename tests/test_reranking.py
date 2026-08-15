import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.app.ai_config import GenerationTaskConfig, TASK_RERANKING
from backend.app.reranking import (
    STATUS_DISABLED,
    STATUS_FALLBACK,
    STATUS_SUCCESS,
    reranquear_candidatos,
)


def _config(enabled=True, candidate_limit=3, final_limit=2, rrf_weight=0.0):
    return GenerationTaskConfig(
        task=TASK_RERANKING,
        provider="google_gemini",
        model="gemini-reranker-test",
        temperature=0.0,
        source="test",
        enabled=enabled,
        candidate_limit=candidate_limit,
        final_limit=final_limit,
        rrf_weight=rrf_weight,
    )


def _candidatos():
    return [
        {
            "candidate_id": "c1",
            "chunk_id": "chunk-1",
            "paper_id": "paper-1",
            "page_number": 3,
            "text": "Trecho apenas tangencialmente relacionado.",
            "rrf_score": 0.032,
            "original_rank": 1,
        },
        {
            "candidate_id": "c2",
            "chunk_id": "chunk-2",
            "paper_id": "paper-2",
            "page_number": 7,
            "text": "Trecho que responde diretamente à pergunta.",
            "rrf_score": 0.029,
            "original_rank": 2,
        },
        {
            "candidate_id": "c3",
            "chunk_id": "chunk-3",
            "paper_id": "paper-3",
            "page_number": 11,
            "text": "Trecho sem evidência relevante.",
            "rrf_score": 0.025,
            "original_rank": 3,
        },
    ]


class RerankingTests(unittest.TestCase):
    def test_reordena_candidatos_e_registra_ranking_antes_e_depois(self):
        resposta = {
            "ranking": [
                {"candidate_id": "c2", "relevance_score": 96, "reason": "Resposta direta."},
                {"candidate_id": "c1", "relevance_score": 65, "reason": "Relação parcial."},
                {"candidate_id": "c3", "relevance_score": 10, "reason": "Irrelevante."},
            ]
        }
        generator = Mock(return_value=SimpleNamespace(text=json.dumps(resposta)))
        logger = Mock()

        selecionados, trace = reranquear_candidatos(
            "Qual trecho responde diretamente?",
            _candidatos(),
            "project-1",
            config=_config(),
            generator=generator,
            logger=logger,
        )

        self.assertEqual(trace["status"], STATUS_SUCCESS)
        self.assertEqual([item["candidate_id"] for item in selecionados], ["c2", "c1"])
        self.assertEqual(trace["model_ranking"][0]["candidate_id"], "c2")
        self.assertEqual(selecionados[0]["original_rank"], 2)
        self.assertEqual(selecionados[0]["model_rank"], 1)
        self.assertEqual(selecionados[0]["rerank_rank"], 1)
        self.assertEqual(selecionados[0]["rerank_score"], 96.0)
        self.assertIsNotNone(selecionados[0]["fusion_score"])
        self.assertEqual(len(trace["initial_ranking"]), 3)
        self.assertEqual(len(trace["reranked_ranking"]), 3)
        self.assertEqual(trace["reranked_ranking"][0]["candidate_id"], "c2")
        self.assertEqual(len(trace["final_ranking"]), 2)
        self.assertEqual(logger.call_args.args[1], "reranking_agent")
        self.assertEqual(logger.call_args.args[3]["status"], STATUS_SUCCESS)

    def test_peso_rrf_protege_a_ordem_original_sem_descartar_avaliacao_da_ia(self):
        resposta = {
            "ranking": [
                {"candidate_id": "c2", "relevance_score": 96, "reason": "Resposta direta."},
                {"candidate_id": "c1", "relevance_score": 65, "reason": "Relação parcial."},
                {"candidate_id": "c3", "relevance_score": 10, "reason": "Irrelevante."},
            ]
        }

        selecionados, trace = reranquear_candidatos(
            "Pergunta",
            _candidatos(),
            "project-1",
            config=_config(rrf_weight=0.8),
            generator=Mock(return_value=SimpleNamespace(text=json.dumps(resposta))),
            logger=Mock(),
        )

        self.assertEqual([item["candidate_id"] for item in selecionados], ["c1", "c2"])
        self.assertEqual(trace["model_ranking"][0]["candidate_id"], "c2")
        self.assertEqual(selecionados[0]["model_rank"], 2)
        self.assertEqual(selecionados[0]["rerank_rank"], 1)
        self.assertEqual(trace["configuration"]["rrf_weight"], 0.8)

    def test_falha_do_modelo_retorna_ordem_rrf_e_registra_fallback(self):
        generator = Mock(side_effect=RuntimeError("modelo indisponível"))
        logger = Mock()

        selecionados, trace = reranquear_candidatos(
            "Pergunta",
            _candidatos(),
            "project-1",
            config=_config(),
            generator=generator,
            logger=logger,
        )

        self.assertEqual(trace["status"], STATUS_FALLBACK)
        self.assertEqual([item["candidate_id"] for item in selecionados], ["c1", "c2"])
        self.assertTrue(all(item["rerank_score"] is None for item in selecionados))
        self.assertIn("RuntimeError", trace["error"])
        self.assertEqual(logger.call_args.args[3]["status"], STATUS_FALLBACK)

    def test_configuracao_desativada_nao_chama_modelo(self):
        generator = Mock()
        logger = Mock()

        selecionados, trace = reranquear_candidatos(
            "Pergunta",
            _candidatos(),
            "project-1",
            config=_config(enabled=False),
            generator=generator,
            logger=logger,
        )

        self.assertEqual(trace["status"], STATUS_DISABLED)
        self.assertEqual([item["candidate_id"] for item in selecionados], ["c1", "c2"])
        generator.assert_not_called()
        logger.assert_called_once()

    def test_resposta_invalida_aciona_fallback(self):
        selecionados, trace = reranquear_candidatos(
            "Pergunta",
            _candidatos(),
            "project-1",
            config=_config(),
            generator=Mock(return_value=SimpleNamespace(text='{"sem_ranking": []}')),
            logger=Mock(),
        )

        self.assertEqual(trace["status"], STATUS_FALLBACK)
        self.assertEqual(selecionados[0]["candidate_id"], "c1")


if __name__ == "__main__":
    unittest.main()
