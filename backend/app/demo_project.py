"""Carga reproduzível de um projeto demonstrativo, sem chamadas externas de IA.

Os metadados representam publicações reais. Para manter o repositório leve e não
redistribuir artigos integrais, a carga cria cartões PDF locais com atribuição,
uma síntese editorial e um único trecho curto da publicação. Esses cartões servem
somente para demonstrar rastreabilidade, revisão humana e exportação.
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path

import fitz
from psycopg2.extras import Json

from backend.app.evidence_utils import FIELD_TYPES, NOT_REPORTED, SCHEMA_VERSION


DEMO_SEED_ID = "ml-screening-demo-v1"
DEMO_SEED_VERSION = 1
DEMO_PROJECT_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DEMO_SEED_ID}:project"))
DEMO_PROJECT_TITLE = "Demonstração — IA na triagem de revisões sistemáticas"
DEMO_QUESTION = (
    "Quais benefícios, limitações e cuidados metodológicos são relatados no uso "
    "de aprendizado de máquina para apoiar a triagem de estudos em revisões sistemáticas?"
)


def _stable_id(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DEMO_SEED_ID}:{label}"))


DEMO_PROTOCOL = {
    "pico": {
        "population": "Registros recuperados para revisões sistemáticas e sínteses de evidências",
        "intervention": "Triagem apoiada por aprendizado de máquina, IA ou mineração de texto",
        "comparison": "Triagem manual convencional ou dupla triagem humana",
        "outcome": "Recall, precisão, redução de trabalho, confiabilidade e segurança metodológica",
    },
    "inclusion_criteria": [
        "Estudos sobre automação ou apoio computacional à triagem de literatura",
        "Aplicação em revisão sistemática, revisão de escopo ou síntese de evidências",
        "Relato de desempenho, economia de trabalho ou cuidados metodológicos",
        "Publicação em inglês ou português a partir de 2020",
    ],
    "exclusion_criteria": [
        "Uso de IA para rastreamento clínico sem automação da revisão de literatura",
        "Estudos sem relação com seleção ou priorização de publicações",
        "Editorial sem descrição de método, resultado ou recomendação",
    ],
    "search_string": (
        '("systematic review" OR "evidence synthesis") AND '
        '("machine learning" OR "artificial intelligence" OR "text mining") AND '
        '(screening OR prioritization)'
    ),
    "audit_questions": [
        "A automação preserva recall elevado?",
        "Quais riscos exigem validação humana?",
        "Há redução mensurável do trabalho de triagem?",
    ],
    "_demo": {
        "seed_id": DEMO_SEED_ID,
        "seed_version": DEMO_SEED_VERSION,
        "data_kind": "real_metadata_with_demo_evidence_cards",
        "external_ai_executed": False,
        "notice": (
            "Projeto exclusivamente demonstrativo. Os PDFs são cartões de evidência "
            "e não substituem a leitura dos artigos integrais."
        ),
    },
}


PAPER_SPECS = [
    {
        "key": "feng_2022",
        "title": (
            "Automated medical literature screening using artificial intelligence: "
            "a systematic review and meta-analysis"
        ),
        "doi": "10.1093/jamia/ocac066",
        "year": 2022,
        "authors": [
            "Yunying Feng",
            "Siyu Liang",
            "Yuelun Zhang",
            "Shi Chen",
            "Qing Wang",
            "Tianze Huang",
            "Feng Sun",
            "Xiaoqing Liu",
            "Huijuan Zhu",
            "Hui Pan",
        ],
        "pmid": "35641139",
        "pmcid": "PMC9277646",
        "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9277646/",
        "abstract": (
            "Revisão sistemática e metanálise sobre métodos de IA para a triagem "
            "automatizada de literatura médica, tomando decisões humanas como referência."
        ),
        "evidence_field": "objective",
        "evidence_value": (
            "Investigar a aplicação e a acurácia de métodos de IA na triagem automatizada "
            "de literatura médica para revisões sistemáticas."
        ),
        "quote": (
            "We aim to investigate the application and accuracy of artificial intelligence "
            "methods for automated medical literature screening for systematic reviews."
        ),
        "confidence": 0.99,
        "review_status": "approved",
    },
    {
        "key": "callaghan_2020",
        "title": "Statistical stopping criteria for automated screening in systematic reviews",
        "doi": "10.1186/s13643-020-01521-4",
        "year": 2020,
        "authors": ["Max W Callaghan", "Finn Müller-Hansen"],
        "pmcid": "PMC7700715",
        "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7700715/",
        "abstract": (
            "Estudo metodológico sobre critérios estatísticos de parada para triagem "
            "com aprendizado ativo, equilibrando recall desejado, confiança e esforço humano."
        ),
        "evidence_field": "main_results",
        "evidence_value": (
            "Critérios estatísticos flexíveis podem reduzir trabalho ao controlar, com nível "
            "de confiança explícito, o risco de não atingir o recall pretendido."
        ),
        "quote": (
            "offer real work reductions on the basis of rejecting a hypothesis of having "
            "missed a given recall target with a given level of confidence."
        ),
        "confidence": 0.97,
        "review_status": "approved",
    },
    {
        "key": "pham_2021",
        "title": (
            "Text mining to support abstract screening for knowledge syntheses: "
            "a semi-automated workflow"
        ),
        "doi": "10.1186/s13643-021-01700-x",
        "year": 2021,
        "authors": [
            "Ba' Pham",
            "Jelena Jovanovic",
            "Ebrahim Bagheri",
            "Jesmin Antony",
            "Huda Ashoor",
            "Tam T. Nguyen",
            "Patricia Rios",
            "Reid Robson",
            "Sonia M. Thomas",
            "Jennifer Watt",
            "Sharon E. Straus",
            "Andrea C. Tricco",
        ],
        "pmcid": "PMC8152711",
        "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC8152711/",
        "abstract": (
            "Fluxo semiautomatizado de mineração de texto e classificação, avaliado em "
            "uma revisão sistemática e uma revisão de escopo de grande porte."
        ),
        "evidence_field": "metrics",
        "evidence_value": [
            "Sensibilidade: 88%/89%",
            "Especificidade: 99%/99%",
            "Precisão: 71%/72%",
            "Redução de trabalho: 63%/55%",
        ],
        "quote": (
            "the workflow attained 88%/89% sensitivity, 99%/99% specificity, "
            "71%/72% precision, and 63%/55% workload reduction"
        ),
        "confidence": 0.99,
        "review_status": "approved",
    },
    {
        "key": "chappell_2023",
        "title": "Machine learning for accelerating screening in evidence reviews",
        "doi": "10.1002/cesm.12021",
        "year": 2023,
        "authors": [
            "Mary Chappell",
            "Mary Edwards",
            "Deborah Watkins",
            "Christopher Marshall",
            "Sara Graziadio",
        ],
        "pmcid": "PMC11795896",
        "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11795896/",
        "abstract": (
            "Síntese metodológica sobre ferramentas de aprendizado de máquina para "
            "priorização de registros e redução do trabalho em revisões de evidências."
        ),
        "evidence_field": "limitations",
        "evidence_value": [
            "O ganho de trabalho deve ser avaliado em conjunto com a possível perda de sensibilidade."
        ],
        "quote": (
            "the trade-off between workload savings and lost sensitivity needs to be "
            "considered before their use in each new review."
        ),
        "confidence": 0.96,
        "review_status": "corrected",
    },
    {
        "key": "anderson_2022",
        "title": (
            "Independent External Validation of Artificial Intelligence Algorithms for "
            "Automated Interpretation of Screening Mammography: A Systematic Review"
        ),
        "doi": "10.1016/j.jacr.2021.11.008",
        "year": 2022,
        "authors": [
            "Anna W Anderson",
            "M Luke Marinovich",
            "Nehmat Houssami",
            "Kathryn P Lowry",
            "Joann G Elmore",
            "Diana S M Buist",
            "Solveig Hofvind",
            "Christoph I Lee",
        ],
        "pmid": "35065909",
        "pmcid": "PMC8857031",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/35065909/",
        "abstract": (
            "Revisão sobre validação externa de algoritmos que interpretam mamografias. "
            "O objeto é rastreamento clínico, e não automação da triagem bibliográfica."
        ),
        "excluded": True,
    },
]


RETRIEVED_SPECS = [
    {"key": "pubmed_feng", "paper": "feng_2022", "source": "PubMed", "action": "auto_create"},
    {"key": "openalex_feng", "paper": "feng_2022", "source": "OpenAlex", "action": "auto_merge"},
    {
        "key": "semantic_callaghan",
        "paper": "callaghan_2020",
        "source": "Semantic Scholar",
        "action": "auto_create",
    },
    {"key": "pubmed_callaghan", "paper": "callaghan_2020", "source": "PubMed", "action": "auto_merge"},
    {"key": "pubmed_pham", "paper": "pham_2021", "source": "PubMed", "action": "auto_create"},
    {"key": "openalex_chappell", "paper": "chappell_2023", "source": "OpenAlex", "action": "auto_create"},
    {
        "key": "semantic_anderson",
        "paper": "anderson_2022",
        "source": "Semantic Scholar",
        "action": "auto_create",
    },
]


GOLDEN_SPECS = [
    {
        "key": "beneficio",
        "question": "Que benefício os critérios estatísticos de parada oferecem na triagem automatizada?",
        "paper": "callaghan_2020",
        "grade": 3,
    },
    {
        "key": "metricas",
        "question": "Quais métricas foram relatadas no fluxo semiautomatizado de mineração de texto?",
        "paper": "pham_2021",
        "grade": 3,
    },
    {
        "key": "objetivo",
        "question": "Qual foi o objetivo da revisão sobre triagem automatizada de literatura médica?",
        "paper": "feng_2022",
        "grade": 3,
    },
    {
        "key": "cuidado",
        "question": "Qual cuidado metodológico é indicado ao buscar redução de trabalho com aprendizado de máquina?",
        "paper": "chappell_2023",
        "grade": 3,
    },
    {
        "key": "recusa",
        "question": "Qual é o consumo de combustível de uma aeronave comercial transatlântica?",
        "expected_refusal": True,
        "notes": "Pergunta deliberadamente fora do escopo do projeto demonstrativo.",
    },
]


def build_demo_dataset() -> dict:
    """Monta a carga em memória, com identificadores determinísticos e auditáveis."""
    papers = []
    paper_by_key = {}
    for raw_spec in PAPER_SPECS:
        spec = deepcopy(raw_spec)
        spec["id"] = _stable_id(f"paper:{spec['key']}")
        spec["screening_id"] = _stable_id(f"screening:{spec['key']}")
        if not spec.get("excluded"):
            spec["chunk_id"] = _stable_id(f"chunk:{spec['key']}")
            spec["extraction_id"] = _stable_id(f"extraction:{spec['key']}")
        paper_by_key[spec["key"]] = spec
        papers.append(spec)

    queries = {
        source: {
            "id": _stable_id(f"search:{source.lower().replace(' ', '-') }"),
            "source": source,
            "query_text": DEMO_PROTOCOL["search_string"],
        }
        for source in ("OpenAlex", "PubMed", "Semantic Scholar")
    }

    records = []
    for raw_spec in RETRIEVED_SPECS:
        spec = deepcopy(raw_spec)
        spec["id"] = _stable_id(f"record:{spec['key']}")
        spec["decision_id"] = _stable_id(f"dedup:{spec['key']}")
        spec["paper_spec"] = paper_by_key[spec["paper"]]
        spec["search_query_id"] = queries[spec["source"]]["id"]
        records.append(spec)

    golden_queries = []
    for raw_spec in GOLDEN_SPECS:
        spec = deepcopy(raw_spec)
        spec["id"] = _stable_id(f"golden:{spec['key']}")
        if spec.get("paper"):
            spec["paper_spec"] = paper_by_key[spec["paper"]]
            spec["relevance_id"] = _stable_id(f"relevance:{spec['key']}")
        golden_queries.append(spec)

    return {
        "project_id": DEMO_PROJECT_ID,
        "protocol": deepcopy(DEMO_PROTOCOL),
        "queries": list(queries.values()),
        "papers": papers,
        "records": records,
        "golden_queries": golden_queries,
    }


def is_demo_project(project: dict | None) -> bool:
    criteria = (project or {}).get("criteria_jsonb") or {}
    marker = criteria.get("_demo") or {}
    return marker.get("seed_id") == DEMO_SEED_ID


def _paper_sources(dataset: dict, paper_key: str) -> list[str]:
    return list(
        dict.fromkeys(
            record["source"]
            for record in dataset["records"]
            if record["paper"] == paper_key
        )
    )


def _extraction_for(paper: dict) -> dict:
    extraction = {
        "schema_version": SCHEMA_VERSION,
        "document_scope": {"chunks_used": 1, "truncated": False},
        "validation_warnings": [],
        "_demo": {"seed_id": DEMO_SEED_ID, "evidence_card": True},
    }
    for field_name, field_type in FIELD_TYPES.items():
        extraction[field_name] = {
            "value": [] if field_type == "list" else NOT_REPORTED,
            "evidence": [],
            "confidence": 0.0,
        }

    field_name = paper["evidence_field"]
    extraction[field_name] = {
        "value": deepcopy(paper["evidence_value"]),
        "evidence": [
            {
                "chunk_id": paper["chunk_id"],
                "page": 1,
                "quote": paper["quote"],
            }
        ],
        "confidence": float(paper["confidence"]),
    }
    return extraction


def _flatten_extraction(extraction: dict) -> dict:
    return {
        field_name: deepcopy(extraction[field_name]["value"])
        for field_name in FIELD_TYPES
    }


def _card_text(paper: dict) -> str:
    return "\n\n".join(
        [
            "CARTÃO DE EVIDÊNCIA - PROJETO DEMONSTRATIVO",
            paper["title"],
            f"Autores: {', '.join(paper['authors'])}",
            f"Ano: {paper['year']} | DOI: {paper['doi']}",
            f"Fonte pública: {paper['source_url']}",
            (
                "Aviso: este arquivo foi gerado localmente para demonstrar o fluxo da "
                "aplicação. Ele contém metadados reais, uma síntese editorial em português "
                "e um trecho curto atribuído; não é o artigo integral."
            ),
            f"Síntese editorial: {paper['abstract']}",
            f"Trecho literal curto: \"{paper['quote']}\"",
        ]
    )


def build_demo_pdf_bytes(paper: dict) -> bytes:
    """Gera um cartão PDF pequeno e autoexplicativo para uma publicação incluída."""
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_textbox(
        fitz.Rect(54, 54, 541, 788),
        _card_text(paper),
        fontsize=10.5,
        fontname="helv",
        lineheight=1.35,
        color=(0.05, 0.12, 0.22),
    )
    payload = document.tobytes(garbage=4, deflate=True)
    document.close()
    return payload


def _default_pdf_directory() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "pdfs"


def _ensure_demo_pdfs(dataset: dict, pdf_directory: Path | None = None) -> dict:
    pdf_directory = Path(pdf_directory or _default_pdf_directory())
    pdf_directory.mkdir(parents=True, exist_ok=True)
    created = 0
    existing = 0
    for paper in dataset["papers"]:
        if paper.get("excluded"):
            continue
        path = pdf_directory / f"{paper['id']}.pdf"
        if path.exists():
            existing += 1
            continue
        path.write_bytes(build_demo_pdf_bytes(paper))
        created += 1
    return {"created": created, "existing": existing, "directory": str(pdf_directory)}


def _remove_demo_pdfs(dataset: dict, pdf_directory: Path | None = None) -> int:
    pdf_directory = Path(pdf_directory or _default_pdf_directory()).resolve()
    removed = 0
    for paper in dataset["papers"]:
        target = (pdf_directory / f"{paper['id']}.pdf").resolve()
        if target.parent != pdf_directory:
            raise RuntimeError("Caminho inesperado ao restaurar os PDFs demonstrativos.")
        if target.exists():
            target.unlink()
            removed += 1
    return removed


def _metadata_for(paper: dict, sources: list[str]) -> dict:
    external_ids = {
        "doi": paper["doi"],
        "pmid": paper.get("pmid"),
        "pmcid": paper.get("pmcid"),
    }
    return {
        "sources": sources,
        "external_ids": {key: value for key, value in external_ids.items() if value},
        "metadata": {
            "year": paper["year"],
            "authors": paper["authors"],
            "url": paper["source_url"],
            "demo_seed_id": DEMO_SEED_ID,
        },
    }


def _insert_dataset(cursor, dataset: dict) -> None:
    project_id = dataset["project_id"]
    cursor.execute(
        """
        INSERT INTO review_projects
            (id, title, question, criteria_jsonb, status, protocol_version)
        VALUES (%s, %s, %s, %s, 'search_ready', 1)
        """,
        (project_id, DEMO_PROJECT_TITLE, DEMO_QUESTION, Json(dataset["protocol"])),
    )
    cursor.execute(
        """
        INSERT INTO review_protocol_versions
            (id, project_id, version, question, criteria_jsonb, change_reason)
        VALUES (%s, %s, 1, %s, %s, %s)
        """,
        (
            _stable_id("protocol:1"),
            project_id,
            DEMO_QUESTION,
            Json(dataset["protocol"]),
            "Carga reproduzível do projeto demonstrativo",
        ),
    )

    for query in dataset["queries"]:
        cursor.execute(
            """
            INSERT INTO search_queries
                (id, project_id, source, query_text, query_jsonb)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                query["id"],
                project_id,
                query["source"],
                query["query_text"],
                Json({"demo_fixture": True, "max_results": 10}),
            ),
        )

    for paper in dataset["papers"]:
        sources = _paper_sources(dataset, paper["key"])
        cursor.execute(
            """
            INSERT INTO deduplicated_papers
                (id, project_id, canonical_doi, title, abstract, merged_sources_jsonb)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                paper["id"],
                project_id,
                paper["doi"],
                paper["title"],
                paper["abstract"],
                Json(_metadata_for(paper, sources)),
            ),
        )

    for record in dataset["records"]:
        paper = record["paper_spec"]
        sources = _paper_sources(dataset, paper["key"])
        metadata = _metadata_for(paper, sources)
        external_id = paper.get("pmid") or paper.get("pmcid") or paper["doi"]
        cursor.execute(
            """
            INSERT INTO retrieved_records
                (id, project_id, search_query_id, source, external_id, doi,
                 metadata_jsonb, raw_jsonb)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record["id"],
                project_id,
                record["search_query_id"],
                record["source"],
                external_id,
                paper["doi"],
                Json(metadata["metadata"]),
                Json({
                    "demo_fixture": True,
                    "source": record["source"],
                    "title": paper["title"],
                    "doi": paper["doi"],
                    "source_url": paper["source_url"],
                }),
            ),
        )
        auto_merge = record["action"] == "auto_merge"
        incoming = {
            "proposed_paper_id": paper["id"],
            "canonical_doi": paper["doi"],
            "title": paper["title"],
            "abstract": paper["abstract"],
            "fontes_dict": metadata,
        }
        cursor.execute(
            """
            INSERT INTO deduplication_decisions
                (id, project_id, retrieved_record_id, candidate_paper_id,
                 result_paper_id, rule_code, similarity_score, system_action,
                 explanation, evidence_jsonb, incoming_record_jsonb, review_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'automatic')
            """,
            (
                record["decision_id"],
                project_id,
                record["id"],
                paper["id"] if auto_merge else None,
                paper["id"],
                "doi_exact" if auto_merge else "no_candidate",
                1.0 if auto_merge else 0.0,
                "auto_merge" if auto_merge else "auto_create",
                (
                    "Mesmo DOI encontrado; a proveniência das fontes foi mesclada automaticamente."
                    if auto_merge
                    else "Nenhum candidato anterior; um artigo único foi criado."
                ),
                Json({
                    "title_similarity": 1.0 if auto_merge else 0.0,
                    "author_overlap": 1.0 if auto_merge else 0.0,
                    "year_match": bool(auto_merge),
                    "doi_match": bool(auto_merge),
                    "doi_conflict": False,
                    "demo_fixture": True,
                }),
                Json(incoming),
            ),
        )

    for paper in dataset["papers"]:
        excluded = bool(paper.get("excluded"))
        rationale = {
            "confidence": 0.94 if excluded else 0.95,
            "justification": (
                "O estudo trata de rastreamento clínico por mamografia, não da triagem "
                "bibliográfica em sínteses de evidências."
                if excluded
                else "O título e o resumo atendem ao escopo sobre apoio computacional à triagem."
            ),
            "criteria_checked": True,
            "demo_fixture": True,
        }
        cursor.execute(
            """
            INSERT INTO screening_decisions
                (id, paper_id, suggested_decision, human_decision,
                 rationale_jsonb, justification, exclusion_reason_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                paper["screening_id"],
                paper["id"],
                "Excluir" if excluded else "Incluir",
                "Excluir" if excluded else "Incluir",
                Json(rationale),
                (
                    "Excluído por tratar de detecção clínica em imagens, fora do escopo da revisão."
                    if excluded
                    else "Inclusão humana confirmada para a demonstração reproduzível."
                ),
                "population_mismatch" if excluded else None,
            ),
        )

        if excluded:
            continue

        chunk_text = _card_text(paper)
        cursor.execute(
            """
            INSERT INTO paper_chunks
                (id, paper_id, chunk_type, chunk_text, metadata_jsonb)
            VALUES (%s, %s, 'full_text_part_1', %s, %s)
            """,
            (
                paper["chunk_id"],
                paper["id"],
                chunk_text,
                Json({
                    "source_type": "pdf",
                    "file_name": f"{paper['id']}.pdf",
                    "page_start": 1,
                    "page_end": 1,
                    "page_chunk_index": 1,
                    "document_chunk_index": 1,
                    "traceability_version": 1,
                    "demo_generated": True,
                    "document_kind": "demo_evidence_card",
                    "source_url": paper["source_url"],
                }),
            ),
        )
        extraction = _extraction_for(paper)
        human_values = _flatten_extraction(extraction)
        cursor.execute(
            """
            INSERT INTO extracted_evidence
                (id, paper_id, extraction_jsonb, schema_version,
                 human_review_status, human_review_jsonb, review_notes, reviewed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """,
            (
                paper["extraction_id"],
                paper["id"],
                Json(extraction),
                SCHEMA_VERSION,
                paper["review_status"],
                Json(human_values),
                (
                    "Revisão demonstrativa baseada em cartão de evidência atribuído; "
                    "não utilizar como substituto do artigo integral."
                ),
            ),
        )
        cursor.execute(
            """
            INSERT INTO evidence_field_sources
                (id, extraction_id, field_name, evidence_order, chunk_id,
                 page_number, quote, quote_validated)
            VALUES (%s, %s, %s, 0, %s, 1, %s, TRUE)
            """,
            (
                _stable_id(f"evidence-source:{paper['key']}"),
                paper["extraction_id"],
                paper["evidence_field"],
                paper["chunk_id"],
                paper["quote"],
            ),
        )

    for paper in dataset["papers"]:
        cursor.execute(
            """
            INSERT INTO agent_interactions
                (id, project_id, agent_name, input_jsonb, output_jsonb, model_jsonb)
            VALUES (%s, %s, 'demo_screening_fixture', %s, %s, %s)
            """,
            (
                _stable_id(f"interaction:screening:{paper['key']}"),
                project_id,
                Json({"paper_id": paper["id"], "criteria": dataset["protocol"]}),
                Json({
                    "suggested_decision": "Excluir" if paper.get("excluded") else "Incluir",
                    "human_validation_recorded": True,
                    "demo_fixture": True,
                }),
                Json({
                    "provider": "fixture",
                    "model_name": "no-external-ai",
                    "generated_by_ai": False,
                    "seed_id": DEMO_SEED_ID,
                }),
            ),
        )

    snapshot_queries = []
    for golden in dataset["golden_queries"]:
        expected_refusal = bool(golden.get("expected_refusal"))
        cursor.execute(
            """
            INSERT INTO rag_golden_queries
                (id, project_id, question, expected_refusal, notes)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                golden["id"],
                project_id,
                golden["question"],
                expected_refusal,
                golden.get("notes") or "Pergunta demonstrativa revisada por humano.",
            ),
        )
        relevances = []
        if golden.get("paper_spec"):
            paper = golden["paper_spec"]
            cursor.execute(
                """
                INSERT INTO rag_golden_relevances
                    (id, golden_query_id, paper_id, page_number,
                     relevance_grade, notes)
                VALUES (%s, %s, %s, 1, %s, %s)
                """,
                (
                    golden["relevance_id"],
                    golden["id"],
                    paper["id"],
                    int(golden["grade"]),
                    "Fonte demonstrativa validada no cartão de evidência.",
                ),
            )
            relevances.append(
                {
                    "id": golden["relevance_id"],
                    "paper_id": paper["id"],
                    "paper_title": paper["title"],
                    "page_number": 1,
                    "relevance_grade": int(golden["grade"]),
                    "notes": "Fonte demonstrativa validada no cartão de evidência.",
                }
            )
        snapshot_queries.append(
            {
                "id": golden["id"],
                "question": golden["question"],
                "expected_refusal": expected_refusal,
                "notes": golden.get("notes") or "Pergunta demonstrativa revisada por humano.",
                "relevances": relevances,
            }
        )

    golden_snapshot = {
        "project_id": project_id,
        "version": 1,
        "queries": snapshot_queries,
        "demo_fixture": True,
    }
    cursor.execute(
        """
        INSERT INTO rag_golden_set_versions
            (id, project_id, version, set_jsonb, change_reason)
        VALUES (%s, %s, 1, %s, %s)
        """,
        (
            _stable_id("golden-version:1"),
            project_id,
            Json(golden_snapshot),
            "Carga inicial do Golden Set demonstrativo",
        ),
    )


