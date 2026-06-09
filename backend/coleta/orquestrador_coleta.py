import sys
import os
import uuid

# Pequeno truque para o Python encontrar a pasta 'app' da Pessoa 3,
# independentemente de onde estejas a executar o script no terminal.
caminho_raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(caminho_raiz)

from backend.coleta.coleta_openalex import recolher_artigos_openalex
from backend.coleta.coleta_pubmed import recolher_artigos_pubmed
from backend.coleta.coleta_semantic import recolher_artigos_semantic
from backend.app.database import salvar_artigo_coletado

# <-- 2. Função de Impressão Digital:
def gerar_id_deterministico(artigo):
    """
    Cria uma impressão digital única (UUID5) baseada no DOI.
    Se o DOI não existir, usa o Título do artigo.
    """
    doi = artigo["fontes_dict"]["external_ids"].get("doi")
    
    if doi:
        # Se tem DOI, usamos isso como base (em minúsculas para não haver erros)
        texto_base = f"doi:{doi.strip().lower()}"
    else:
        # Se não tem DOI, usamos o título exato
        titulo = artigo.get("titulo", "Sem titulo").strip().lower()
        texto_base = f"titulo:{titulo}"
        
    # uuid5 gera sempre o mesmo ID para o mesmo 'texto_base'
    return str(uuid.uuid5(uuid.NAMESPACE_URL, texto_base))

def iniciar_recolha(query, max_por_fonte=5):
    print("=======================================================")
    print(f"🚀 A iniciar o pipeline de recolha para: '{query}'")
    print("=======================================================\n")

    artigos_totais = []

    # 1. Recolha OpenAlex
    print("[Fonte 1] A contactar o OpenAlex...")
    artigos_openalex = recolher_artigos_openalex(query, max_resultados=max_por_fonte)
    artigos_totais.extend(artigos_openalex)

    # 2. Recolha PubMed 
    print("[Fonte 2] A contactar o PubMed...")
    artigos_pubmed = recolher_artigos_pubmed(query, max_resultados=max_por_fonte)
    artigos_totais.extend(artigos_pubmed)
    
    # 3. Recolha Semantic Scholar
    print("\n[Fonte 3] A contactar o Semantic Scholar...")
    artigos_semantic = recolher_artigos_semantic(query, max_resultados=max_por_fonte)
    artigos_totais.extend(artigos_semantic)

    print("-------------------------------------------------------")
    print(f"📊 Total de artigos recolhidos na web: {len(artigos_totais)}")
    print("💾 A enviar para a Base de Dados (Docker)...\n")

    # 4. Guardar na Base de Dados com Desduplicação
    sucessos = 0
    
    for artigo in artigos_totais:
        try:
            # 1. Geramos o ID inteligente antes de gravar
            id_inteligente = gerar_id_deterministico(artigo)
            
            # 2. Usamos o novo ID em vez do artigo["id"]
            salvar_artigo_coletado(
                id_artigo=id_inteligente, 
                titulo=artigo["titulo"],
                abstract=artigo["abstract"],
                fontes_dict=artigo["fontes_dict"]
            )
            sucessos += 1
        except Exception as e:
            # A base de dados vai rejeitar se o ID já lá estiver (Primary Key Duplicada)
            # ou a função da Pessoa 3 vai gerir o erro (ON CONFLICT DO NOTHING)
            print(f"⚠️ Artigo '{artigo['titulo'][:20]}...' ignorado/erro: {e}")

    print(f"\n✅ Processo concluído! Tentativa de gravar {len(artigos_totais)} artigos.")

if __name__ == "__main__":
    # Podes mudar o termo de pesquisa aqui!
    termo_pesquisa = "Retrieval-Augmented Generation"
    
    # Vamos pedir 5 artigos para este primeiro teste
    iniciar_recolha(termo_pesquisa, max_por_fonte=5)