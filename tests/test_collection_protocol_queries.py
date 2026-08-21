import unittest
from unittest.mock import Mock, patch

from backend.coleta import orquestrador_coleta


class CollectionProtocolQueryTests(unittest.TestCase):
    def test_cada_fonte_usa_string_confirmada_e_registra_a_versao_logica(self):
        config = Mock(enabled=True)
        config.public_metadata.return_value = {"enabled": True}
        queries = {
            "openalex": "open query",
            "pubmed": "pubmed query",
            "semantic_scholar": "semantic query",
        }

        with (
            patch.object(orquestrador_coleta, "resolver_project_id", return_value="project-1"),
            patch.object(orquestrador_coleta, "get_source_config", return_value=config),
            patch.object(orquestrador_coleta, "recolher_artigos_openalex", return_value=[]) as openalex,
            patch.object(orquestrador_coleta, "recolher_artigos_pubmed", return_value=[]) as pubmed,
            patch.object(orquestrador_coleta, "recolher_artigos_semantic", return_value=[]) as semantic,
            patch.object(orquestrador_coleta, "registrar_busca", side_effect=["s1", "s2", "s3"]) as register,
        ):
            result = orquestrador_coleta.iniciar_recolha(
                "general query",
                project_id="project-1",
                max_por_fonte=7,
                source_queries=queries,
            )

        self.assertEqual(result, (0, 0, 0, 0))
        openalex.assert_called_once_with("open query", max_resultados=7)
        pubmed.assert_called_once_with("pubmed query", max_resultados=7)
        semantic.assert_called_once_with("semantic query", max_resultados=7)
        self.assertEqual(register.call_args_list[0].args[2], "open query")
        self.assertTrue(register.call_args_list[0].args[3]["source_specific_query"])


if __name__ == "__main__":
    unittest.main()
