# Checklist da candidata v2.4

Objetivo: validar `v2.4.0-rc.1` antes de promover o RAG visual revisado para
`v2.4.0`. As evidências ficam em [VALIDACAO_V2_4_RC1.md](VALIDACAO_V2_4_RC1.md).

## 1. Preparação local

- [x] RAG visual integrado à `main` pelo PR #58.
- [x] Uso visual opcional por projeto e desligado por padrão.
- [x] Somente interpretações atuais com duas revisões humanas válidas são elegíveis.
- [x] Citações visuais incluem artigo, página e ID do artefato.
- [x] Relatório Final, embeddings e formatos v1 de backup/pacote preservados.
- [x] Migração requerida `018_visual_rag.sql` reaplicável.
- [x] Ensaio isolado de banco, Docker local e teste funcional aprovados.
- [x] Identidade `2.4.0-rc.1`, 291 testes e contratos dos Compose aprovados.
- [x] Docker local reconstruído; migração encerrou com código zero e todos os
  serviços persistentes ficaram saudáveis.
- [x] Diagnóstico completo reconheceu a migração `018`, sem falhas ou tarefas órfãs.
- [x] Commit da branch `release/v2.4.0-rc.1` enviado ao GitHub.
- [x] PR #59 para `main`, checks e merge concluídos.
- [x] Tag anotada `v2.4.0-rc.1` publicada como pré-release.

## 2. Piloto Web da tag

Antes da atualização, valide e preserve um backup e confirme que a árvore da VPS
está limpa. Não substitua os arquivos reais de ambiente ou OIDC.

```bash
cd /opt/rag-revisao-sistematica
git status --short
git describe --tags --exact-match
git rev-parse HEAD
git fetch --tags origin
git switch --detach v2.4.0-rc.1
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
- [x] HTTPS retorna `200` e o menu mostra `2.4.0-rc.1` no perfil Web privado.
- [x] Diagnóstico operacional reconhece a migração `018` e permanece saudável.

## 3. Teste funcional Web

- [x] Com a opção desligada, uma consulta textual preserva o comportamento anterior.
- [x] Outro projeto mantém configuração independente e desligada por padrão.
- [x] Com a opção ligada, consulta dirigida recupera interpretação elegível e mostra
  artigo, página e ID visual; o detalhe identifica a fonte como interpretação.
- [x] Correção ou rejeição posterior exclui o visual de novas respostas e separa o histórico antigo.
- [x] Golden Set aceita alvo visual específico sem conflitar com alvo textual da mesma página.
- [x] Comparação texto × texto+visual conclui os dois modos, mostra exclusões e exporta JSON.
- [x] Relatório Final continua funcionando sem incorporar automaticamente os visuais.
- [x] Reinício preserva configuração; credenciais e demais fluxos não apresentam regressão.

## 4. Portabilidade e recuperação

- [x] Backup local gerado, baixado e validado.
- [x] Backup externo gerado e verificado no destino privado.
- [x] Pacote acadêmico exportado/importado em projeto separado; opt-in importado continua desligado.
- [x] Restauração controlada concluída, com textos, visuais, julgamentos e auditoria conferidos.

## 5. Promoção

- [x] Evidências do piloto registradas, sem incluir segredos ou conteúdo de artigos.
- [x] Preparar `release/v2.4.0` e repetir suíte/contratos locais.
- [x] Integrar a promoção em `main`, criar a tag estável e atualizar a VPS.

Não mova a tag da candidata. Correções produzem `v2.4.0-rc.2`. Migrações são
progressivas; retornar o código não desfaz schema nem dados, portanto recuperação
depende de backup compatível e preferencialmente de ensaio isolado.
