"""Ensaio com PostgreSQL descartável. Nunca executar no banco de uma instalação.

Requer DB_NAME=rag_visual_validation, esquema inicial e migrações aplicados.
O banco deve estar vazio de projetos. Não chama nenhum provedor de IA.
"""

import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import fitz
from psycopg2.extras import Json

from backend.app.database import get_connection
from backend.app.golden_set import add_golden_query, add_golden_relevance, add_visual_golden_relevance, list_golden_queries
from backend.app.visual_rag import (
    _pdf_hash, get_visual_rag_setting, set_visual_rag_setting,
    list_eligible_visual_evidence, ensure_visual_evidence_current,
)
from backend.app.visual_interpretation import review_visual_interpretation
from backend.app.reproducibility_package import generate_reproducibility_package
from backend.app.reproducibility_import import import_reproducibility_package


def execute(sql, params=()):
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall() if cursor.description else []


def run():
    if os.environ.get("DB_NAME") != "rag_visual_validation":
        raise RuntimeError("Use exclusivamente o banco descartável rag_visual_validation.")
    if execute("SELECT count(*) FROM review_projects")[0][0]:
        raise RuntimeError("O banco precisa estar vazio; nenhum dado existente será alterado.")
    project, other, paper = (str(uuid.uuid4()) for _ in range(3))
    for project_id in (project, other):
        execute("INSERT INTO review_projects (id,title,question,criteria_jsonb) VALUES (%s,'Ensaio visual','Como otimizar rotas?', '{}')", (project_id,))
    execute("INSERT INTO deduplicated_papers (id,project_id,title,merged_sources_jsonb) VALUES (%s,%s,'Rotas do estudo','{}')", (paper, project))
    execute("INSERT INTO screening_decisions (paper_id,human_decision) VALUES (%s,'Incluir')", (paper,))
    execute("INSERT INTO paper_chunks (paper_id,chunk_type,chunk_text,metadata_jsonb) VALUES (%s,'pdf','As rotas reduzem distancias', '{\"source_type\":\"pdf\",\"page_start\":1}')", (paper,))
    with tempfile.TemporaryDirectory(prefix="rag-visual-fixture-") as temporary:
        os.environ["PDF_DIRECTORY"] = temporary
        path = Path(temporary) / f"{paper}.pdf"
        document = fitz.open()
        document.new_page().insert_text((50, 50), "Figura 1: Otimizacao de rotas")
        document.save(path)
        document.close()
        file_hash = _pdf_hash(paper)
        artifacts, interpretations = [], []
        for index in range(2):
            artifact, interpretation = str(uuid.uuid4()), str(uuid.uuid4())
            artifacts.append(artifact)
            interpretations.append(interpretation)
            execute(
                """INSERT INTO visual_artifacts
                   (id,project_id,paper_id,detection_key,file_sha256,page_number,artifact_type,
                    artifact_order,caption,detection_method,review_status,human_description)
                   VALUES (%s,%s,%s,%s,%s,1,'figure',%s,'Rotas','caption_only','approved','Fluxo de rotas validado')""",
                (artifact, project, paper, str(index) * 64, file_hash, index + 1),
            )
            execute(
                """INSERT INTO visual_interpretations
                   (id,project_id,artifact_id,source_file_sha256,image_sha256,prompt_version,
                    provider_code,model_name,interpretation_jsonb,review_status)
                   VALUES (%s,%s,%s,%s,%s,'test','google_gemini','test',%s,'approved')""",
                (interpretation, project, artifact, file_hash, "b" * 64,
                 Json({"summary": "Rotas com menor distancia", "structured_data": {"valor": 999}})),
            )
        assert get_visual_rag_setting(project)["enabled"] is False
        setting = set_visual_rag_setting(project, True)
        assert setting["revision"] == 1
        assert get_visual_rag_setting(other)["enabled"] is False
        assert list_eligible_visual_evidence(other) == []
        eligible = list_eligible_visual_evidence(project, setting=setting)
        assert len(eligible) == 2
        ensure_visual_evidence_current(project, eligible)
        query = add_golden_query(project, "Como as rotas reduzem distancias?")
        add_golden_relevance(project, query["id"], paper, 1)
        for artifact in artifacts:
            add_visual_golden_relevance(project, query["id"], artifact)
        golden = list_golden_queries(project)
        assert len(golden["queries"][0]["relevances"]) == 3
        # Reaplicação de TODAS as migrações com texto e duas figuras na mesma página.
        environment = os.environ | {
            "PGHOST": os.environ["DB_HOST"], "PGPORT": os.environ["DB_PORT"],
            "PGUSER": os.environ["DB_USER"], "PGPASSWORD": os.environ["DB_PASSWORD"],
            "PGDATABASE": os.environ["DB_NAME"],
        }
        for _ in range(2):
            result = subprocess.run(["/bin/sh", "/migrations/migrate.sh"], env=environment,
                                    text=True, capture_output=True)
            if result.returncode:
                raise RuntimeError(result.stderr[-4000:])
        assert len(list_golden_queries(project)["queries"][0]["relevances"]) == 3
        package = generate_reproducibility_package(project)
        imported = import_reproducibility_package(package["data"], title="Copia historica do ensaio")
        imported_id = imported["project_id"]
        assert get_visual_rag_setting(imported_id)["enabled"] is False
        assert list_eligible_visual_evidence(imported_id) == []
        imported_relevances = list_golden_queries(imported_id)["queries"][0]["relevances"]
        assert len(imported_relevances) == 3
        assert all(item["artifact_id"] not in artifacts for item in imported_relevances if item["artifact_id"])
        review_visual_interpretation(project, interpretations[0], "corrected", "Revisor do ensaio",
                                     corrected_summary="Correcao humana sem valores numericos", human_notes="Valor original ilegivel")
        corrected = list_eligible_visual_evidence(project, setting=setting)
        corrected_item = next(i for i in corrected if i["interpretation_id"] == interpretations[0])
        assert "999" not in corrected_item["text"]
        try:
            ensure_visual_evidence_current(project, eligible)
        except ValueError:
            pass
        else:
            raise AssertionError("A revisao antiga permaneceu valida")
        review_visual_interpretation(project, interpretations[0], "rejected", "Revisor do ensaio", human_notes="Fonte insuficiente")
        assert len(list_eligible_visual_evidence(project)) == 1
        document = fitz.open(path)
        document[0].insert_text((50, 80), "PDF substituido")
        document.saveIncr()
        document.close()
        assert list_eligible_visual_evidence(project) == []
        assert execute("SELECT count(*) FROM agent_interactions WHERE project_id=%s AND agent_name='visual_rag_configuration'", (project,))[0][0] == 1
    print("PASS: migracoes reaplicadas 2x; opt-in/auditoria; isolamento; golden visual; portabilidade historica; correcao/revogacao; hash fisico.")


if __name__ == "__main__":
    run()
