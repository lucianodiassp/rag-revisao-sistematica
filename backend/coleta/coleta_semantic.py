import os
import requests
import uuid
import time
from dotenv import load_dotenv

# Carrega as variáveis do ficheiro .env
load_dotenv()

def recolher_artigos_semantic(query_term, max_resultados=100):
    """
    Pesquisa artigos no Semantic Scholar com mecanismo de retry e suporte a API Key (Premium Tier).
    """
    # 1. LIMPADOR DE QUERY PARA SEMANTIC SCHOLAR
    # Remove operadores booleanos para evitar que o motor falhe a busca
    query_limpa = query_term.replace("(", "").replace(")", "").replace('"', '').replace("*", "")
    query_limpa = query_limpa.replace(" AND ", " ").replace(" OR ", " ")
    
    # Remove espaços duplos e garante que não excede o limite de tamanho da API
    query_limpa = " ".join(query_limpa.split())[:300] 
    
    print(f"🔍 A iniciar pesquisa no Semantic Scholar por: '{query_limpa}'")
    
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query_limpa, # Usamos a query tratada aqui
        "limit": max_resultados,
        "fields": "paperId,title,abstract,authors,year,venue,externalIds"
    }

    # ==========================================================
    # CONFIGURAÇÃO DE CABEÇALHOS E AUTENTICAÇÃO
    # ==========================================================
    headers = {
        "User-Agent": "Projeto-Academico-RAG/1.0 (mailto:luciano.oliveira@ensino.ipt.br)"
    }
    
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key.strip()
        print("🔑 Chave de API do Semantic Scholar detectada. Usando limite expandido (100 req/s).")
    else:
        print("ℹ️ Chave do Semantic Scholar não encontrada no .env. Executando no modo estrito (1 req/s).")
    # ==========================================================

    max_tentativas = 3
    
    for tentativa in range(1, max_tentativas + 1):
        try:
            # Otimização: Se temos a API Key, a pausa não precisa ser de 2 segundos.
            if api_key:
                time.sleep(0.5)
            else:
                time.sleep(2) 
            
            response = requests.get(url, params=params, headers=headers)
            
            # Se o servidor nos der o Erro 429, fazemos uma pausa longa e tentamos novamente
            if response.status_code == 429:
                print(f"   ⚠️ Servidor ocupado (Erro 429). A aguardar 5 segundos... (Tentativa {tentativa}/{max_tentativas})")
                time.sleep(5)
                continue 
                
            response.raise_for_status() 
            
            dados_brutos = response.json()
            resultados = dados_brutos.get("data", [])
            
            if not resultados:
                print("❌ Nenhum artigo encontrado no Semantic Scholar.")
                return []
                
            print(f"✅ Encontrados {len(resultados)} artigos. A formatar dados...")
            
            artigos_formatados = []
            
            for artigo in resultados:
                titulo = artigo.get("title")
                if not titulo:
                    continue
                    
                autores = [autor.get("name") for autor in artigo.get("authors", [])]
                external_ids = artigo.get("externalIds", {})

                fontes_dict = {
                    "sources": ["Semantic Scholar"],
                    "external_ids": {
                        "doi": external_ids.get("DOI"),
                        "semantic_scholar": artigo.get("paperId")
                    },
                    "metadata": {
                        "publication_year": artigo.get("year"),
                        "authors": autores,
                        "journal_name": artigo.get("venue") or "Revista não especificada",
                        "language": "en"
                    },
                    "concepts": []
                }
                
                id_interno = str(uuid.uuid4())
                abstract = artigo.get("abstract") or "Abstract indisponível diretamente via API."
                
                artigos_formatados.append({
                    "id": id_interno,
                    "titulo": titulo,
                    "abstract": abstract,
                    "fontes_dict": fontes_dict
                })
                
                print(f"   -> Formatado: {titulo[:50]}...")

            return artigos_formatados

        except requests.exceptions.RequestException as e:
            print(f"❌ Erro ao contactar o Semantic Scholar na tentativa {tentativa}: {e}")
            if tentativa == max_tentativas:
                return [] 
            time.sleep(3)
            
    return []