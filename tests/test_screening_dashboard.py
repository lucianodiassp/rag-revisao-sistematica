import unittest
from unittest.mock import Mock

from backend.agentes.agente_triagem import buscar_artigos_sem_analise
from backend.app.screening_service import (
    UNUSABLE_ABSTRACTS,
    get_next_pending_human_screening,
    get_screening_summary,
)


def _connection_factory(fetchone=None, fetchall=None):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.return_value = fetchone
    cursor.fetchall.return_value = fetchall or []
    connection.cursor.return_value = cursor
    return Mock(return_value=connection), cursor


class ScreeningDashboardTests(unittest.TestCase):
    def test_resumo_fecha_todos_os_estados_do_projeto(self):
        factory, cursor = _connection_factory(
            fetchone=(12, 2, 1, 3, 3, 1, 2, 0, 4)
        )

        summary = get_screening_summary("project-1", connection_factory=factory)

        self.assertEqual(summary["total_papers"], 12)
        self.assertEqual(summary["awaiting_ai"], 2)
        self.assertEqual(summary["without_usable_abstract"], 1)
        self.assertEqual(summary["awaiting_human"], 3)
        self.assertEqual(summary["final_decisions"], 4)
        self.assertEqual(summary["human_reviewed"], 6)
        self.assertEqual(summary["accounted_papers"], 12)
        self.assertEqual(summary["awaiting_deduplication"], 4)
        self.assertFalse(summary["is_complete"])

        sql, params = cursor.execute.call_args.args
        self.assertIn("scoped_paper.project_id = %s", sql)
        self.assertIn("p.project_id = %s", sql)
        self.assertIn("dd.project_id = %s", sql)
        self.assertEqual(params[0], "project-1")
        self.assertEqual(params[-2:], ("project-1", "project-1"))
        for abstract in UNUSABLE_ABSTRACTS:
            self.assertEqual(params.count(abstract), 2)

    def test_resumo_so_conclui_com_decisoes_finais_e_sem_deduplicacao(self):
        factory, _ = _connection_factory(
            fetchone=(5, 0, 0, 0, 4, 1, 0, 0, 0)
        )

        summary = get_screening_summary("project-1", connection_factory=factory)

        self.assertTrue(summary["is_complete"])
        self.assertEqual(summary["accounted_papers"], summary["total_papers"])

    def test_proximo_parecer_humano_preserva_isolamento_e_reavaliacao(self):
        expected = (
            "paper-1",
            "Título",
            "Resumo",
            "Incluir",
            {"confidence": 0.9},
            "restricted_access",
            "Acesso restrito",
            None,
        )
        factory, cursor = _connection_factory(fetchone=expected)

        result = get_next_pending_human_screening(
            "project-1", connection_factory=factory
        )

        self.assertEqual(result, expected)
        sql, params = cursor.execute.call_args.args
        self.assertIn("d.project_id = %s", sql)
        self.assertIn("s.human_decision IS NULL", sql)
        self.assertIn("sr.project_id = d.project_id", sql)
        self.assertEqual(params, ("project-1",))

    def test_fila_da_ia_usa_not_exists_e_exclui_resumos_inadequados(self):
        papers = [("paper-1", "Título", "Resumo válido")]
        factory, cursor = _connection_factory(fetchall=papers)

        result = buscar_artigos_sem_analise(
            "project-1", connection_factory=factory
        )

        self.assertEqual(result, papers)
        sql, params = cursor.execute.call_args.args
        self.assertIn("NOT EXISTS", sql)
        self.assertNotIn("NOT IN (SELECT paper_id", sql)
        self.assertIn("d.project_id = %s", sql)
        self.assertEqual(params, ("project-1", *UNUSABLE_ABSTRACTS))

    def test_resumo_rejeita_projeto_vazio(self):
        with self.assertRaisesRegex(ValueError, "Projeto"):
            get_screening_summary("", connection_factory=Mock())


if __name__ == "__main__":
    unittest.main()
