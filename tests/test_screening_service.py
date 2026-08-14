import unittest
from unittest.mock import Mock

from backend.app.screening_service import save_human_screening_decision


def _connection_factory(returned_id="decision-1"):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.return_value = (returned_id,) if returned_id else None
    connection.cursor.return_value = cursor
    return Mock(return_value=connection), cursor


class ScreeningServiceTests(unittest.TestCase):
    def test_exclusao_exige_categoria_e_justificativa(self):
        with self.assertRaisesRegex(ValueError, "categoria"):
            save_human_screening_decision(
                "project-1", "paper-1", "Excluir", "Motivo suficiente", None,
                connection_factory=Mock(),
            )
        with self.assertRaisesRegex(ValueError, "5 caracteres"):
            save_human_screening_decision(
                "project-1", "paper-1", "Excluir", "não", "population_mismatch",
                connection_factory=Mock(),
            )

    def test_salva_exclusao_estruturada_no_projeto(self):
        factory, cursor = _connection_factory()
        result = save_human_screening_decision(
            "project-1",
            "paper-1",
            "Excluir",
            "A população estudada está fora do protocolo.",
            "population_mismatch",
            connection_factory=factory,
        )
        sql, params = cursor.execute.call_args.args
        self.assertIn("p.project_id = %s", sql)
        self.assertEqual(params[2], "population_mismatch")
        self.assertEqual(params[-1], "project-1")
        self.assertEqual(result["exclusion_reason_code"], "population_mismatch")

    def test_inclusao_limpa_motivo_de_exclusao(self):
        factory, cursor = _connection_factory()
        result = save_human_screening_decision(
            "project-1",
            "paper-1",
            "Incluir",
            "Atende aos critérios.",
            "population_mismatch",
            connection_factory=factory,
        )
        _, params = cursor.execute.call_args.args
        self.assertIsNone(params[2])
        self.assertIsNone(result["exclusion_reason_code"])

    def test_rejeita_artigo_fora_do_projeto(self):
        factory, _ = _connection_factory(returned_id=None)
        with self.assertRaisesRegex(ValueError, "projeto ativo"):
            save_human_screening_decision(
                "project-1", "paper-1", "Incluir", connection_factory=factory
            )


if __name__ == "__main__":
    unittest.main()
