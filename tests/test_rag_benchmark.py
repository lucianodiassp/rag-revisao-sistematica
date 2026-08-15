import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.rag_benchmark import (
    benchmark_to_csv,
    is_transient_ai_error,
    run_rag_benchmark,
    validate_golden_set,
)


GOLDEN = {
    "project_id": "project-1",
    "version": 4,
    "queries": [
        {
            "id": "q1",
            "question": "Qual método foi utilizado?",
            "expected_refusal": False,
            "notes": None,
            "relevances": [
                {
                    "id": "r1",
                    "paper_id": "paper-1",
                    "paper_title": "Artigo relevante",
                    "page_number": 7,
                    "relevance_grade": 3,
                    "notes": None,
                }
            ],
        },
        {
            "id": "q2",
            "question": "Qual é a capital de Marte?",
            "expected_refusal": True,
            "notes": None,
            "relevances": [],
        },
    ],
}


def _runner(question, project_id, return_details=False):
    if "Marte" in question:
        return {
            "answer": "Não tenho dados suficientes nos artigos recolhidos para responder.",
            "reranking": {
                "status": "no_candidates",
                "initial_ranking": [],
                "reranked_ranking": [],
                "final_ranking": [],
            },
            "citation_validation": {},
        }
    irrelevant = {
        "chunk_id": "c0",
        "paper_id": "paper-0",
        "page_number": 2,
        "rrf_score": 0.03,
        "original_rank": 1,
    }
    relevant = {
        "chunk_id": "c1",
        "paper_id": "paper-1",
        "page_number": 7,
        "rrf_score": 0.02,
        "original_rank": 2,
        "rerank_rank": 1,
        "rerank_score": 99,
    }
    return {
        "answer": "Resposta fundamentada [paper-1, p. 7].",
        "reranking": {
            "status": "success",
            "initial_ranking": [irrelevant, relevant],
            "reranked_ranking": [relevant, irrelevant],
            "final_ranking": [relevant],
        },
        "citation_validation": {
            "valid_citations": ["[paper-1, p. 7]"],
            "invalid_citations_removed": [],
            "source_citations_appended": [],
        },
    }


