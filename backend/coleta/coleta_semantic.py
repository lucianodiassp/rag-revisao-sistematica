import requests
import uuid
import time # <-- Nova biblioteca para gerir as pausas

def recolher_artigos_semantic(query_term, max_resultados=5):
    """
    Pesquisa artigos no Semantic Scholar com mecanismo de retry para evitar Erro 429.
    """
    print(f"🔍 A iniciar pesquisa no Semantic Scholar por: '{query_term}'")
    
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query_term,
        "limit": max_resultados,
        "fields": "paperId,title,abstract,authors,year,venue,externalIds"
    }

    max_tentativas = 3
    
    for tentativa in range(1, max_tentativas + 1):
        try:
            # Pausa de cortesia de 2 segundos antes de qualquer pedido
            time.sleep(2) 
            
            headers = {
                "User-Agent": "Projeto-Academico-RAG/1.0 (mailto:lucianodiass@gmail.com)"
            }
            
            response = requests.get(url, params=params, headers=headers)
            
            # Se o servidor nos der o Erro 429, fazemos uma pausa longa e tentamos novamente
            if response.status_code == 429:
                print(f"   ⚠️ Servidor ocupado (Erro 429). A aguardar 5 segundos... (Tentativa {tentativa}/{max_tentativas})")
                time.sleep(5)
                continue # Volta ao início do ciclo para tentar de novo
                
            # Se der outro erro qualquer, isto faz o script saltar para o "except"
            response.raise_for_status() 
            
            # Se chegou aqui, o pedido teve sucesso!
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

            return artigos_formatados # Devolve os artigos e sai da função

        except requests.exceptions.RequestException as e:
            print(f"❌ Erro ao contactar o Semantic Scholar na tentativa {tentativa}: {e}")
            if tentativa == max_tentativas:
                return [] # Se falhou a última tentativa, devolve lista vazia para não quebrar o Orquestrador
            time.sleep(3)
            
    return [] # Prevenção final