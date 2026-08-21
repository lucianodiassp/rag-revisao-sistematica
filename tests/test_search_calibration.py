import unittest
from unittest.mock import Mock, patch

from backend.app.search_calibration import (
    PRESS_DOMAINS,
    _match_sentinel,
    calibration_matches_csv,
    run_calibration,
    save_press_review,
)


def _protocol():
    return {
        "pico": {
            "population": "Sistemas logísticos",
            "intervention": "Otimização de rotas",
            "comparison": "",
            "outcome": "Custo e distância",
            "study_design": "",
        },
        "inclusion_criteria": ["Estudos sobre transporte de cargas"],
        "exclusion_criteria": ["Somente transporte de passageiros"],
        "search_string": '"vehicle routing" AND freight',
        "source_search_strings": {"pubmed": "routing AND freight"},
    }


def _article(title, doi):
    return {
        "titulo": title,
        "fontes_dict": {"external_ids": {"doi": doi}},
    }


def _factory(fetchone_values):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.side_effect = fetchone_values
    connection.cursor.return_value = cursor
    return Mock(return_value=connection), cursor


class SearchCalibrationTests(unittest.TestCase):
    def test_correspondencia_prioriza_doi_e_registra_posicao(self):
        sentinel = {
            "id": "sentinel-1",
            "title": "A title written differently",
            "canonical_doi": "10.1000/example",
        }
        result = _match_sentinel(
            sentinel,
            [
                _article("Outro estudo", "10.2000/other"),
                _article("Completely distinct displayed title", "https://doi.org/10.1000/EXAMPLE"),
            ],
        )
        self.assertEqual(result["method"], "doi_exact")
        self.assertEqual(result["rank"], 2)
        self.assertEqual(result["similarity"], 1.0)

    def test_titulo_muito_semelhante_e_aceito_sem_doi(self):
        sentinel = {
            "id": "sentinel-1",
            "title": "Deep reinforcement learning for vehicle routing problems",
            "canonical_doi": None,
        }
        result = _match_sentinel(
            sentinel,
            [_article("Deep Reinforcement Learning for Vehicle-Routing Problems", None)],
        )
        self.assertIn(result["method"], {"title_exact", "title_similar"})

    def test_doi_divergente_impede_falso_positivo_por_titulo(self):
        sentinel = {
            "id": "sentinel-1",
            "title": "Mesmo título em publicações diferentes",
            "canonical_doi": "10.1/original",
        }
        result = _match_sentinel(
            sentinel,
            [_article("Mesmo título em publicações diferentes", "10.1/outra")],
        )
        self.assertIsNone(result)

    def test_piloto_e_isolado_e_calcula_sensibilidade_conhecida(self):
        factory, cursor = _factory([ (3, _protocol()), ("run-1",) ])
        sentinels = [
            {"id": "11111111-1111-1111-1111-111111111111", "title": "Known A", "canonical_doi": "10.1/a"},
            {"id": "22222222-2222-2222-2222-222222222222", "title": "Known B", "canonical_doi": "10.1/b"},
        ]
        config = {
            code: Mock(enabled=True)
            for code in ("openalex", "pubmed", "semantic_scholar")
        }
        collectors = {
            "openalex": Mock(return_value=[_article("Known A", "10.1/a")]),
            "pubmed": Mock(return_value=[_article("Known B", "10.1/b")]),
            "semantic_scholar": Mock(return_value=[]),
        }
        with (
            patch("backend.app.search_calibration.list_sentinels", return_value=sentinels),
            patch("backend.app.search_calibration.get_bibliographic_settings", return_value=config),
        ):
            result = run_calibration(
                "project-1", 50, collectors=collectors, connection_factory=factory
            )

        self.assertEqual(result["summary_jsonb"]["known_item_sensitivity"], 1.0)
        self.assertEqual(result["summary_jsonb"]["sources"]["openalex"]["results_scanned"], 1)
        executed_sql = "\n".join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn("INSERT INTO search_calibration_runs", executed_sql)
        self.assertNotIn("retrieved_records", executed_sql)
        self.assertNotIn("deduplicated_papers", executed_sql)

    def test_falha_de_uma_fonte_gera_execucao_parcial(self):
        factory, _ = _factory([(1, _protocol()), ("run-1",)])
        sentinels = [
            {"id": "11111111-1111-1111-1111-111111111111", "title": "Known A", "canonical_doi": "10.1/a"}
        ]
        config = {code: Mock(enabled=True) for code in ("openalex", "pubmed", "semantic_scholar")}
        collectors = {
            "openalex": Mock(side_effect=RuntimeError("temporarily unavailable")),
            "pubmed": Mock(return_value=[_article("Known A", "10.1/a")]),
            "semantic_scholar": Mock(return_value=[]),
        }
        with (
            patch("backend.app.search_calibration.list_sentinels", return_value=sentinels),
            patch("backend.app.search_calibration.get_bibliographic_settings", return_value=config),
        ):
            result = run_calibration(
                "project-1", 10, collectors=collectors, connection_factory=factory
            )
        self.assertEqual(result["status"], "partial")
        self.assertIn("RuntimeError", result["summary_jsonb"]["sources"]["openalex"]["error"])

    def test_revisao_press_exige_todos_os_dominios_e_usa_hash_da_versao(self):
        checklist = [
            {"code": domain["code"], "response": "yes", "comment": "Revisado"}
            for domain in PRESS_DOMAINS
        ]
        factory, cursor = _factory([(_protocol(),), ("review-1",)])
        review_id = save_press_review(
            "project-1", 2, checklist, "approved", "Pesquisadora", "Estratégia validada",
            connection_factory=factory,
        )
        self.assertEqual(review_id, "review-1")
        insert_params = cursor.execute.call_args_list[1].args[1]
        self.assertEqual(len(insert_params[2]), 64)
        self.assertEqual(insert_params[4], "approved")

    def test_csv_de_correspondencias_tem_bom_e_campos_auditaveis(self):
        content = calibration_matches_csv(
            {
                "matches": [
                    {
                        "source_code": "pubmed",
                        "sentinel_id": "s1",
                        "result_rank": 7,
                        "match_method": "doi_exact",
                        "similarity_score": 1,
                        "matched_title": "Título",
                        "matched_doi": "10.1/a",
                    }
                ]
            }
        )
        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"match_method", content)


if __name__ == "__main__":
    unittest.main()
