from backend.agentes.agente_rag import buscar_contexto_hibrido
from backend.app.database import resolver_project_id


def buscar_artigos_similares(pergunta, project_id=None, limite=3):
    project_id = resolver_project_id(project_id)
    resultados = buscar_contexto_hibrido(
        pergunta,
        project_id=project_id,
        limite=limite,
    )
    for indice, (paper_id, texto, score) in enumerate(resultados, 1):
        print(f"{indice}º · projeto={project_id} · artigo={paper_id} · RRF={score:.4f}")
        print(f"Trecho: {texto[:200]}...")


if __name__ == "__main__":
    buscar_artigos_similares("Quais são as principais limitações dos estudos?")
