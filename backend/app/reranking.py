"""Reranking rastreável das evidências recuperadas pelo RRF."""

import json

from backend.app.ai_config import TASK_RERANKING, get_ai_settings, get_reranking_config
from backend.app.ai_service import generate_content
from backend.app.database import log_interacao_agente


STATUS_SUCCESS = "success"
STATUS_FALLBACK = "fallback_rrf"
STATUS_DISABLED = "disabled"
FUSION_RANK_CONSTANT = 60


def _candidato_auditavel(candidato, incluir_texto=False):
    item = {
        "candidate_id": candidato["candidate_id"],
        "chunk_id": str(candidato["chunk_id"]),
        "paper_id": str(candidato["paper_id"]),
        "paper_title": candidato.get("paper_title"),
        "page_number": int(candidato["page_number"]),
        "original_rank": int(candidato["original_rank"]),
        "rrf_score": float(candidato["rrf_score"]),
    }
    if incluir_texto:
        item["snippet"] = str(candidato["text"])[:1000]
    if candidato.get("rerank_rank") is not None:
        item["rerank_rank"] = int(candidato["rerank_rank"])
    if "rerank_score" in candidato:
        item["rerank_score"] = candidato.get("rerank_score")
    if "rerank_reason" in candidato:
        item["rerank_reason"] = candidato.get("rerank_reason")
    if candidato.get("model_rank") is not None:
        item["model_rank"] = int(candidato["model_rank"])
    if candidato.get("fusion_score") is not None:
        item["fusion_score"] = float(candidato["fusion_score"])
    return item


def _erro_seguro(erro):
    mensagem = str(erro).strip() or erro.__class__.__name__
    try:
        segredo = get_ai_settings().api_key
    except Exception:
        segredo = None
    if segredo:
        mensagem = mensagem.replace(str(segredo), "[REDACTED]")
    return f"{erro.__class__.__name__}: {mensagem}"[:500]


def _selecionar_por_rrf(candidatos, limite):
    selecionados = []
    for indice, candidato in enumerate(candidatos[:limite], 1):
        item = dict(candidato)
        item.update(
            {
                "rerank_rank": indice,
                "model_rank": None,
                "rerank_score": None,
                "fusion_score": None,
                "rerank_reason": "Ordem original do RRF utilizada.",
            }
        )
        selecionados.append(item)
    return selecionados


def _normalizar_ranking(resposta, candidatos, limite):
    dados = json.loads(resposta)
    ranking = dados.get("ranking") if isinstance(dados, dict) else None
    if not isinstance(ranking, list):
        raise ValueError("A resposta do reranker não contém uma lista 'ranking'.")

    por_id = {item["candidate_id"]: item for item in candidatos}
    classificados = []
    usados = set()
    for item in ranking:
        if not isinstance(item, dict):
            continue
        candidate_id = str(item.get("candidate_id") or "")
        if candidate_id not in por_id or candidate_id in usados:
            continue
        try:
            score = float(item.get("relevance_score"))
        except (TypeError, ValueError):
            continue
        if not 0 <= score <= 100:
            continue
        usados.add(candidate_id)
        classificados.append(
            (
                score,
                por_id[candidate_id]["original_rank"],
                candidate_id,
                " ".join(str(item.get("reason") or "Sem justificativa.").split())[:500],
            )
        )

    if not classificados:
        raise ValueError("O reranker não devolveu candidatos válidos.")

    classificados.sort(key=lambda item: (-item[0], item[1]))
    # Se o modelo omitir algum candidato, ele permanece depois dos classificados,
    # respeitando a ordem RRF e garantindo o limite final configurado.
    for candidato in candidatos:
        if candidato["candidate_id"] not in usados:
            classificados.append(
                (
                    -1.0,
                    candidato["original_rank"],
                    candidato["candidate_id"],
                    "Candidato omitido pelo modelo; mantido após os itens classificados.",
                )
            )

    selecionados = []
    for model_rank, (score, _, candidate_id, reason) in enumerate(classificados[:limite], 1):
        item = dict(por_id[candidate_id])
        item.update(
            {
                "model_rank": model_rank,
                "rerank_score": None if score < 0 else round(score, 2),
                "rerank_reason": reason,
            }
        )
        selecionados.append(item)
    return selecionados


