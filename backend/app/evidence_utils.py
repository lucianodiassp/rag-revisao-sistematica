import re


SCHEMA_VERSION = "traceable-v1"
FIELD_TYPES = {
    "objective": "text",
    "method": "text",
    "dataset": "text",
    "metrics": "list",
    "main_results": "text",
    "limitations": "list",
}
NOT_REPORTED = "Não reportado"


def normalizar_trecho(texto):
    """Normaliza apenas espaços e caixa para validar uma citação literal."""
    return re.sub(r"\s+", " ", str(texto or "")).strip().casefold()


def _valor_ausente(valor, tipo):
    if tipo == "list":
        return not valor
    return not str(valor or "").strip() or normalizar_trecho(valor) in {
        "nao reportado",
        "não reportado",
        "n/a",
    }


def _normalizar_valor(valor, tipo):
    if tipo == "list":
        if isinstance(valor, str):
            if _valor_ausente(valor, "text"):
                return []
            valor = [item.strip() for item in valor.split(";")]
        if not isinstance(valor, list):
            return []
        return [str(item).strip() for item in valor if str(item).strip()]

    if isinstance(valor, list):
        valor = "; ".join(str(item).strip() for item in valor if str(item).strip())
    valor = str(valor or "").strip()
    return valor if valor else NOT_REPORTED


def validar_extracao_rastreavel(resposta, chunks):
    """
    Valida a resposta do LLM contra os chunks realmente enviados.

    `chunks` deve ser um iterável com id, chunk_text e page_number. Uma evidência
    só é mantida quando o trecho citado aparece literalmente no chunk indicado.
    """
    chunks_por_id = {str(chunk["id"]): chunk for chunk in chunks}
    resposta = resposta if isinstance(resposta, dict) else {}
    resultado = {"schema_version": SCHEMA_VERSION}
    avisos = []

    for campo, tipo in FIELD_TYPES.items():
        bruto = resposta.get(campo, {})
        if not isinstance(bruto, dict):
            bruto = {"value": bruto, "evidence": [], "confidence": 0}

        valor = _normalizar_valor(bruto.get("value"), tipo)
        evidencias_validas = []
        vistos = set()
        evidencias = bruto.get("evidence") or []
        if not isinstance(evidencias, list):
            evidencias = []

        for evidencia in evidencias:
            if not isinstance(evidencia, dict):
                continue
            chunk_id = str(evidencia.get("chunk_id") or "")
            quote = re.sub(r"\s+", " ", str(evidencia.get("quote") or "")).strip()
            chunk = chunks_por_id.get(chunk_id)
            if not chunk or not quote:
                continue
            if normalizar_trecho(quote) not in normalizar_trecho(chunk.get("chunk_text")):
                continue

            chave = (chunk_id, normalizar_trecho(quote))
            if chave in vistos:
                continue
            vistos.add(chave)
            evidencias_validas.append(
                {
                    "chunk_id": chunk_id,
                    "page": chunk.get("page_number"),
                    "quote": quote,
                }
            )

        if not _valor_ausente(valor, tipo) and not evidencias_validas:
            avisos.append(f"{campo}: valor removido por não possuir citação literal válida")
            valor = [] if tipo == "list" else NOT_REPORTED

        try:
            confianca = float(bruto.get("confidence", 0))
        except (TypeError, ValueError):
            confianca = 0.0
        confianca = max(0.0, min(1.0, confianca)) if evidencias_validas else 0.0

        resultado[campo] = {
            "value": valor,
            "evidence": evidencias_validas,
            "confidence": confianca,
        }

    escopo = resposta.get("document_scope") or {}
    resultado["document_scope"] = {
        "chunks_used": len(chunks_por_id),
        "truncated": bool(escopo.get("truncated", False)),
    }
    resultado["validation_warnings"] = avisos
    return resultado


def achatar_extracao(extracao):
    """Converte extrações rastreáveis ou legadas para a forma editável/exportável."""
    extracao = extracao if isinstance(extracao, dict) else {}
    resultado = {}
    for campo, tipo in FIELD_TYPES.items():
        bruto = extracao.get(campo, [] if tipo == "list" else NOT_REPORTED)
        valor = bruto.get("value") if isinstance(bruto, dict) else bruto
        resultado[campo] = _normalizar_valor(valor, tipo)
    return resultado


def listar_fontes_extracao(extracao):
    """Produz linhas prontas para persistência na tabela de fontes."""
    linhas = []
    extracao = extracao if isinstance(extracao, dict) else {}
    for campo in FIELD_TYPES:
        bloco = extracao.get(campo) or {}
        if not isinstance(bloco, dict):
            continue
        for ordem, evidencia in enumerate(bloco.get("evidence") or []):
            linhas.append(
                {
                    "field_name": campo,
                    "evidence_order": ordem,
                    "chunk_id": evidencia["chunk_id"],
                    "page_number": evidencia.get("page"),
                    "quote": evidencia["quote"],
                }
            )
    return linhas
