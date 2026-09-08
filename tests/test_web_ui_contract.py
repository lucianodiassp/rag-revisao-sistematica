from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_credential_pages_show_dynamic_deployment_scope():
    for relative_path in (
        "frontend/views/4_Configuracao_IA.py",
        "frontend/views/6_Fontes_Bibliograficas.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")

        assert "application_metadata" in source
        assert "metadata['deployment_label']" in source
        assert "metadata['user_mode_label']" in source
        assert "Escopo atual: instalação local" not in source


def test_visual_catalog_is_exposed_with_explicit_human_review_scope():
    navigation = (ROOT / "frontend/app.py").read_text(encoding="utf-8")
    page = (ROOT / "frontend/views/14_Catalogo_Visual.py").read_text(
        encoding="utf-8"
    )

    assert 'title="Catálogo Visual"' in navigation
    assert "Nenhuma imagem ou tabela é" in page
    assert "interpretada por IA" in page
    assert "Confirmo que conferi este candidato no PDF" in page
    assert "Autorizo o envio deste recorte aprovado" in page
    assert "Aprove ou corrija o candidato visual" in page
    assert "Confirmo que comparei a interpretação com o recorte" in page
    assert "uso visual habilitado explicitamente no projeto" in page
    assert "Permanece fora do relatório final" in page


def test_project_lifecycle_page_exposes_reversible_and_protected_flows():
    navigation = (ROOT / "frontend/app.py").read_text(encoding="utf-8")
    page = (ROOT / "frontend/views/15_Gestao_Projetos.py").read_text(
        encoding="utf-8"
    )

    assert 'title="Gestão de Projetos"' in navigation
    assert "Arquivar é reversível" in page
    assert "último projeto ativo" in page
    assert "backup completo **depois deste arquivamento**" in page
    assert "digite exatamente o título" in page
    assert "Histórico imutável do ciclo de vida" in page


def test_installation_pages_are_visible_only_to_operator_and_recheck_backend_role():
    navigation = (ROOT / "frontend/app.py").read_text(encoding="utf-8")
    backup_page = (ROOT / "frontend/views/9_Backup_Restauracao.py").read_text(
        encoding="utf-8"
    )
    health_page = (
        ROOT / "frontend/views/13_Diagnostico_Operacional.py"
    ).read_text(encoding="utf-8")

    assert "if current_user_is_operator():" in navigation
    assert 'title="Backup e Restauração"' in navigation
    assert 'title="Diagnóstico Operacional"' in navigation
    assert "require_installation_operator()" in backup_page
    assert "create_installation_backup" in backup_page
    assert "restore_installation_backup" in backup_page
    assert "require_installation_operator()" in health_page
    assert "build_installation_health_report" in health_page


def test_user_access_page_exposes_protected_membership_and_ownership_flows():
    navigation = (ROOT / "frontend/app.py").read_text(encoding="utf-8")
    page = (ROOT / "frontend/views/16_Usuarios_Acessos.py").read_text(
        encoding="utf-8"
    )

    assert 'title="Usuários e Acessos"' in navigation
    assert "pré-autorização por e-mail verificado" in page
    assert "não enviam mensagem" in page
    assert "Somente o operador pode ativar ou desativar contas" in page
    assert "O projeto nunca fica sem proprietário" in page
    assert "transfer_project_ownership" in page
    assert "set_application_user_status" in page


def test_auth_gate_uses_project_admission_only_for_future_multi_user_mode():
    gate = (ROOT / "frontend/auth_gate.py").read_text(encoding="utf-8")

    assert 'decision.code == "email_not_allowed"' in gate
    assert 'metadata["user_mode"] == "multi_user"' in gate
    assert "multi_user_admission_source" in gate
    assert "additional_allowed_emails=(decision.email,)" in gate
    assert "multi_user_admission_check_failed" in gate