def fundir_rankings(ranking_modelo, rrf_weight, limite=None):
    """Combina as posições do RRF e da IA por Reciprocal Rank Fusion ponderado."""
    peso_rrf = min(1.0, max(0.0, float(rrf_weight or 0.0)))
    classificados = []
    for indice, candidato in enumerate(ranking_modelo or [], 1):
        item = dict(candidato)
        original_rank = int(item.get("original_rank") or indice)
        model_rank = int(item.get("model_rank") or indice)
        fusion_score = (
            peso_rrf / (FUSION_RANK_CONSTANT + original_rank)
            + (1.0 - peso_rrf) / (FUSION_RANK_CONSTANT + model_rank)
        )
        classificados.append((fusion_score, model_rank, original_rank, item))

    classificados.sort(key=lambda value: (-value[0], value[1], value[2]))
    limite = len(classificados) if limite is None else min(int(limite), len(classificados))
    resultado = []
    for rerank_rank, (fusion_score, _model_rank, _original_rank, item) in enumerate(
        classificados[:limite], 1
    ):
        item["rerank_rank"] = rerank_rank
        item["fusion_score"] = round(fusion_score, 10)
        resultado.append(item)
    return resultado


def reranquear_candidatos(
    pergunta,
    candidatos,
    project_id,
    *,
    config=None,
    generator=None,
    logger=None,
):
    """Reordena candidatos e devolve seleção e trilha de auditoria."""
    config = config or get_reranking_config()
    generator = generator or generate_content
    logger = logger or log_interacao_agente
    limite_final = min(int(config.final_limit or 4), len(candidatos))
    candidatos = [dict(item) for item in candidatos]
    ranking_inicial = [_candidato_auditavel(item, incluir_texto=True) for item in candidatos]

    if not candidatos:
        return [], {
            "status": STATUS_DISABLED if not config.enabled else STATUS_SUCCESS,
            "initial_ranking": [],
            "model_ranking": [],
            "reranked_ranking": [],
            "final_ranking": [],
            "error": None,
            "configuration": config.metadata(),
        }

    erro = None
    if not config.enabled:
        status = STATUS_DISABLED
        ranking_modelo = []
        ranking_completo = _selecionar_por_rrf(candidatos, len(candidatos))
        selecionados = ranking_completo[:limite_final]
    else:
        candidatos_prompt = [
            {
                "candidate_id": item["candidate_id"],
                "paper_id": str(item["paper_id"]),
                "paper_title": item.get("paper_title"),
                "page_number": int(item["page_number"]),
                "text": str(item["text"])[:3000],
            }
            for item in candidatos
        ]
        prompt = f"""
Você é um reranker de evidências para revisão sistemática da literatura.
Avalie somente a relevância de cada trecho para responder à pergunta, sem responder à pergunta.
Considere correspondência conceitual, especificidade e presença de evidência direta.

PERGUNTA:
{pergunta}

CANDIDATOS:
{json.dumps(candidatos_prompt, ensure_ascii=False)}

Retorne JSON válido no formato:
{{"ranking":[{{"candidate_id":"c1","relevance_score":95,"reason":"Evidência diretamente relacionada."}}]}}

Regras:
- inclua todos os candidate_id recebidos uma única vez;
- relevance_score deve estar entre 0 e 100;
- ordene do mais relevante para o menos relevante;
- use uma justificativa curta baseada apenas no trecho.
"""
        try:
            resposta = generator(
                TASK_RERANKING,
                contents=prompt,
                response_mime_type="application/json",
            )
            ranking_modelo = _normalizar_ranking(
                resposta.text, candidatos, len(candidatos)
            )
            ranking_completo = fundir_rankings(
                ranking_modelo,
                config.rrf_weight,
            )
            selecionados = ranking_completo[:limite_final]
            status = STATUS_SUCCESS
        except Exception as excecao:
            status = STATUS_FALLBACK
            erro = _erro_seguro(excecao)
            ranking_modelo = []
            ranking_completo = _selecionar_por_rrf(candidatos, len(candidatos))
            selecionados = ranking_completo[:limite_final]

    ranking_final = [_candidato_auditavel(item) for item in selecionados]
    ranking_ia = [_candidato_auditavel(item) for item in ranking_modelo]
    ranking_reranqueado = [_candidato_auditavel(item) for item in ranking_completo]
    trace = {
        "status": status,
        "initial_ranking": ranking_inicial,
        "model_ranking": ranking_ia,
        "reranked_ranking": ranking_reranqueado,
        "final_ranking": ranking_final,
        "error": erro,
        "configuration": config.metadata(),
    }
    logger(
        str(project_id),
        "reranking_agent",
        {
            "question": pergunta,
            "candidates": ranking_inicial,
            "candidate_count": len(candidatos),
        },
        {
            "status": status,
            "model_ranking": ranking_ia,
            "selected": ranking_final,
            "selected_count": len(selecionados),
            "fallback_error": erro,
        },
        config.metadata(),
    )
    return selecionados, trace
