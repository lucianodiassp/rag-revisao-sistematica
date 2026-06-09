import requests
import uuid

def recolher_artigos_pubmed(query_term, max_resultados=5):
    """
    Pesquisa artigos no PubMed (NCBI) e formata-os para o contrato de dados da equipa.
    """
    print(f"🔍 A iniciar pesquisa no PubMed por: '{query_term}'")
    
    # 1. Pesquisa para obter os IDs (PMIDs)
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "pubmed",
        "term": query_term,
        "retmax": max_resultados,
        "retmode": "json"
    }

    try:
        search_resp = requests.get(search_url, params=search_params)
        search_resp.raise_for_status()
        id_list = search_resp.json().get("esearchresult", {}).get("idlist", [])

        if not id_list:
            print("❌ Nenhum artigo encontrado no PubMed.")
            return []

        print(f"✅ Encontrados {len(id_list)} PMIDs. A extrair detalhes...")

        # 2. Obter os detalhes dos artigos usando os IDs encontrados
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        summary_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json"
        }

        summary_resp = requests.get(summary_url, params=summary_params)
        summary_resp.raise_for_status()
        summary_data = summary_resp.json().get("result", {})

        artigos_formatados = []

        for pmid in id_list:
            artigo = summary_data.get(pmid)
            if not artigo:
                continue

            titulo = artigo.get("title", "Título indisponível")
            
            # Extrair autores
            autores = [autor.get("name") for autor in artigo.get("authors", [])]
            
            # Tentar extrair o DOI se existir na lista de IDs do artigo
            doi = ""
            for article_id in artigo.get("articleids", []):
                if article_id.get("idtype") == "doi":
                    doi = article_id.get("value")

            # 3. Construir o NOSSO contrato de dados
            fontes_dict = {
                "sources": ["PubMed"],
                "external_ids": {
                    "doi": doi,
                    "pubmed": pmid
                },
                "metadata": {
                    "publication_year": artigo.get("pubdate", "")[:4], # Pega apenas o ano
                    "authors": autores,
                    "journal_name": artigo.get("fulljournalname", "Revista não especificada"),
                    "language": "en"
                },
                "concepts": [] # O PubMed summary não devolve conceitos estruturados tão facilmente
            }
            
            # Gerar UUID único
            id_interno = str(uuid.uuid4())
            
            artigos_formatados.append({
                "id": id_interno,
                "titulo": titulo,
                "abstract": "Abstract via PubMed E-Summary (Requer E-Fetch para texto completo).",
                "fontes_dict": fontes_dict
            })
            
            print(f"   -> Formatado: {titulo[:50]}...")

        return artigos_formatados

    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao contactar o PubMed: {e}")
        return []