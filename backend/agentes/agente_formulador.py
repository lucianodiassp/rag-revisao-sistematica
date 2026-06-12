import os
import json
from dotenv import load_dotenv, find_dotenv
from google import genai
from google.genai import types

load_dotenv(find_dotenv())
cliente = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
NOME_MODELO = 'gemini-2.5-flash'

def estruturar_pergunta_pesquisa(pergunta_livre):
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
        resposta = cliente.models.generate_content(
            model=NOME_MODELO,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2, # Baixa temperatura para manter o rigor metodológico
            ),
        )
        return json.loads(resposta.text)
    except Exception as e:
        print(f"Erro ao estruturar pergunta: {e}")
        return None