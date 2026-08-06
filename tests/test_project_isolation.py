import unittest

from backend.app.project_utils import (
    gerar_id_artigo,
    mesclar_proveniencia,
    normalizar_doi,
    normalizar_titulo,
)


class ProjectIsolationTests(unittest.TestCase):
    def setUp(self):
        self.artigo = {
            "titulo": "RAG para Revisão Sistemática",
            "fontes_dict": {
                "sources": ["OpenAlex"],
                "external_ids": {"doi": "https://doi.org/10.1234/ABC.1"},
            },
        }

    def test_mesmo_artigo_e_projeto_gera_id_estavel(self):
        primeiro = gerar_id_artigo(self.artigo, "projeto-a")
        segundo = gerar_id_artigo(self.artigo, "projeto-a")
        self.assertEqual(primeiro, segundo)

    def test_mesmo_artigo_em_projetos_distintos_nao_colide(self):
        primeiro = gerar_id_artigo(self.artigo, "projeto-a")
        segundo = gerar_id_artigo(self.artigo, "projeto-b")
        self.assertNotEqual(primeiro, segundo)

    def test_doi_e_titulo_sao_canonicalizados(self):
        self.assertEqual(normalizar_doi("DOI: 10.1234/ABC.1"), "10.1234/abc.1")
        self.assertEqual(
            normalizar_doi("https://doi.org/10.1234/ABC.1"),
            "10.1234/abc.1",
        )
        self.assertEqual(
            normalizar_titulo("  Revisão—Sistemática: RAG! "),
            "revisao sistematica rag",
        )

    def test_proveniencia_de_duplicatas_e_mesclada(self):
        atual = {
            "sources": ["OpenAlex"],
            "external_ids": {"doi": "10.1234/teste", "openalex": "W1"},
            "metadata": {"publication_year": 2025},
        }
        nova = {
            "sources": ["PubMed", "OpenAlex"],
            "external_ids": {"doi": "10.1234/teste", "pubmed": "123"},
            "metadata": {"journal_name": "Journal"},
        }

        resultado = mesclar_proveniencia(atual, nova)

        self.assertEqual(resultado["sources"], ["OpenAlex", "PubMed"])
        self.assertEqual(resultado["external_ids"]["openalex"], "W1")
        self.assertEqual(resultado["external_ids"]["pubmed"], "123")
        self.assertEqual(resultado["metadata"]["publication_year"], 2025)
        self.assertEqual(resultado["metadata"]["journal_name"], "Journal")


if __name__ == "__main__":
    unittest.main()