class RagBenchmarkTests(unittest.TestCase):
    def test_identifica_erros_transitorios_sem_confundir_erro_funcional(self):
        class TooManyRequestsError(RuntimeError):
            status_code = 429

        self.assertTrue(is_transient_ai_error(TooManyRequestsError("limite")))
        self.assertTrue(
            is_transient_ai_error(RuntimeError("503 UNAVAILABLE: high demand"))
        )
        self.assertFalse(is_transient_ai_error(ValueError("JSON inválido")))

    def test_valida_perguntas_sem_fontes(self):
        invalid = {
            "queries": [
                {
                    "question": "Pergunta respondível",
                    "expected_refusal": False,
                    "relevances": [],
                }
            ]
        }
        self.assertTrue(validate_golden_set(invalid))

    @patch("backend.app.rag_benchmark.get_reranking_config")
    @patch("backend.app.rag_benchmark.get_generation_config")
    @patch("backend.app.rag_benchmark.get_embedding_config")
    @patch("backend.app.rag_benchmark.salvar_execucao_avaliacao", return_value="run-1")
    @patch("backend.app.rag_benchmark.list_golden_queries", return_value=GOLDEN)
    def test_compara_rrf_reranking_recusa_e_citacoes(
        self,
        _golden,
        save_run,
        embedding_config,
        rag_config,
        reranking_config,
    ):
        embedding_config.return_value = SimpleNamespace(metadata=lambda: {"model": "embed"})
        rag_config.return_value = SimpleNamespace(metadata=lambda: {"model": "rag"})
        reranking_config.return_value = SimpleNamespace(metadata=lambda: {"model": "rerank"})

        run = run_rag_benchmark("project-1", rag_runner=_runner)
        summary = run["metrics"]["summary"]

        self.assertEqual(summary["rrf"]["reciprocal_rank"], 0.5)
        self.assertEqual(summary["model_reranked"]["reciprocal_rank"], 1.0)
        self.assertEqual(summary["reranked"]["reciprocal_rank"], 1.0)
        self.assertEqual(
            summary["reranking_calibration"]["recommended_rrf_weight"], 0.0
        )
        self.assertEqual(summary["reranking_calibration"]["status"], "exploratory")
        self.assertEqual(summary["correct_refusal_rate"], 1.0)
        self.assertEqual(summary["false_refusal_rate"], 0.0)
        self.assertEqual(summary["citation_validity"], 1.0)
        self.assertEqual(summary["citation_compliance_rate"], 1.0)
        self.assertEqual(run["params"]["golden_set_version"], 4)
        self.assertIn("Qual método foi utilizado?", benchmark_to_csv(run))
        self.assertIn("Fusão configurada", benchmark_to_csv(run))
        self.assertEqual(summary["failed_query_count"], 0)
        save_run.assert_called_once()

    @patch("backend.app.rag_benchmark.get_reranking_config")
    @patch("backend.app.rag_benchmark.get_generation_config")
    @patch("backend.app.rag_benchmark.get_embedding_config")
    @patch("backend.app.rag_benchmark.salvar_execucao_avaliacao", return_value="run-2")
    @patch("backend.app.rag_benchmark.list_golden_queries", return_value=GOLDEN)
    def test_repete_erro_transitorio_com_espera_exponencial(
        self,
        _golden,
        _save_run,
        embedding_config,
        rag_config,
        reranking_config,
    ):
        embedding_config.return_value = SimpleNamespace(metadata=lambda: {"model": "embed"})
        rag_config.return_value = SimpleNamespace(metadata=lambda: {"model": "rag"})
        reranking_config.return_value = SimpleNamespace(metadata=lambda: {"model": "rerank"})
        attempts = {}
        sleeps = []

        def flaky_runner(question, project_id, return_details=False):
            attempts[question] = attempts.get(question, 0) + 1
            if "método" in question and attempts[question] < 3:
                raise RuntimeError("503 UNAVAILABLE: high demand")
            return _runner(question, project_id, return_details)

        run = run_rag_benchmark(
            "project-1",
            rag_runner=flaky_runner,
            retry_max_attempts=4,
            retry_base_delay_seconds=1.5,
            retry_max_delay_seconds=2.0,
            sleep_func=sleeps.append,
        )

        first = run["metrics"]["results"][0]
        summary = run["metrics"]["summary"]
        self.assertEqual(first["execution_status"], "success_after_retry")
        self.assertEqual(first["execution_attempts"], 3)
        self.assertEqual(first["retry_count"], 2)
        self.assertEqual(sleeps, [1.5, 2.0])
        self.assertEqual(summary["retried_query_count"], 1)
        self.assertEqual(summary["total_retry_count"], 2)
        self.assertEqual(summary["failed_query_count"], 0)
        self.assertEqual(run["params"]["retry_policy"]["backoff"], "exponential")

    @patch("backend.app.rag_benchmark.get_reranking_config")
    @patch("backend.app.rag_benchmark.get_generation_config")
    @patch("backend.app.rag_benchmark.get_embedding_config")
    @patch("backend.app.rag_benchmark.salvar_execucao_avaliacao", return_value="run-3")
    @patch("backend.app.rag_benchmark.list_golden_queries", return_value=GOLDEN)
    def test_preserva_resultados_quando_uma_pergunta_esgota_tentativas(
        self,
        _golden,
        save_run,
        embedding_config,
        rag_config,
        reranking_config,
    ):
        embedding_config.return_value = SimpleNamespace(metadata=lambda: {"model": "embed"})
        rag_config.return_value = SimpleNamespace(metadata=lambda: {"model": "rag"})
        reranking_config.return_value = SimpleNamespace(metadata=lambda: {"model": "rerank"})

        def unavailable_runner(question, project_id, return_details=False):
            if "método" in question:
                raise RuntimeError("503 UNAVAILABLE api_key=segredo-de-teste")
            return _runner(question, project_id, return_details)

        run = run_rag_benchmark(
            "project-1",
            rag_runner=unavailable_runner,
            retry_max_attempts=3,
            retry_base_delay_seconds=0,
            sleep_func=lambda _delay: None,
        )

        first, second = run["metrics"]["results"]
        summary = run["metrics"]["summary"]
        self.assertEqual(first["execution_status"], "failed_transient")
        self.assertEqual(first["execution_attempts"], 3)
        self.assertIn("503", first["execution_error"])
        self.assertNotIn("segredo-de-teste", first["execution_error"])
        self.assertIn("[REDACTED]", first["execution_error"])
        self.assertEqual(second["execution_status"], "success")
        self.assertEqual(summary["failed_query_count"], 1)
        self.assertEqual(summary["successful_query_count"], 1)
        self.assertEqual(summary["evaluated_answerable_query_count"], 0)
        self.assertEqual(summary["evaluated_refusal_query_count"], 1)
        self.assertEqual(summary["correct_refusal_rate"], 1.0)
        self.assertTrue(summary["interpretation"]["warnings"])
        self.assertIn("status_execucao", benchmark_to_csv(run))
        save_run.assert_called_once()

    @patch("backend.app.rag_benchmark.salvar_execucao_avaliacao")
    @patch("backend.app.rag_benchmark.list_golden_queries", return_value=GOLDEN)
    def test_erro_nao_transitorio_continua_sendo_exposto(self, _golden, save_run):
        def invalid_runner(_question, _project_id, return_details=False):
            raise ValueError("Resposta interna inválida")

        with self.assertRaisesRegex(ValueError, "Resposta interna inválida"):
            run_rag_benchmark(
                "project-1",
                rag_runner=invalid_runner,
                sleep_func=lambda _delay: None,
            )
        save_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
