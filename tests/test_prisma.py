import json
import unittest
from unittest.mock import Mock

from backend.app.prisma import (
    calcular_fluxo_prisma,
    gerar_prisma_svg,
    prisma_para_csv,
    prisma_para_json,
)


def _prisma_connection_factory():
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.side_effect = [
        ("Projeto de teste", 3),
        (13, 10, 1, 3, 3, 2),
        (6, 1),
    ]
    cursor.fetchall.side_effect = [
        [("openalex", 8), ("semantic_scholar", 5)],
        [
            ("Incluir", None, None, None, 4),
            ("Excluir", "population_mismatch", None, None, 2),
            ("Excluir", "pdf_not_found", "exclude", "pdf_not_found", 1),
            ("Talvez", None, None, None, 1),
            (None, None, "return_to_screening", "restricted_access", 1),
        ],
    ]
    connection.cursor.return_value = cursor
    return Mock(return_value=connection)


class PrismaTests(unittest.TestCase):
    def test_calcula_etapas_sem_ia_e_fecha_as_contagens(self):
        snapshot = calcular_fluxo_prisma(
            "project-1", connection_factory=_prisma_connection_factory()
        )
        metrics = snapshot["metrics"]
        self.assertEqual(metrics["records_identified"], 13)
        self.assertEqual(metrics["duplicates_removed"], 2)
        self.assertEqual(metrics["records_after_deduplication"], 10)
        self.assertEqual(metrics["screening_completed"], 7)
        self.assertEqual(metrics["screening_pending"], 2)
        self.assertEqual(metrics["screening_excluded"], 2)
        self.assertEqual(metrics["reports_not_retrieved"], 1)
        self.assertEqual(metrics["returned_to_screening"], 1)
        self.assertEqual(metrics["reports_awaiting_pdf"], 1)
        self.assertEqual(metrics["studies_included_synthesis"], 2)
        self.assertEqual(
            snapshot["exclusion_reasons"]["screening"]["population_mismatch"], 2
        )

    def test_exporta_json_csv_utf8_e_svg(self):
        snapshot = calcular_fluxo_prisma(
            "project-1", connection_factory=_prisma_connection_factory()
        )
        json_data = prisma_para_json(snapshot)
        csv_data = prisma_para_csv(snapshot)
        svg_data = gerar_prisma_svg(snapshot)

        self.assertEqual(json.loads(json_data)["project_title"], "Projeto de teste")
        self.assertTrue(csv_data.startswith("\ufeff"))
        self.assertIn("População fora do escopo", csv_data)
        self.assertIn("<svg", svg_data)
        self.assertIn('height="1110"', svg_data)
        self.assertIn('viewBox="0 0 1200 1110"', svg_data)
        self.assertIn("Fluxo PRISMA rastreável", svg_data)
        self.assertIn("Estudos incluídos na síntese (n = 2)", svg_data)


if __name__ == "__main__":
    unittest.main()
