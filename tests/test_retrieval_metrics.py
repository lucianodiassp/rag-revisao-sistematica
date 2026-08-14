import unittest

from backend.app.retrieval_metrics import evaluate_ranking


class RetrievalMetricsTests(unittest.TestCase):
    def test_calcula_metricas_com_julgamento_por_pagina_e_artigo(self):
        judgments = [
            {"paper_id": "paper-1", "page_number": 7, "relevance_grade": 3},
            {"paper_id": "paper-2", "page_number": None, "relevance_grade": 2},
        ]
        ranking = [
            {"paper_id": "irrelevant", "page_number": 1},
            {"paper_id": "paper-1", "page_number": 7},
            {"paper_id": "paper-2", "page_number": 99},
        ]

        metrics = evaluate_ranking(ranking, judgments, k_values=(1, 3))

        self.assertEqual(metrics["precision_at_1"], 0.0)
        self.assertEqual(metrics["recall_at_1"], 0.0)
        self.assertEqual(metrics["hit_rate_at_1"], 0.0)
        self.assertEqual(metrics["reciprocal_rank"], 0.5)
        self.assertEqual(metrics["precision_at_3"], round(2 / 3, 6))
        self.assertEqual(metrics["recall_at_3"], 1.0)
        self.assertGreater(metrics["ndcg_at_3"], 0.0)
        self.assertLess(metrics["ndcg_at_3"], 1.0)

    def test_nao_conta_o_mesmo_julgamento_duas_vezes(self):
        metrics = evaluate_ranking(
            [
                {"paper_id": "paper-1", "page_number": 7},
                {"paper_id": "paper-1", "page_number": 7},
            ],
            [{"paper_id": "paper-1", "page_number": 7, "relevance_grade": 3}],
            k_values=(2,),
        )
        self.assertEqual(metrics["precision_at_2"], 0.5)
        self.assertEqual(metrics["recall_at_2"], 1.0)

    def test_exige_julgamento_humano(self):
        with self.assertRaisesRegex(ValueError, "julgamento"):
            evaluate_ranking([], [])


if __name__ == "__main__":
    unittest.main()
