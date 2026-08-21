import os
import sys


caminho_raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(caminho_raiz)

from backend.app.database import (  # noqa: E402
    registrar_busca,
    resolver_project_id,
    salvar_artigo_coletado,
)
from backend.app.bibliographic_config import (  # noqa: E402
    SOURCE_OPENALEX,
    SOURCE_PUBMED,
    SOURCE_SEMANTIC_SCHOLAR,
    get_source_config,
)
from backend.app.project_utils import gerar_id_artigo  # noqa: E402
from backend.app.deduplication import (  # noqa: E402
    ACTION_AUTO_CREATE,
    ACTION_AUTO_MERGE,
    ACTION_PENDING_REVIEW,
)
from backend.coleta.coleta_openalex import recolher_artigos_openalex  # noqa: E402
from backend.coleta.coleta_pubmed import recolher_artigos_pubmed  # noqa: E402
from backend.coleta.coleta_semantic import recolher_artigos_semantic  # noqa: E402


def gerar_id_deterministico(artigo, project_id):
    return gerar_id_artigo(artigo, project_id)


def iniciar_recolha(query, project_id=None, max_por_fonte=5, source_queries=None):
    project_id = resolver_project_id(project_id)
    source_queries = source_queries or {}
    print("=======================================================")
    print(f"🚀 A iniciar a coleta do projeto {project_id}: '{query}'")
    print("=======================================================\n")

    fontes_disponiveis = [
        (SOURCE_OPENALEX, "OpenAlex", recolher_artigos_openalex),
        (SOURCE_PUBMED, "PubMed", recolher_artigos_pubmed),
        (SOURCE_SEMANTIC_SCHOLAR, "Semantic Scholar", recolher_artigos_semantic),
    ]
    fontes = []
    for source_code, nome_fonte, coletor in fontes_disponiveis:
        config = get_source_config(source_code)
        if config.enabled:
            fontes.append((source_code, nome_fonte, coletor, config))
        else:
            print(f"⏭️ {nome_fonte} desativada; a fonte não será consultada.")
    if not fontes:
        raise RuntimeError(
            "Nenhuma fonte bibliográfica está habilitada. "
            "Ative ao menos uma fonte na tela de configuração."
        )
    resultados_por_fonte = []

    for indice, (source_code, nome_fonte, coletor, config) in enumerate(fontes, 1):
        print(f"[Fonte {indice}/{len(fontes)}] A contactar {nome_fonte}...")
        source_query = str(source_queries.get(source_code) or query).strip()
        artigos = coletor(source_query, max_resultados=max_por_fonte)
        busca_id = registrar_busca(
            project_id,
            nome_fonte,
            source_query,
            {
                "source_code": source_code,
                "general_query": query,
                "source_specific_query": source_query != query,
                "max_resultados": max_por_fonte,
                "resultados_retornados": len(artigos),
                "source_configuration": config.public_metadata(),
            },
        )
        resultados_por_fonte.append((nome_fonte, busca_id, artigos))

    total_encontrados = sum(len(artigos) for _, _, artigos in resultados_por_fonte)
    print("-------------------------------------------------------")
    print(f"📊 Total de artigos recolhidos na web: {total_encontrados}")

    sucessos = 0
    mesclados = 0
    pendentes_revisao = 0
    for nome_fonte, busca_id, artigos in resultados_por_fonte:
        for artigo in artigos:
            try:
                id_artigo = gerar_id_deterministico(artigo, project_id)
                resultado_persistencia = salvar_artigo_coletado(
                    project_id=project_id,
                    id_artigo=id_artigo,
                    titulo=artigo["titulo"],
                    abstract=artigo["abstract"],
                    fontes_dict=artigo["fontes_dict"],
                    search_query_id=busca_id,
                    fonte=nome_fonte,
                )
                status_deduplicacao = (
                    resultado_persistencia.get("status")
                    if isinstance(resultado_persistencia, dict)
                    else ACTION_AUTO_CREATE if resultado_persistencia else ACTION_AUTO_MERGE
                )
                if status_deduplicacao == ACTION_AUTO_CREATE:
                    sucessos += 1
                elif status_deduplicacao == ACTION_AUTO_MERGE:
                    mesclados += 1
                elif status_deduplicacao == ACTION_PENDING_REVIEW:
                    pendentes_revisao += 1
            except Exception as erro:
                print(f"⚠️ Artigo '{artigo['titulo'][:20]}...' gerou erro: {erro}")

    print(
        f"\n✅ Processo concluído no projeto {project_id}: "
        f"{sucessos} novos, {mesclados} mesclados automaticamente e "
        f"{pendentes_revisao} aguardando revisão, em {total_encontrados} registros recuperados."
    )
    return sucessos, total_encontrados, mesclados, pendentes_revisao


if __name__ == "__main__":
    from backend.app.database import obter_projeto

    projeto_id = resolver_project_id()
    projeto = obter_projeto(projeto_id)
    termo_pesquisa = (projeto.get("criteria_jsonb") or {}).get("search_string", "")
    if not termo_pesquisa:
        raise RuntimeError("O projeto ativo ainda não possui uma estratégia de busca.")
    iniciar_recolha(termo_pesquisa, project_id=projeto_id, max_por_fonte=5)
