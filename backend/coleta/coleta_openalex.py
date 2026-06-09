import requests
import json
import uuid

# IMPORTANTE: Vamos simular a importação da função da Pessoa 3.
# Se o ficheiro database.py estiver na pasta 'app', garante que o caminho está correto.
# from app.database import salvar_artigo_coletado

def recolher_artigos_openalex(query_term, max_resultados=5):
    """
    Pesquisa artigos no OpenAlex e formata-os para o contrato de dados da equipa.
    """
    print(f"🔍 A iniciar pesquisa no OpenAlex por: '{query_term}'")
    
    # URL base da API do OpenAlex para trabalhos (works)
    url = "https://api.openalex.org/works"
    
    # Parâmetros da pesquisa
    params = {
        "search": query_term,
        "per-page": max_resultados,
        # O email coloca-nos na 'Polite Pool' (mais rápido e sem bloqueios)
        "mailto": "equipa_rag@teu_dominio.com" 
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status() # Verifica se houve algum erro HTTP
        dados_brutos = response.json()
        
        resultados = dados_brutos.get("results", [])
        print(f"✅ Encontrados {len(resultados)} artigos. A formatar dados...")
        
        artigos_formatados = []
        
        for artigo in resultados:
            # 1. Extração segura de dados (usando .get() para evitar erros se o campo não existir)
            titulo = artigo.get("title")
            if not titulo: # Se não tem título, ignoramos (lixo da API)
                continue
                
            # O OpenAlex devolve o abstract num formato invertido estranho, isto limpa ou deixa vazio
            abstract_invertido = artigo.get("abstract_inverted_index", {})
            abstract = "Abstract indisponível." if not abstract_invertido else "Abstract extraído do índice (simplificado para este exemplo)."
            
            # Extrair autores
            autores = [autor.get("author", {}).get("display_name") for autor in artigo.get("authorships", [])]
            
            # Extrair conceitos/palavras-chave (limitado aos 5 principais)
            conceitos = [conceito.get("display_name") for conceito in artigo.get("concepts", [])][:5]

            # --- NOVA EXTRAÇÃO SEGURA PARA A REVISTA ---
            local_primario = artigo.get("primary_location")
            fonte = local_primario.get("source") if local_primario else None
            nome_revista = fonte.get("display_name") if fonte else "Revista não especificada"

            # 2. Construir o NOSSO contrato de dados (O JSON que acordámos)
            fontes_dict = {
                "sources": ["OpenAlex"],
                "external_ids": {
                    "doi": artigo.get("doi"),
                    "openalex": artigo.get("id")
                },
                "metadata": {
                    "publication_year": artigo.get("publication_year"),
                    "authors": autores,
                    "journal_name": nome_revista, # <-- Usamos a nossa variável segura aqui
                    "language": artigo.get("language", "en")
                },
                "concepts": conceitos
            }
            
            # Gerar um UUID único para a nossa base de dados (exigência da Pessoa 3)
            id_interno = str(uuid.uuid4())
            
            # Adicionar à nossa lista processada
            artigos_formatados.append({
                "id": id_interno,
                "titulo": titulo,
                "abstract": abstract,
                "fontes_dict": fontes_dict
            })
            
            print(f"   -> Formatado: {titulo[:50]}...")

        return artigos_formatados

    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao contactar o OpenAlex: {e}")
        return []

# ==========================================
# TESTE DE EXECUÇÃO
# ==========================================
if __name__ == "__main__":
    # 1. Fazemos a recolha (limitado a 3 para testar)
    artigos_para_guardar = recolher_artigos_openalex("Retrieval-Augmented Generation", max_resultados=3)
    
    print("\n💾 Simulação de gravação na Base de Dados:")
    # 2. Enviamos para a função da Pessoa 3
    for art in artigos_para_guardar:
        print(f"A chamar salvar_artigo_coletado() para o ID: {art['id']}")
        # Aqui, na prática, faríamos o 'uncomment' desta linha:
        # salvar_artigo_coletado(art["id"], art["titulo"], art["abstract"], art["fontes_dict"])
        
    print("\n✨ Ficheiro JSON de exemplo do primeiro artigo gerado:")
    if artigos_para_guardar:
        print(json.dumps(artigos_para_guardar[0]["fontes_dict"], indent=2, ensure_ascii=False))