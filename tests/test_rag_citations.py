import unittest

from backend.app.rag_citations import validar_citacoes_rag


PAPER_ID = "75000000-0000-0000-0000-000000000001"
OUTRO_PAPER_ID = "75000000-0000-0000-0000-000000000002"


class RagCitationTests(unittest.TestCase):
    def setUp(self):
        self.evidencias = [
            {"paper_id": PAPER_ID, "page_number": 12},
            {"paper_id": PAPER_ID, "page_number": 13},
        ]

    def test_preserva_citacao_de_artigo_e_pagina_recuperados(self):
        resposta, auditoria = validar_citacoes_rag(
            f"Achado confirmado [{PAPER_ID}, p. 12].",
            self.evidencias,
        )

        self.assertEqual(resposta, f"Achado confirmado [{PAPER_ID}, p. 12].")
        self.assertEqual(auditoria["valid_citations"], [f"[{PAPER_ID}, p. 12]"])
        self.assertFalse(auditoria["source_citations_appended"])

    def test_desambigua_referencia_numerica_interna_e_adiciona_fontes(self):
        resposta, auditoria = validar_citacoes_rag(
            "Wang et al. [36] propuseram uma heurística.",
            self.evidencias,
        )

        self.assertIn("referência bibliográfica nº 36 citada no artigo", resposta)
        self.assertNotIn("[36]", resposta)
        self.assertIn("**Aviso de rastreabilidade:**", resposta)
        self.assertIn("Fontes recuperadas:", resposta)
        self.assertEqual(auditoria["internal_references_disambiguated"], ["36"])
        self.assertEqual(len(auditoria["source_citations_appended"]), 2)

    def test_remove_uuid_e_pagina_que_nao_foram_recuperados(self):
        resposta, auditoria = validar_citacoes_rag(
            f"Afirmação [{OUTRO_PAPER_ID}, p. 99].",
            self.evidencias,
        )

        self.assertNotIn(OUTRO_PAPER_ID, resposta)
        self.assertIn("citação de fonte não validada removida", resposta)
        self.assertEqual(
            auditoria["invalid_citations_removed"],
            [f"[{OUTRO_PAPER_ID}, p. 99]"],
        )

    def test_resposta_sem_contexto_nao_recebe_lista_de_fontes(self):
        resposta, auditoria = validar_citacoes_rag(
            "Não tenho dados suficientes nos artigos recolhidos para responder.",
            self.evidencias,
        )

        self.assertNotIn("Fontes recuperadas", resposta)
        self.assertFalse(auditoria["source_citations_appended"])


if __name__ == "__main__":
    unittest.main()
