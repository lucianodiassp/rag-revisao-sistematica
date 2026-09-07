"""Contratos de autorização dos agentes e das exportações por projeto."""

from unittest.mock import patch

import pytest

from backend.agentes import (
    agente_avaliador,
    agente_extrator,
    agente_formulador,
    agente_rag,
    agente_relator,
    agente_triagem,
)
from backend.app import golden_set, prisma, reproducibility_package, reranking


PROJECT_ID = "project-agent-authorization"
RESOURCE_ID = "resource-agent-authorization"


def _assert_gate(module, expected_role, operation):
    with patch.object(
        module,
        "enforce_project_access",
        side_effect=PermissionError("blocked by authorization contract"),
    ) as access_gate:
        with pytest.raises(PermissionError, match="authorization contract"):
            operation()

    assert access_gate.call_count == 1
    assert access_gate.call_args.args[:2] == (PROJECT_ID, expected_role)


@pytest.mark.parametrize(
    ("module", "operation"),
    [
        (golden_set, lambda: golden_set.list_golden_queries(PROJECT_ID)),
        (golden_set, lambda: golden_set.list_indexed_papers(PROJECT_ID)),
        (prisma, lambda: prisma.calcular_fluxo_prisma(PROJECT_ID)),
        (prisma, lambda: prisma.carregar_ultimo_snapshot_prisma(PROJECT_ID)),
        (
            reproducibility_package,
            lambda: reproducibility_package.generate_reproducibility_package(PROJECT_ID),
        ),
        (
            agente_triagem,
            lambda: agente_triagem.buscar_artigos_sem_analise(PROJECT_ID),
        ),
        (
            agente_extrator,
            lambda: agente_extrator.carregar_extracoes_projeto(PROJECT_ID),
        ),
        (
            agente_extrator,
            lambda: agente_extrator.buscar_chunks_pdf(PROJECT_ID, RESOURCE_ID),
        ),
        (
            agente_avaliador,
            lambda: agente_avaliador.carregar_perguntas_auditoria(PROJECT_ID),
        ),
        (
            agente_relator,
            lambda: agente_relator.coletar_evidencias(PROJECT_ID),
        ),
        (
            agente_rag,
            lambda: agente_rag._buscar_contexto_hibrido_detalhado(
                "Pergunta de teste", PROJECT_ID
            ),
        ),
    ],
)
def test_agent_and_export_reads_require_viewer_role(module, operation):
    _assert_gate(module, "viewer", operation)


@pytest.mark.parametrize(
    ("module", "operation"),
    [
        (
            golden_set,
            lambda: golden_set.add_golden_query(
                PROJECT_ID, "Pergunta válida para o Golden Set"
            ),
        ),
        (prisma, lambda: prisma.salvar_snapshot_prisma(PROJECT_ID)),
        (
            agente_formulador,
            lambda: agente_formulador.estruturar_pergunta_pesquisa(
                "Pergunta científica", PROJECT_ID
            ),
        ),
        (
            agente_triagem,
            lambda: next(agente_triagem.executar_pipeline_triagem_ui(PROJECT_ID)),
        ),
        (
            agente_extrator,
            lambda: agente_extrator.executar_pipeline_extracao(PROJECT_ID),
        ),
        (
            agente_extrator,
            lambda: agente_extrator.extrair_evidencias_com_ia(
                PROJECT_ID, "Artigo", []
            ),
        ),
        (
            agente_avaliador,
            lambda: agente_avaliador.executar_auditoria(PROJECT_ID),
        ),
        (
            agente_avaliador,
            lambda: agente_avaliador.avaliar_resposta(
                PROJECT_ID, "Pergunta", "Resposta", "Contexto"
            ),
        ),
        (
            agente_relator,
            lambda: agente_relator.gerar_relatorio_final(PROJECT_ID),
        ),
        (
            agente_rag,
            lambda: agente_rag.responder_com_rag("Pergunta de teste", PROJECT_ID),
        ),
        (
            agente_rag,
            lambda: agente_rag.buscar_contexto_reranqueado(
                "Pergunta de teste", PROJECT_ID
            ),
        ),
        (
            reranking,
            lambda: reranking.reranquear_candidatos(
                "Pergunta de teste", [], PROJECT_ID
            ),
        ),
    ],
)
def test_agent_and_export_mutations_require_editor_role(module, operation):
    _assert_gate(module, "editor", operation)
