import unittest
from unittest.mock import Mock, patch

from backend.app.protocol_service import (
    compare_protocols,
    get_protocol_change_impact,
    get_protocol_history,
    normalize_protocol,
    protocol_fingerprint,
    validate_protocol,
)


def _factory(fetchone=None, fetchall=None):
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


def _valid_protocol():
    return {
        "pico": {
            "population": "Veículos de transporte de cargas",
            "intervention": "Métodos de otimização de rotas",
            "comparison": "Métodos tradicionais",
            "outcome": "Distância e custo",
            "study_design": "Estudos experimentais",
        },
        "eligibility": {
            "year_from": "2020",
            "year_to": 2026,
            "languages": ["Português", "Inglês"],
            "publication_types": ["Artigo completo"],
            "study_designs": ["Experimento computacional"],
        },
        "inclusion_criteria": ["Avalia transporte de cargas"],
        "exclusion_criteria": ["Trata somente de passageiros"],
        "search_concepts": [
            {"concept": "Roteamento", "terms": "vehicle routing; VRP"}
        ],
        "search_string": '("vehicle routing" OR VRP) AND freight',
        "source_search_strings": {"pubmed": "routing AND freight"},
        "audit_questions": [],
    }


class ProtocolServiceTests(unittest.TestCase):
    def test_normaliza_protocolo_legado_sem_perder_marcadores_privados(self):
        result = normalize_protocol(
            {
                "pico": {"population": "  Veículos   comerciais "},
                "inclusion_criteria": ["Critério A", "critério a", ""],
                "exclusion_criteria": ["Critério B"],
                "search_string": " freight ",
                "_demo": {"seed_id": "demo"},
            }
        )

        self.assertEqual(result["pico"]["population"], "Veículos comerciais")
        self.assertEqual(result["pico"]["study_design"], "")
        self.assertEqual(result["inclusion_criteria"], ["Critério A"])
        self.assertEqual(result["source_search_strings"]["openalex"], "")
        self.assertEqual(result["_demo"]["seed_id"], "demo")

    def test_valida_e_normaliza_rascunho_confirmado(self):
        question, protocol, reason = validate_protocol(
            "Como otimizar rotas de transporte de cargas?",
            _valid_protocol(),
            "Refinamento após busca piloto",
        )

        self.assertTrue(question.endswith("?"))
        self.assertEqual(protocol["eligibility"]["year_from"], 2020)
        self.assertEqual(protocol["search_concepts"][0]["terms"], ["vehicle routing", "VRP"])
        self.assertEqual(reason, "Refinamento após busca piloto")

    def test_rejeita_periodo_e_sintaxe_inconsistentes(self):
        protocol = _valid_protocol()
        protocol["eligibility"]["year_from"] = 2030
        with self.assertRaisesRegex(ValueError, "posterior"):
            validate_protocol("Pergunta suficientemente longa?", protocol, "Ajuste válido")

        protocol = _valid_protocol()
        protocol["search_string"] = '(routing AND "freight"'
        with self.assertRaisesRegex(ValueError, "parênteses"):
            validate_protocol("Pergunta suficientemente longa?", protocol, "Ajuste válido")

    def test_hash_e_estavel_apos_normalizacao(self):
        first = _valid_protocol()
        second = _valid_protocol()
        second["inclusion_criteria"] = ["  Avalia   transporte de cargas  "]
        self.assertEqual(protocol_fingerprint(first), protocol_fingerprint(second))

    def test_comparacao_identifica_secoes_metodologicas_alteradas(self):
        first = _valid_protocol()
        second = _valid_protocol()
        second["pico"]["outcome"] = "Emissões e custo"
        second["source_search_strings"]["openalex"] = "freight routing"
        changes = compare_protocols(
            "Pergunta original suficientemente longa?",
            first,
            "Pergunta refinada suficientemente longa?",
            second,
        )
        self.assertEqual(
            changes,
            ["Pergunta de pesquisa", "PICO/PICOS", "Strings por fonte"],
        )

    def test_historico_e_impacto_permanecem_isolados_por_projeto(self):
        protocol = _valid_protocol()
        history_factory, history_cursor = _factory(
            fetchall=[(2, "Pergunta", protocol, "Motivo", "2026-08-20")]
        )
        history = get_protocol_history("project-1", connection_factory=history_factory)
        self.assertEqual(history[0]["version"], 2)
        self.assertEqual(history_cursor.execute.call_args.args[1], ("project-1",))

        impact_factory, impact_cursor = _factory(fetchone=(3, 104, 92))
        impact = get_protocol_change_impact(
            "project-1", connection_factory=impact_factory
        )
        self.assertTrue(impact["requires_attention"])
        self.assertEqual(impact["screening_decisions"], 92)
        self.assertEqual(
            impact_cursor.execute.call_args.args[1],
            ("project-1", "project-1", "project-1"),
        )

    def test_registro_de_busca_inclui_versao_e_hash_do_protocolo(self):
        from backend.app import database

        factory, cursor = _factory()
        cursor.fetchone.side_effect = [(4, _valid_protocol()), ("search-1",)]
        with patch.object(database, "get_connection", factory):
            result = database.registrar_busca(
                "project-1", "OpenAlex", "routing", {"limit": 10}
            )

        self.assertEqual(result, "search-1")
        _, insert_params = cursor.execute.call_args_list[1].args
        metadata = insert_params[3].adapted
        self.assertEqual(metadata["protocol_version"], 4)
        self.assertEqual(metadata["limit"], 10)
        self.assertEqual(len(metadata["protocol_fingerprint"]), 64)

    def test_atualizacao_de_busca_preserva_metadados_do_protocolo(self):
        from backend.app import database

        factory, cursor = _factory()
        cursor.rowcount = 1
        with patch.object(database, "get_connection", factory):
            database.atualizar_metadados_busca(
                "project-1", "search-1", {"status": "completed"}
            )
        sql = cursor.execute.call_args.args[0]
        self.assertIn("COALESCE(query_jsonb", sql)
        self.assertIn("%s::jsonb - 'protocol_version'", sql)


if __name__ == "__main__":
    unittest.main()
