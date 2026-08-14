import unittest
from unittest.mock import Mock

from backend.app.golden_set import add_golden_query, add_golden_relevance


class GoldenSetValidationTests(unittest.TestCase):
    def test_pergunta_exige_texto_minimo(self):
        with self.assertRaisesRegex(ValueError, "5 caracteres"):
            add_golden_query("project-1", "Oi", connection_factory=Mock())

    def test_grau_de_relevancia_deve_estar_entre_um_e_tres(self):
        with self.assertRaisesRegex(ValueError, "entre 1 e 3"):
            add_golden_relevance(
                "project-1",
                "query-1",
                "paper-1",
                page_number=1,
                relevance_grade=4,
                connection_factory=Mock(),
            )

    def test_pagina_deve_ser_positiva(self):
        with self.assertRaisesRegex(ValueError, "maior que zero"):
            add_golden_relevance(
                "project-1",
                "query-1",
                "paper-1",
                page_number=-1,
                relevance_grade=2,
                connection_factory=Mock(),
            )


if __name__ == "__main__":
    unittest.main()
