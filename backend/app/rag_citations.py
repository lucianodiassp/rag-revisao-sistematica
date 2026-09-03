"""Normalização e validação determinística das citações produzidas pelo RAG."""

import re


RESPOSTA_SEM_CONTEXTO = "Não tenho dados suficientes nos artigos recolhidos"
UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
PADRAO_CITACAO_RAG = re.compile(
    rf"\[({UUID_PATTERN})\s*,\s*p\.\s*(\d+)(?:\s*,\s*visual\s+({UUID_PATTERN}))?\]",
    flags=re.IGNORECASE,
)
PADRAO_REFERENCIA_INTERNA = re.compile(r"\[(\d{1,3})\]")


def formatar_citacao(paper_id, page_number, artifact_id=None):
    visual = f", visual {artifact_id}" if artifact_id else ""
    return f"[{paper_id}, p. {int(page_number)}{visual}]"


def validar_citacoes_rag(resposta, evidencias):
    """Aceita apenas artigo/página recuperados e desambigua referências internas."""
    resposta = str(resposta or "").strip()
    fontes_permitidas = {
        (str(item["paper_id"]).lower(), int(item["page_number"]),
         str(item.get("artifact_id") or "").lower() if item.get("source_type") == "visual_interpretation" else "")
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
        artifact_id = (match.group(3) or "").lower()
        if (paper_id, pagina, artifact_id) in fontes_permitidas:
            citacao = formatar_citacao(paper_id, pagina, artifact_id)
            citacoes_validas.append(citacao)
            return citacao
        citacoes_invalidas.append(match.group(0))
        return "(citação de fonte não validada removida)"

    resposta = PADRAO_CITACAO_RAG.sub(_validar, resposta)
    fontes_adicionadas = []
    sem_contexto = RESPOSTA_SEM_CONTEXTO.lower() in resposta.lower()
    if not citacoes_validas and fontes_permitidas and not sem_contexto:
        fontes_adicionadas = [
            formatar_citacao(paper_id, pagina, artifact_id)
            for paper_id, pagina, artifact_id in sorted(fontes_permitidas)
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
            {"paper_id": paper_id, "page_number": pagina,
             **({"artifact_id": artifact_id, "source_type": "visual_interpretation"} if artifact_id else {})}
            for paper_id, pagina, artifact_id in sorted(fontes_permitidas)
        ],
    }