def ensure_demo_project(
    *,
    reset: bool = False,
    connection_factory=None,
    pdf_directory: Path | None = None,
) -> dict:
    """Cria, abre ou restaura somente o projeto marcado com o seed oficial."""
    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection

    dataset = build_demo_dataset()
    created = False
    restored = False
    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT criteria_jsonb FROM review_projects WHERE id = %s FOR UPDATE",
            (DEMO_PROJECT_ID,),
        )
        existing = cursor.fetchone()
        if existing:
            marker = ((existing[0] or {}).get("_demo") or {}).get("seed_id")
            if marker != DEMO_SEED_ID:
                raise RuntimeError(
                    "O identificador reservado da demonstração pertence a outro projeto."
                )
            if reset:
                cursor.execute("DELETE FROM review_projects WHERE id = %s", (DEMO_PROJECT_ID,))
                restored = True
            else:
                pdf_result = _ensure_demo_pdfs(dataset, pdf_directory)
                return {
                    "project_id": DEMO_PROJECT_ID,
                    "created": False,
                    "restored": False,
                    "pdfs": pdf_result,
                    "seed_id": DEMO_SEED_ID,
                }

        _insert_dataset(cursor, dataset)
        created = True

    if restored:
        _remove_demo_pdfs(dataset, pdf_directory)
    pdf_result = _ensure_demo_pdfs(dataset, pdf_directory)

    from backend.app.prisma import salvar_snapshot_prisma

    snapshot = salvar_snapshot_prisma(DEMO_PROJECT_ID)
    return {
        "project_id": DEMO_PROJECT_ID,
        "created": created,
        "restored": restored,
        "pdfs": pdf_result,
        "snapshot_version": snapshot["snapshot_version"],
        "seed_id": DEMO_SEED_ID,
    }


def main() -> None:
    result = ensure_demo_project(reset=False)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
