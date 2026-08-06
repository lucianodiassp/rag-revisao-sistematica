from backend.app.database import (
    log_interacao_agente,
    resolver_project_id,
    salvar_artigo_coletado,
)
from backend.coleta.orquestrador_coleta import gerar_id_deterministico


project_id = resolver_project_id()
artigo = {
    "titulo": "O impacto do RAG na automação de revisões",
    "abstract": "Artigo de teste inserido via script Python.",
    "fontes_dict": {
        "sources": ["TesteLocal"],
        "external_ids": {"doi": "10.0000/teste-rag"},
        "metadata": {},
    },
}
paper_id = gerar_id_deterministico(artigo, project_id)

salvar_artigo_coletado(
    project_id=project_id,
    id_artigo=paper_id,
    titulo=artigo["titulo"],
    abstract=artigo["abstract"],
    fontes_dict=artigo["fontes_dict"],
    fonte="TesteLocal",
)

log_interacao_agente(
    project_id,
    "agente_teste_python",
    {"paper_id": paper_id, "acao": "analisar_inclusao"},
    {"decisao": "include", "confianca": 0.99},
    {"provider": "teste", "model_name": "modelo-local"},
)

print(f"✅ Teste concluído no projeto {project_id}.")
