import os
import sys


caminho_raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(caminho_raiz)

from backend.app.database import (  # noqa: E402
    registrar_busca,
    resolver_project_id,
    salvar_artigo_coletado,
)
from backend.app.project_utils import gerar_id_artigo  # noqa: E402
from backend.coleta.coleta_openalex import recolher_artigos_openalex  # noqa: E402
from backend.coleta.coleta_pubmed import recolher_artigos_pubmed  # noqa: E402
from backend.coleta.coleta_semantic import recolher_artigos_semantic  # noqa: E402


def gerar_id_deterministico(artigo, project_id):
    return gerar_id_artigo(artigo, project_id)


def iniciar_recolha(query, project_id=None, max_por_fonte=5):
    project_id = resolver_project_id(project_id)
    print("=======================================================")
    print(f"🚀 A iniciar a coleta do projeto {project_id}: '{query}'")
    print("=======================================================\n")

    fontes = [
        ("OpenAlex", recolher_artigos_openalex),
        ("PubMed", recolher_artigos_pubmed),
        ("Semantic Scholar", recolher_artigos_semantic),
    ]
    resultados_por_fonte = []

    for indice, (nome_fonte, coletor) in enumerate(fontes, 1):
        print(f"[Fonte {indice}] A contactar {nome_fonte}...")
        artigos = coletor(query, max_resultados=max_por_fonte)
        busca_id = registrar_busca(
            project_id,
            nome_fonte,
            query,
            {"max_resultados": max_por_fonte, "resultados_retornados": len(artigos)},
        )
        resultados_por_fonte.append((nome_fonte, busca_id, artigos))

    total_encontrados = sum(len(artigos) for _, _, artigos in resultados_por_fonte)
    print("-------------------------------------------------------")
    print(f"📊 Total de artigos recolhidos na web: {total_encontrados}")

    sucessos = 0
    for nome_fonte, busca_id, artigos in resultados_por_fonte:
        for artigo in artigos:
            try:
                id_artigo = gerar_id_deterministico(artigo, project_id)
                inserido = salvar_artigo_coletado(
                    project_id=project_id,
                    id_artigo=id_artigo,
                    titulo=artigo["titulo"],
                    abstract=artigo["abstract"],
                    fontes_dict=artigo["fontes_dict"],
                    search_query_id=busca_id,
                    fonte=nome_fonte,
                )
                if inserido:
                    sucessos += 1
            except Exception as erro:
                print(f"⚠️ Artigo '{artigo['titulo'][:20]}...' gerou erro: {erro}")

    print(
        f"\n✅ Processo concluído no projeto {project_id}: "
        f"{sucessos} novos artigos de {total_encontrados} registros recuperados."
    )
    return sucessos, total_encontrados


if __name__ == "__main__":
    from backend.app.database import obter_projeto

    projeto_id = resolver_project_id()
    projeto = obter_projeto(projeto_id)
    termo_pesquisa = (projeto.get("criteria_jsonb") or {}).get("search_string", "")
    if not termo_pesquisa:
        raise RuntimeError("O projeto ativo ainda não possui uma estratégia de busca.")
    iniciar_recolha(termo_pesquisa, project_id=projeto_id, max_por_fonte=5)
