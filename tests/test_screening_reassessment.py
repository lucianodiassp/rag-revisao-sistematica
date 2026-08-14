import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from backend.app.screening_reassessment import (
    ACTION_EXCLUDE,
    ACTION_RETURN_TO_SCREENING,
    reassess_included_paper,
)


def _connection_factory(previous_decision="Incluir", previous_justification="Aceito"):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    connection.cursor.return_value = cursor
    cursor.fetchone.side_effect = [
        ("decision-1", previous_decision, previous_justification, "Artigo de teste"),
        ("reassessment-1", datetime(2026, 8, 13, tzinfo=timezone.utc)),
    ]
    return Mock(return_value=connection), cursor


class ScreeningReassessmentTests(unittest.TestCase):
    def test_devolve_artigo_para_triagem_e_preserva_historico(self):
        factory, cursor = _connection_factory()

        resultado = reassess_included_paper(
            project_id="project-1",
            paper_id="paper-1",
            action=ACTION_RETURN_TO_SCREENING,
            reason_code="restricted_access",
            reason="Acesso apenas mediante pagamento.",
            connection_factory=factory,
        )

        update_sql, update_params = cursor.execute.call_args_list[1].args
        insert_sql, insert_params = cursor.execute.call_args_list[2].args
        self.assertIn("human_decision = NULL", update_sql)
        self.assertEqual(update_params, ("decision-1",))
        self.assertIn("INSERT INTO screening_reassessments", insert_sql)
        self.assertEqual(insert_params[6], "Incluir")
        self.assertEqual(insert_params[7], "Aceito")
        self.assertIsNone(insert_params[8])
        self.assertIsNone(resultado["resulting_human_decision"])

    def test_exclui_artigo_com_justificativa(self):
        factory, cursor = _connection_factory(previous_justification=None)

        resultado = reassess_included_paper(
            project_id="project-1",
            paper_id="paper-1",
            action=ACTION_EXCLUDE,
            reason_code="pdf_not_found",
            reason="O PDF não foi localizado em fontes legais.",
            connection_factory=factory,
        )

        update_sql, update_params = cursor.execute.call_args_list[1].args
        self.assertIn("human_decision = 'Excluir'", update_sql)
        self.assertEqual(
            update_params,
            ("O PDF não foi localizado em fontes legais.", "pdf_not_found", "decision-1"),
        )
        self.assertEqual(resultado["resulting_human_decision"], "Excluir")

    def test_exige_justificativa_e_valida_categoria(self):
        with self.assertRaisesRegex(ValueError, "pelo menos 5"):
            reassess_included_paper(
                "project-1",
                "paper-1",
                ACTION_EXCLUDE,
                "restricted_access",
                "não",
                connection_factory=Mock(),
            )
        with self.assertRaisesRegex(ValueError, "Categoria"):
            reassess_included_paper(
                "project-1",
                "paper-1",
                ACTION_EXCLUDE,
                "categoria-invalida",
                "Justificativa válida",
                connection_factory=Mock(),
            )

    def test_rejeita_artigo_que_nao_esta_incluido(self):
        factory, _ = _connection_factory(previous_decision="Excluir")

        with self.assertRaisesRegex(ValueError, "atualmente incluídos"):
            reassess_included_paper(
                "project-1",
                "paper-1",
                ACTION_RETURN_TO_SCREENING,
                "restricted_access",
                "Acesso restrito confirmado.",
                connection_factory=factory,
            )


if __name__ == "__main__":
    unittest.main()
