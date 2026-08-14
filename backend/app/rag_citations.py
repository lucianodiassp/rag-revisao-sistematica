"""Normalização e validação determinística das citações produzidas pelo RAG."""

import re


RESPOSTA_SEM_CONTEXTO = "Não tenho dados suficientes nos artigos recolhidos"
PADRAO_CITACAO_RAG = re.compile(
    r"\[([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s*,\s*p\.\s*(\d+)\]",
    flags=re.IGNORECASE,
)
PADRAO_REFERENCIA_INTERNA = re.compile(r"\[(\d{1,3})\]")


def formatar_citacao(paper_id, page_number):
    return f"[{paper_id}, p. {int(page_number)}]"


def validar_citacoes_rag(resposta, evidencias):
    """Aceita apenas artigo/página recuperados e desambigua referências internas."""
    resposta = str(resposta or "").strip()
    fontes_permitidas = {
        (str(item["paper_id"]).lower(), int(item["page_number"]))
        for item in evidencias or []
        if item.get("paper_id") and item.get("page_number") is not None
    }
    referencias_internas = PADRAO_REFERENCIA_INTERNA.findall(resposta)
    resposta = PADRAO_REFERENCIA_INTERNA.sub(
        lambda match: f"(referência bibliográfica nº {match.group(1)} citada no artigo)",
        resposta,
    )

    citacoes_validas = []
    citacoes_invalidas = []

    def _validar(match):
        paper_id = match.group(1).lower()
        pagina = int(match.group(2))
        if (paper_id, pagina) in fontes_permitidas:
            citacao = formatar_citacao(paper_id, pagina)
            citacoes_validas.append(citacao)
            return citacao
        citacoes_invalidas.append(match.group(0))
        return "(citação de fonte não validada removida)"

    resposta = PADRAO_CITACAO_RAG.sub(_validar, resposta)
    fontes_adicionadas = []
    sem_contexto = RESPOSTA_SEM_CONTEXTO.lower() in resposta.lower()
    if not citacoes_validas and fontes_permitidas and not sem_contexto:
        fontes_adicionadas = [
            formatar_citacao(paper_id, pagina)
            for paper_id, pagina in sorted(fontes_permitidas)
        ]
        resposta += (
            "\n\n**Aviso de rastreabilidade:** o modelo não vinculou as afirmações "
            "individualmente no formato exigido. Fontes recuperadas: "
            + "; ".join(fontes_adicionadas)
        )

    return resposta, {
        "valid_citations": list(dict.fromkeys(citacoes_validas)),
        "invalid_citations_removed": citacoes_invalidas,
        "internal_references_disambiguated": referencias_internas,
        "source_citations_appended": fontes_adicionadas,
        "allowed_sources": [
            {"paper_id": paper_id, "page_number": pagina}
            for paper_id, pagina in sorted(fontes_permitidas)
        ],
    }
