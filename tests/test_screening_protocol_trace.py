import json
import unittest
from unittest.mock import Mock, patch

from backend.agentes import agente_triagem


class ScreeningProtocolTraceTests(unittest.TestCase):
    def test_criterios_dinamicos_incluem_picos_e_elegibilidade_estruturada(self):
        protocol = {
            "pico": {
                "population": "Frotas comerciais",
                "intervention": "Manutenção preditiva",
                "outcome": "Redução de falhas",
                "study_design": "Estudos experimentais",
            },
            "eligibility": {
                "year_from": 2020,
                "year_to": 2026,
                "languages": ["Português", "Inglês"],
                "publication_types": ["Artigo completo"],
                "study_designs": ["Experimento"],
            },
            "inclusion_criteria": ["Avalia frotas comerciais"],
            "exclusion_criteria": ["Não apresenta avaliação"],
        }
        scope, inclusion, exclusion = agente_triagem.carregar_criterios_dinamicos(
            "project-1", protocol=protocol
        )
        self.assertIn("População ou problema: Frotas comerciais", scope)
        self.assertIn("Período de publicação: 2020 a 2026", scope)
        self.assertIn("Idiomas aceitos: Português, Inglês", scope)
        self.assertIn("Avalia frotas comerciais", inclusion)
        self.assertIn("Não apresenta avaliação", exclusion)

    def test_parecer_registra_versao_hash_e_snapshot_dos_criterios(self):
        protocol = {
            "pico": {
                "population": "Frotas",
                "intervention": "Manutenção preditiva",
                "comparison": "Manutenção corretiva",
                "outcome": "Redução de falhas",
            },
            "inclusion_criteria": ["Avalia frotas comerciais"],
            "exclusion_criteria": ["Não apresenta avaliação"],
            "search_string": "fleet AND predictive maintenance",
        }
        connection = Mock()
        cursor = Mock()
        connection.cursor.return_value = cursor
        config = Mock(provider="google_gemini", model="model-1")
        config.metadata.return_value = {"provider": "google_gemini", "model": "model-1"}

        with (
            patch.object(agente_triagem, "resolver_project_id", return_value="project-1"),
            patch.object(
                agente_triagem,
                "obter_projeto",
                return_value={"criteria_jsonb": protocol, "protocol_version": 7},
            ),
            patch.object(
                agente_triagem,
                "buscar_artigos_sem_analise",
                return_value=[("paper-1", "Título", "Resumo")],
            ),
            patch.object(
                agente_triagem,
                "triar_artigo_com_ia",
                return_value={
                    "suggested_decision": "Incluir",
                    "confidence": 0.9,
                    "justification": "Atende aos critérios.",
                },
            ),
            patch.object(agente_triagem, "get_generation_config", return_value=config),
            patch.object(agente_triagem, "get_conexao", return_value=connection),
        ):
            statuses = list(agente_triagem.executar_pipeline_triagem_ui("project-1"))

        self.assertEqual(statuses[-1]["status"], "concluido")
        screening_params = cursor.execute.call_args_list[0].args[1]
        rationale = json.loads(screening_params[3])
        self.assertEqual(rationale["protocol_version"], 7)
        self.assertEqual(len(rationale["protocol_fingerprint"]), 64)

        interaction_params = cursor.execute.call_args_list[1].args[1]
        interaction_input = json.loads(interaction_params[3])
        self.assertEqual(interaction_input["protocol_version"], 7)
        self.assertEqual(
            interaction_input["eligibility_snapshot"]["inclusion_criteria"],
            ["Avalia frotas comerciais"],
        )


if __name__ == "__main__":
    unittest.main()
