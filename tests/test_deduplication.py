import unittest
from unittest.mock import Mock

from backend.app.deduplication import (
    ACTION_AUTO_CREATE,
    ACTION_AUTO_MERGE,
    ACTION_PENDING_REVIEW,
    HUMAN_KEEP_SEPARATE,
    HUMAN_MERGE,
    RULE_DOI_EXACT,
    RULE_TITLE_EXACT,
    RULE_TITLE_SIMILAR,
    avaliar_duplicidade,
    revisar_decisao_deduplicacao,
)


def _artigo(paper_id, titulo, doi=None, autores=None, ano=None):
    fontes = {
        "sources": ["Teste"],
        "external_ids": {"doi": doi},
        "metadata": {"authors": autores or [], "publication_year": ano},
    }
    return {
        "id": paper_id,
        "canonical_doi": doi,
        "title": titulo,
        "abstract": "Resumo existente",
        "merged_sources_jsonb": fontes,
    }


def _entrada(titulo, doi=None, autores=None, ano=None):
    return {
        "proposed_paper_id": "paper-new",
        "canonical_doi": doi,
        "title": titulo,
        "abstract": "Resumo recebido",
        "fontes_dict": {
            "sources": ["Nova fonte"],
            "external_ids": {"doi": doi},
            "metadata": {"authors": autores or [], "publication_year": ano},
        },
    }


def _connection_factory(fetchone_results):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.side_effect = fetchone_results
    connection.cursor.return_value = cursor
    return Mock(return_value=connection), cursor


class ExplainableDeduplicationTests(unittest.TestCase):
    def test_doi_identico_e_mesclado_automaticamente(self):
        entrada = _entrada("Título recebido", "https://doi.org/10.1000/ABC")
        candidato = _artigo("paper-1", "Outro título", "10.1000/abc")

        resultado = avaliar_duplicidade(entrada, [candidato])

        self.assertEqual(resultado["rule_code"], RULE_DOI_EXACT)
        self.assertEqual(resultado["system_action"], ACTION_AUTO_MERGE)
        self.assertEqual(resultado["score"], 1.0)
        self.assertTrue(resultado["evidence"]["doi_match"])

    def test_titulo_identico_exige_revisao_e_explica_conflito_de_doi(self):
        entrada = _entrada("RAG para Revisão Sistemática", "10.1000/novo")
        candidato = _artigo(
            "paper-1",
            "RAG para revisão sistemática!",
            "10.1000/existente",
        )

        resultado = avaliar_duplicidade(entrada, [candidato])

        self.assertEqual(resultado["rule_code"], RULE_TITLE_EXACT)
        self.assertEqual(resultado["system_action"], ACTION_PENDING_REVIEW)
        self.assertTrue(resultado["evidence"]["doi_conflict"])
        self.assertIn("DOIs divergentes", resultado["explanation"])

    def test_titulo_semelhante_combina_autores_e_ano(self):
        entrada = _entrada(
            "Retrieval augmented generation for systematic literature reviews",
            autores=["Ana Silva", "Bruno Souza"],
            ano=2025,
        )
        candidato = _artigo(
            "paper-1",
            "Retrieval-augmented generation in systematic literature review",
            autores=["Silva A", "Souza B"],
            ano=2025,
        )

        resultado = avaliar_duplicidade(entrada, [candidato])

        self.assertEqual(resultado["rule_code"], RULE_TITLE_SIMILAR)
        self.assertEqual(resultado["system_action"], ACTION_PENDING_REVIEW)
        self.assertGreaterEqual(resultado["score"], 0.78)
        self.assertEqual(resultado["evidence"]["author_overlap"], 1.0)
        self.assertTrue(resultado["evidence"]["year_match"])

    def test_candidato_fraco_cria_novo_artigo(self):
        resultado = avaliar_duplicidade(
            _entrada("Modelos de linguagem na educação"),
            [_artigo("paper-1", "Diagnóstico médico por imagens")],
        )

        self.assertEqual(resultado["system_action"], ACTION_AUTO_CREATE)
        self.assertLess(resultado["score"], 0.78)

    def test_revisao_humana_mescla_proveniencia(self):
        incoming = _entrada("Título recebido", "10.1000/abc")
        factory, cursor = _connection_factory(
            [
                ("paper-1", incoming, "pending"),
                (
                    "Título existente",
                    "Resumo existente",
                    "10.1000/abc",
                    {"sources": ["OpenAlex"], "metadata": {}},
                ),
            ]
        )

        resultado = revisar_decisao_deduplicacao(
            "project-1",
            "decision-1",
            HUMAN_MERGE,
            "Metadados confirmam que é o mesmo artigo.",
            connection_factory=factory,
        )

        self.assertEqual(resultado["result_paper_id"], "paper-1")
        self.assertEqual(resultado["human_decision"], HUMAN_MERGE)
        comandos = [chamada.args[0] for chamada in cursor.execute.call_args_list]
        self.assertTrue(any("UPDATE deduplicated_papers" in comando for comando in comandos))
        self.assertTrue(any("UPDATE deduplication_decisions" in comando for comando in comandos))

    def test_revisao_humana_mantem_artigo_separado(self):
        incoming = _entrada("Título diferente", "10.1000/diferente")
        factory, cursor = _connection_factory(
            [("paper-1", incoming, "pending"), None]
        )

        resultado = revisar_decisao_deduplicacao(
            "project-1",
            "decision-1",
            HUMAN_KEEP_SEPARATE,
            "O objeto de estudo e o DOI são diferentes.",
            connection_factory=factory,
        )

        self.assertEqual(resultado["human_decision"], HUMAN_KEEP_SEPARATE)
        comandos = [chamada.args[0] for chamada in cursor.execute.call_args_list]
        self.assertTrue(any("INSERT INTO deduplicated_papers" in comando for comando in comandos))

    def test_revisao_exige_justificativa(self):
        with self.assertRaisesRegex(ValueError, "pelo menos 5"):
            revisar_decisao_deduplicacao(
                "project-1",
                "decision-1",
                HUMAN_MERGE,
                "não",
                connection_factory=Mock(),
            )


if __name__ == "__main__":
    unittest.main()
