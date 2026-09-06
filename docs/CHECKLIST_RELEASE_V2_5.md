# Checklist da candidata v2.5

Objetivo: validar `v2.5.0-rc.1` antes de promover a gestão segura do ciclo de vida
dos projetos para `v2.5.0`. As evidências ficam em
[VALIDACAO_V2_5_RC1.md](VALIDACAO_V2_5_RC1.md).

## 1. Preparação local

- [x] Funcionalidade integrada à `main` pelo PR #62.
- [x] Arquivamento reversível separado do status científico do projeto.
- [x] Projetos arquivados retirados do seletor operacional e restauráveis.
- [x] Demonstração oficial e último projeto ativo protegidos.
- [x] Exclusão condicionada a ausência de tarefas, backup posterior validado,
  título exato e confirmação da irreversibilidade.
- [x] PDFs protegidos por preparação temporária e retorno em falha transacional.
- [x] Recibos imutáveis sobrevivem à exclusão sem conteúdo científico ou segredos.
- [x] Migração requerida `019_project_lifecycle.sql` aplicada e reaplicável.
- [x] Fluxo funcional aprovado com projeto importado e descartável.
- [x] Identidade `2.5.0-rc.1`, 302 testes e contratos dos Compose aprovados.
- [x] Docker local reconstruído, migração com código zero e serviços saudáveis.
- [x] Diagnóstico completo reconhece a migração `019` e permanece saudável.
- [x] Commit da branch `release/v2.5.0-rc.1` enviado ao GitHub.
- [x] Pull request para `main`, checks e merge concluídos.
- [x] Tag anotada `v2.5.0-rc.1` publicada como pré-release.

## 2. Piloto Web da tag

Antes da atualização, gere, baixe e valide um backup completo e confirme que a
árvore da VPS está limpa. Não substitua `deploy/web.env`, credenciais ou OIDC.

```bash
cd /opt/rag-revisao-sistematica
git status --short
git describe --tags --exact-match
git rev-parse HEAD
git fetch --tags origin
git switch --detach v2.5.0-rc.1
git describe --tags --exact-match
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml build preflight
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml run --rm preflight
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml up -d --build --wait --wait-timeout 300
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml ps -a
curl -I https://revisaorag.tech
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml exec -T app python -m backend.app.operational_health --component full
```

- [x] Preflight e migração encerram com código zero.
- [x] Banco, aplicação, worker, agendador e proxy ficam saudáveis.
- [x] HTTPS retorna `200` e o menu mostra `2.5.0-rc.1` no perfil Web privado.
- [x] Diagnóstico operacional reconhece a migração `019` e permanece saudável.

## 3. Teste funcional Web

Use um pacote acadêmico como projeto descartável; não exclua os dois projetos de
trabalho preservados na instalação.

- [x] Importação cria um terceiro projeto isolado e utilizável.
- [x] Arquivamento o remove do seletor sem remover dados.
- [x] Restauração o devolve ao seletor com conteúdo e recibo preservados.
- [x] Novo arquivamento bloqueia exclusão enquanto não houver backup posterior.
- [x] Backup completo é gerado, baixado e validado depois do arquivamento.
- [x] A zona permanente reconhece o backup, exige título exato e duas confirmações.
- [x] Exclusão remove somente o projeto descartável e preserva seu recibo.
- [x] Demonstração e último projeto ativo permanecem protegidos.
- [x] Navegação, RAG, relatórios, credenciais e tarefas não apresentam regressão.

## 4. Portabilidade e recuperação

- [x] Backup pós-piloto é gerado, baixado e validado.
- [x] Backup externo permanece operacional e verificável no destino privado.
- [x] Restauração controlada em ambiente isolado recompõe projeto arquivado,
  histórico de ciclo de vida e PDFs.
- [x] Retorno à versão anterior considera que migrações são progressivas e não
  remove os campos ou recibos da `019`.

## 5. Promoção

- [x] Evidências do piloto registradas sem incluir segredos ou conteúdo de artigos.
- [x] Preparar `release/v2.5.0` e repetir suíte/contratos locais.
- [x] Integrar a promoção em `main`, criar a tag estável e atualizar a VPS.

Promoção concluída em 2026-09-06: a tag estável `v2.5.0` aponta para o merge
`2319309`, a VPS reporta a versão correta, todos os componentes estão saudáveis e
o endpoint público responde com `HTTP/2 200`.

Não mova a tag da candidata. Correções produzem `v2.5.0-rc.2`. A restauração de
dados depende de backup compatível; trocar somente o código não desfaz migrações.
