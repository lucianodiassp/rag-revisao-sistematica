import requests
import uuid
import xml.etree.ElementTree as ET

from backend.app.bibliographic_config import SOURCE_PUBMED, get_source_config
from backend.coleta.http_utils import get_with_retry, safe_request_error


def _adicionar_identificacao_pubmed(params, config):
    params = dict(params)
    if config.api_key:
        params["api_key"] = config.api_key.strip()
    if config.contact_email:
        params["email"] = config.contact_email
    if config.tool_name:
        params["tool"] = config.tool_name
    return params

def recolher_artigos_pubmed(query_term, max_resultados=10, raise_on_error=False):
    """
    Pesquisa artigos no PubMed (NCBI) e formata-os para o contrato de dados da equipa,
    extraindo o Abstract real por meio do serviço E-Fetch.
    """
    config = get_source_config(SOURCE_PUBMED)
    if not config.enabled:
        print("⏭️ PubMed está desativada na configuração de fontes bibliográficas.")
        return []
    print(f"🔍 A iniciar pesquisa no PubMed por: '{query_term}'")
    
    # 1. Pesquisa para obter os IDs (PMIDs)
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = _adicionar_identificacao_pubmed({
        "db": "pubmed",
        "term": query_term,
        "retmax": max_resultados,
        "retmode": "json"
    }, config)

    try:
        search_resp = get_with_retry(
            search_url,
            config,
            params=search_params,
        )
        search_resp.raise_for_status()
        id_list = search_resp.json().get("esearchresult", {}).get("idlist", [])

        if not id_list:
            print("❌ Nenhum artigo encontrado no PubMed.")
            return []

        print(f"✅ Encontrados {len(id_list)} PMIDs. A extrair detalhes e abstracts...")

        # 2. Obter os detalhes dos artigos usando os IDs encontrados (Metadados em JSON)
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        summary_params = _adicionar_identificacao_pubmed({
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json"
        }, config)

        summary_resp = get_with_retry(
            summary_url,
            config,
            params=summary_params,
        )
        summary_resp.raise_for_status()
        summary_data = summary_resp.json().get("result", {})

        # 3. Chamada ao E-Fetch para obter os Abstracts Reais (Retorno obrigatório em XML)
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        fetch_params = _adicionar_identificacao_pubmed({
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "xml"
        }, config)
        
        fetch_resp = get_with_retry(
            fetch_url,
            config,
            params=fetch_params,
        )
        fetch_resp.raise_for_status()
        
        # Mapeamento de Abstracts: PMID -> Texto do Abstract
        abstracts_mapeados = {}
        root = ET.fromstring(fetch_resp.content)
        
        for artigo_xml in root.findall('.//PubmedArticle'):
            pmid_el = artigo_xml.find('.//PMID')
            if pmid_el is not None and pmid_el.text:
                id_pmid = pmid_el.text
                
                # O PubMed pode dividir o abstract em múltiplos nós AbstractText (Introdução, Métodos, etc.)
                abstract_nodes = artigo_xml.findall('.//AbstractText')
                if abstract_nodes:
                    # Junta todos os blocos de texto preservando o conteúdo estruturado
                    texto_abstract = " ".join([node.text for node in abstract_nodes if node.text])
                    abstracts_mapeados[id_pmid] = texto_abstract
                else:
                    abstracts_mapeados[id_pmid] = "Abstract não disponível no PubMed."

        # 4. Formatação final combinando metadados e os abstracts reais
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

            # Recuperar o abstract real mapeado ou definir um fallback caso falte
            abstract_real = abstracts_mapeados.get(pmid, "Abstract indisponível.")

            # Construir o contrato de dados estruturado
            fontes_dict = {
                "sources": ["PubMed"],
                "external_ids": {
                    "doi": doi,
                    "pubmed": pmid
                },
                "metadata": {
                    "publication_year": artigo.get("pubdate", "")[:4], 
                    "authors": autores,
                    "journal_name": artigo.get("fulljournalname", "Revista não especificada"),
                    "language": "en"
                },
                "concepts": [] 
            }
            
            # Gerar UUID único para o banco de dados relacional
            id_interno = str(uuid.uuid4())
            
            artigos_formatados.append({
                "id": id_interno,
                "titulo": titulo,
                "abstract": abstract_real,
                "fontes_dict": fontes_dict
            })
            
            print(f"   -> Formatado com Abstract Real: {titulo[:50]}...")

        return artigos_formatados

    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao contactar o PubMed: {safe_request_error(e, config.api_key)}")
        if raise_on_error:
            raise
        return []
    except ET.ParseError as e:
        print(f"❌ Erro ao processar o XML de abstracts do PubMed: {e}")
        if raise_on_error:
            raise
        return []
