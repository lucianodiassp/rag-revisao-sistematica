import requests
import json
import uuid

def reconstruir_abstract_openalex(inverted_index):
    """
    Reconstrói o abstract original a partir do formato Inverted Index do OpenAlex.
    """
    if not inverted_index or not isinstance(inverted_index, dict):
        return "Abstract indisponível."
    
    try:
        # Descobrir o tamanho total do abstract (a maior posição no índice)
        posicoes_maximas = [pos for posicoes in inverted_index.values() for pos in posicoes]
        if not posicoes_maximas:
            return "Abstract indisponível."
            
        tamanho_total = max(posicoes_maximas) + 1
        
        # Criar uma lista vazia com esse tamanho
        palavras = [""] * tamanho_total
        
        # Preencher a lista colocando cada palavra na sua posição correta
        for palavra, posicoes in inverted_index.items():
            for pos in posicoes:
                palavras[pos] = palavra
                
        # Juntar tudo com espaços e remover espaços duplos
        texto_limpo = " ".join(palavras).strip()
        return texto_limpo
        
    except Exception as e:
        print(f"Erro ao reconstruir abstract do OpenAlex: {e}")
        return "Abstract indisponível."

def recolher_artigos_openalex(query_term, max_resultados=10):
    """
    Pesquisa artigos no OpenAlex e formata-os para o contrato de dados da equipa,
    reconstruindo o abstract a partir do Inverted Index.
    """
    print(f"🔍 A iniciar pesquisa no OpenAlex por: '{query_term}'")
    
    url = "https://api.openalex.org/works"
    
    params = {
        "search": query_term,
        "per-page": max_resultados,
        "mailto": "equipa_rag@teu_dominio.com" 
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status() 
        dados_brutos = response.json()
        
        resultados = dados_brutos.get("results", [])
        print(f"✅ Encontrados {len(resultados)} artigos. A formatar dados...")
        
        artigos_formatados = []
        
        for artigo in resultados:
            titulo = artigo.get("title")
            if not titulo: 
                continue
                
            # --- NOVA LÓGICA DE EXTRAÇÃO DO ABSTRACT ---
            abstract_invertido = artigo.get("abstract_inverted_index", {})
            abstract_real = reconstruir_abstract_openalex(abstract_invertido)
            
            # Extrair autores
            autores = [autor.get("author", {}).get("display_name") for autor in artigo.get("authorships", [])]
            
            # Extrair conceitos/palavras-chave (limitado aos 5 principais)
            conceitos = [conceito.get("display_name") for conceito in artigo.get("concepts", [])][:5]

            # Extração da revista
            local_primario = artigo.get("primary_location")
            fonte = local_primario.get("source") if local_primario else None
            nome_revista = fonte.get("display_name") if fonte else "Revista não especificada"

            # Construir o contrato de dados
            fontes_dict = {
                "sources": ["OpenAlex"],
                "external_ids": {
                    "doi": artigo.get("doi"),
                    "openalex": artigo.get("id")
                },
                "metadata": {
                    "publication_year": artigo.get("publication_year"),
                    "authors": autores,
                    "journal_name": nome_revista, 
                    "language": artigo.get("language", "en")
                },
                "concepts": conceitos
            }
            
            id_interno = str(uuid.uuid4())
            
            artigos_formatados.append({
                "id": id_interno,
                "titulo": titulo,
                "abstract": abstract_real, # <-- Guardamos o texto reconstruído aqui!
                "fontes_dict": fontes_dict
            })
            
            print(f"   -> Formatado: {titulo[:50]}...")

        return artigos_formatados

    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao contactar o OpenAlex: {e}")
        return []

if __name__ == "__main__":
    artigos_para_guardar = recolher_artigos_openalex("Retrieval-Augmented Generation", max_resultados=3)
    
    print("\n💾 Simulação de gravação na Base de Dados:")
    for art in artigos_para_guardar:
        print(f"A chamar salvar_artigo_coletado() para o ID: {art['id']}")
        
    print("\n✨ Ficheiro JSON de exemplo do primeiro artigo gerado:")
    if artigos_para_guardar:
        print(json.dumps(artigos_para_guardar[0]["fontes_dict"], indent=2, ensure_ascii=False))