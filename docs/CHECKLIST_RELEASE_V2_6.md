# Checklist da candidata v2.6

Objetivo: validar `v2.6.0-rc.1` antes de promover a fundação multiusuário. O
escopo é um piloto OIDC privado, com duas contas conhecidas e sem cadastro público.
As evidências ficam em [VALIDACAO_V2_6_RC1.md](VALIDACAO_V2_6_RC1.md).

## 1. Preparação local

- [x] Fundação integrada à `main` pelo PR #76.
- [x] Identidade, propriedade, papéis, operador e convites cobertos por testes.
- [x] Credenciais e preferências privadas isoladas por usuário.
- [x] Criação e importação restritas ao operador durante o piloto.
- [x] Ativação dupla, backup externo obrigatório e reversão documentados.
- [x] Fluxo funcional local aprovado em `single_user` e backup validado.
- [x] Identidade `2.6.0-rc.1`, 442 testes e contratos de implantação aprovados.
- [x] Docker local reconstruído, migrações com código zero e serviços saudáveis.
- [x] Diagnóstico completo local saudável.
- [ ] Commit da branch `release/v2.6.0-rc.1` enviado ao GitHub.
- [ ] Pull request para `main`, checks e merge concluídos.
- [ ] Tag anotada `v2.6.0-rc.1` publicada como pré-release.

## 2. Implantação inicial da tag em usuário único

Antes da atualização, gere, baixe e valide um backup completo, confirme a cópia no
destino externo e verifique que a árvore da VPS está limpa. Não substitua
`deploy/web.env`, credenciais ou a configuração OIDC.

```bash
cd /opt/rag-revisao-sistematica
git status --short
git describe --tags --exact-match
git rev-parse HEAD
git fetch --tags origin
git switch --detach v2.6.0-rc.1
git describe --tags --exact-match
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml build preflight
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml run --rm preflight
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml up -d --build --wait --wait-timeout 300
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml ps -a
curl -I https://revisaorag.tech
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml exec -T app python -m backend.app.operational_health --component full
```

- [ ] Preflight e migrações `020` a `024` terminam com código zero.
- [ ] Aplicação, PostgreSQL, worker, agendador e proxy ficam saudáveis.
- [ ] HTTPS retorna `200` e o menu mostra `2.6.0-rc.1 · Web privada · Usuário único`.
- [ ] Projetos, navegação, credenciais e tarefas permanecem operacionais.
- [ ] Diagnóstico informa um operador ativo e `oidc_ready_operators: 1`.

Não prossiga se o operador OIDC não estiver pronto ou se o backup externo não
estiver em estado de sucesso.

## 3. Preparação do piloto

- [ ] Escolher um projeto não crítico para o compartilhamento controlado.
- [ ] Registrar convite válido para o e-mail verificado da segunda conta.
- [ ] Iniciar com papel `viewer`; não adicionar a segunda conta à allowlist do servidor.
- [ ] Confirmar `valid_pending_invitations >= 1`, `orphaned_projects: 0` e
  `unsafe_pending_invitations: 0` no diagnóstico.
- [ ] Gerar e validar novo backup completo e confirmar a cópia externa.

No `deploy/web.env`, preservar exatamente um e-mail administrativo e ativar:

```ini
RAG_USER_MODE=multi_user
RAG_MULTI_USER_PILOT_ENABLED=true
RAG_MULTI_USER_PILOT_ACK=ISOLAMENTO_E_BACKUP_CONFIRMADOS
```

Execute novamente preflight, atualização com espera e diagnóstico. O preflight deve
falhar fechado se faltar qualquer confirmação ou se o backup externo estiver
desabilitado.

## 4. Piloto com duas contas reais

Use duas sessões de navegador independentes.

- [ ] O operador mantém acesso aos próprios projetos e às páginas administrativas.
- [ ] A segunda conta entra somente pelo convite e vê apenas o projeto recebido.
- [ ] Como `viewer`, a segunda conta lê, mas não altera nem cria/importa projetos.
- [ ] Após promoção para `editor`, uma alteração controlada conclui normalmente.
- [ ] Credenciais e preferências privadas não aparecem entre as contas.
- [ ] Revogação remove o acesso da segunda conta sem acesso residual.
- [ ] Backup, restauração e diagnóstico continuam exclusivos do operador.
- [ ] Fila, RAG, relatórios, PDFs e navegação não apresentam regressão.
- [ ] Backup pós-piloto é gerado, baixado, validado e confirmado no destino externo.

## 5. Reversão e promoção

Para encerrar o piloto, retorne `RAG_USER_MODE=single_user`, desative a flag e
reaplique o Compose. Não é necessário restaurar o backup: usuários, convites,
associações e recibos permanecem preservados no banco.

- [ ] Retorno a usuário único validado sem perda de dados.
- [ ] Evidências registradas sem e-mails, tokens, chaves ou conteúdo científico.
- [ ] Preparar `release/v2.6.0` somente após aprovação integral do piloto.

Não mova a tag da candidata. Correções produzem `v2.6.0-rc.2`.
