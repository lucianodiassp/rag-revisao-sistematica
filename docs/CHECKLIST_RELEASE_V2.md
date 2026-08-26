# Checklist da candidata v2 Web privada

Este checklist transforma os critérios do roadmap em uma decisão objetiva de
publicação. Os blocos 1 a 3 foram concluídos em 26 de agosto de 2026 e sustentam a
candidata `2.0.0-rc.1`. A tag estável `v2.0.0` exige também o bloco 4 em uma
instalação Web real.

## 1. Integridade do código

- [x] A branch `v2-web` está sincronizada e sem alterações locais não registradas.
- [x] A suíte completa de testes termina sem falhas.
- [x] `docker compose config --quiet` valida o perfil local.
- [x] O perfil Web mantém health checks independentes para `app` e `worker`.
- [x] Somente o proxy publica portas no perfil Web.
- [x] `.env`, `deploy/web.env` e `.streamlit/secrets.toml` não estão rastreados
  pelo Git.
- [x] O `CHANGELOG.md`, o README e os guias operacionais refletem a candidata.

## 2. Compatibilidade e recuperação

Para executar esta etapa sem tocar na instalação principal:

```bash
docker compose -p rag-v2-restore-validation \
  -f docker-compose.yml \
  -f deploy/restore-validation.compose.yml \
  up -d --build db migrate app worker
```

Acesse `http://localhost:18501`. Ao concluir, encerre os contêineres sem apagar os
volumes com o mesmo conjunto de arquivos e o comando `down`. Não acrescente `-v`
até que todas as evidências tenham sido conferidas.

- [x] Um backup `.ragbackup` gerado pela v1 foi validado antes da migração.
- [x] Uma cópia desse backup foi guardada fora do servidor da aplicação.
- [x] O backup foi restaurado em uma instalação v2 limpa.
- [x] Projetos, artigos, PDFs, configurações cifradas e consultas RAG foram
  conferidos após a restauração.
- [x] Uma atualização preservou banco, PDFs, backups e chave-mestra.
- [x] O procedimento de retorno documentado foi ensaiado sem usar
  `docker compose down -v`.

O primeiro ensaio da candidata está registrado em
[VALIDACAO_V2_RC1.md](VALIDACAO_V2_RC1.md).

## 3. Validação funcional da candidata

- [x] O perfil local continua acessível sem login.
- [x] O perfil Web não mostra páginas nem dados antes da autenticação.
- [x] O e-mail autorizado entra e um e-mail não autorizado é bloqueado.
- [x] Coleta, indexação, extração, relatório e benchmark continuam após atualizar
  ou fechar a página.
- [x] Falhas transitórias podem ser repetidas e falhas definitivas apresentam
  diagnóstico compreensível.
- [x] O Diagnóstico Operacional identifica aplicação, banco, migrações, volumes,
  worker e fila sem expor segredos.
- [x] Foi gerado e validado um novo backup ao final do teste.

## 4. Piloto em servidor com domínio público

- [ ] DNS aponta para o servidor e somente as portas `80` e `443` estão públicas.
- [ ] O preflight Web termina com sucesso usando os arquivos reais do servidor.
- [ ] O Caddy obtém um certificado HTTPS válido e redireciona HTTP para HTTPS.
- [ ] A URI OIDC cadastrada é exatamente
  `https://DOMINIO/oauth2callback`.
- [ ] `db`, `app`, `worker` e `proxy` permanecem saudáveis após reinicialização.
- [ ] O fluxo completo foi executado pelo domínio: login, projeto, busca/importação,
  triagem, PDF, indexação, evidências, qualidade, síntese e backup.
- [ ] Uma desconexão do navegador durante uma tarefa longa não interrompe o job.
- [ ] Uma falha controlada do worker aparece no diagnóstico e a recuperação foi
  confirmada após reiniciá-lo.
- [ ] Logs e relatórios de suporte não contêm chaves, tokens, e-mails ou conteúdo
  científico dos projetos.

## 5. Promoção da versão

Após a validação dos blocos 1 a 3:

1. alterar `VERSION` e os testes de identidade para `2.0.0-rc.1`;
2. atualizar o badge e o estado da versão no README e no `CHANGELOG.md`;
3. criar a tag anotada `v2.0.0-rc.1` na `v2-web` e publicar uma pre-release no
   GitHub;
4. executar o piloto do bloco 4 exatamente a partir dessa tag.

Depois do piloto sem pendências críticas:

1. corrigir eventuais problemas em branches `feature/v2-*` direcionadas à
   `v2-web`;
2. atualizar a identidade para `2.0.0` e registrar a data no `CHANGELOG.md`;
3. mesclar `v2-web` na `main`;
4. criar a tag anotada `v2.0.0` e publicar a Release;
5. gerar e validar um backup na instalação atualizada.

Não reutilize a tag de uma candidata corrigida. Se houver alteração depois da
`rc.1`, publique `rc.2`, `rc.3` e assim por diante.
