import json
from backend.app.ai_config import TASK_FORMULATION, get_generation_config
from backend.app.ai_service import generate_content
from backend.app.database import log_interacao_agente


def estruturar_pergunta_pesquisa(pergunta_livre, project_id=None):
    """Transforma uma pergunta livre na estrutura PICO e gera a estratégia de busca."""
    prompt = f"""
    És um metodologista especialista em Revisões Sistemáticas da Literatura.
    A tua tarefa é receber a pergunta de pesquisa inicial do utilizador e estruturá-la cientificamente.
    
    Pergunta inicial do utilizador: "{pergunta_livre}"
    
    Por favor, analisa a pergunta e devolve OBRIGATORIAMENTE um JSON com a seguinte estrutura:
    {{
        "pico": {{
            "population": "Definição da População ou Problema",
            "intervention": "Definição da Intervenção ou Método",
            "comparison": "Comparação (se aplicável, ou 'Não se aplica')",
            "outcome": "Desfechos esperados ou métricas",
            "study_design": "Desenhos de estudo adequados (PICOS)"
        }},
        "eligibility": {{
            "year_from": null,
            "year_to": null,
            "languages": ["Idioma aceito"],
            "publication_types": ["Tipo de publicação aceito"],
            "study_designs": ["Desenho de estudo aceito"]
        }},
        "inclusion_criteria": ["Condição objetiva de inclusão 1", "Condição objetiva de inclusão 2"],
        "exclusion_criteria": ["Condição objetiva de exclusão 1", "Condição objetiva de exclusão 2"],
        "search_concepts": [
            {{"concept": "População ou problema", "terms": ["termo livre", "sinônimo"]}},
            {{"concept": "Intervenção ou método", "terms": ["termo livre", "sinônimo"]}}
        ],
        "search_string": "String booleana geral rigorosa usando AND/OR e parênteses",
        "source_search_strings": {{
            "openalex": "Consulta adequada ao OpenAlex",
            "pubmed": "Consulta adequada ao PubMed, incluindo MeSH quando pertinente",
            "semantic_scholar": "Consulta adequada ao Semantic Scholar"
        }}
    }}

    Os critérios devem ser observáveis no título/resumo sempre que possível. Não exclua
    automaticamente por acesso ao texto integral. Diferencie conceitos usados para ampliar
    a busca de condições aplicadas posteriormente na triagem.
    """
    
    try:
        resposta = generate_content(
            TASK_FORMULATION,
            contents=prompt,
            response_mime_type="application/json",
        )
        resultado = json.loads(resposta.text)
        if project_id:
            log_interacao_agente(
                project_id,
                "question_formulation_agent",
                {"question": pergunta_livre},
                resultado,
                get_generation_config(TASK_FORMULATION).metadata(),
            )
        return resultado
    except Exception as e:
        print(f"Erro ao estruturar pergunta: {e}")
        return None
