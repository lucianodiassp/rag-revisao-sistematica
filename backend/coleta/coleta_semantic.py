import requests
import uuid
import time

from backend.app.bibliographic_config import (
    SOURCE_SEMANTIC_SCHOLAR,
    get_source_config,
)
from backend.coleta.http_utils import safe_request_error

def recolher_artigos_semantic(query_term, max_resultados=100, raise_on_error=False):
    """
    Pesquisa artigos no Semantic Scholar com mecanismo de retry e suporte a API Key (Premium Tier).
    """
    config = get_source_config(SOURCE_SEMANTIC_SCHOLAR)
    if not config.enabled:
        print("⏭️ Semantic Scholar está desativada na configuração de fontes bibliográficas.")
        return []

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
    user_agent = config.tool_name
    if config.contact_email:
        user_agent = f"{user_agent} (mailto:{config.contact_email})"
    headers = {"User-Agent": user_agent}
    
    api_key = config.api_key
    if api_key:
        headers["x-api-key"] = api_key.strip()
        print("🔑 Chave de API do Semantic Scholar detectada. Usando acesso autenticado.")
    else:
        print("ℹ️ Semantic Scholar configurada sem chave de API; aplicando espera conservadora.")
    # ==========================================================

    max_tentativas = config.max_retries
    
    for tentativa in range(1, max_tentativas + 1):
        try:
            # Otimização: Se temos a API Key, a pausa não precisa ser de 2 segundos.
            if api_key:
                time.sleep(0.5)
            else:
                time.sleep(2) 
            
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=config.timeout_seconds,
            )
            
            # Se o servidor nos der o Erro 429, fazemos uma pausa longa e tentamos novamente
            if response.status_code == 429:
                try:
                    espera = max(1, min(int(response.headers.get("Retry-After", 5)), 60))
                except (TypeError, ValueError):
                    espera = 5
                print(
                    "   ⚠️ Limite temporário da API (Erro 429). "
                    f"A aguardar {espera} segundos... "
                    f"(Tentativa {tentativa}/{max_tentativas})"
                )
                time.sleep(espera)
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
            print(
                "❌ Erro ao contactar o Semantic Scholar na tentativa "
                f"{tentativa}: {safe_request_error(e, api_key)}"
            )
            if tentativa == max_tentativas:
                if raise_on_error:
                    raise
                return [] 
            time.sleep(3)
            
    if raise_on_error:
        raise RuntimeError(
            "O Semantic Scholar manteve o limite temporário após todas as tentativas."
        )
    return []
