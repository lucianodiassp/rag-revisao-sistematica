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
            "outcome": "Desfechos esperados ou métricas"
        }},
        "inclusion_criteria": ["Critério 1", "Critério 2"],
        "exclusion_criteria": ["Critério 1", "Critério 2"],
        "search_string": "Uma string booleana rigorosa otimizada para PubMed/Scopus/IEEE usando AND/OR e parênteses."
    }}
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
