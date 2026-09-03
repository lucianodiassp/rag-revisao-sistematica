# Checklist da candidata v2.3

Objetivo: validar `v2.3.0-rc.1` antes de promover o catálogo visual para `v2.3.0`.
A última release estável permanece `v2.2.0`. O piloto Web ainda não foi executado.
As evidências estão em [VALIDACAO_V2_3_RC1.md](VALIDACAO_V2_3_RC1.md).

## 1. Escopo e preparação local

- [x] Catálogo visual e interpretação multimodal integrados à `main` pelos PRs #54 e #55.
- [x] Identidade da aplicação, imagens Web e testes atualizados para `2.3.0-rc.1`.
- [x] Fluxos funcionais da implementação validados localmente pelo pesquisador,
  incluindo preservação das revisões após nova catalogação e confirmação de salvamento.
- [x] Interpretações fora do índice RAG e do relatório final, mesmo após aprovação.
- [x] Formatos de backup e pacote acadêmico permanecem v1; migração requerida `017`.
- [x] Suíte automatizada da candidata: 266 testes aprovados; validação estrutural dos dois Compose aprovada.
- [x] Imagens locais reconstruídas, migrações concluídas e diagnóstico saudável.
- [x] Pesquisador confirmou a versão no menu, conferiu o catálogo e validou o
  backup local da candidata antes do commit de release.
- [ ] PR de `release/v2.3.0-rc.1` para `main`, checks e merge concluídos.
- [ ] Tag anotada `v2.3.0-rc.1` no commit integrado e pré-release publicada, sem marcar Latest.

## 2. Preparação da VPS

Execute esta etapa somente depois da publicação da tag. Não implante a branch de
desenvolvimento em lugar da candidata.

- [ ] Fila sem tarefas pendentes ou em execução; nenhuma nova operação durante a atualização.
- [ ] Backup anterior à atualização gerado, baixado e validado; senha guardada separadamente.
- [ ] Revisão anterior anotada e árvore de trabalho limpa. Não sobrescrever alterações locais.
- [ ] Arquivos reais de ambiente e OIDC preservados, fora do Git.

No terminal da VPS, confira primeiro:

```bash
cd /opt/rag-revisao-sistematica
git status --short
git describe --tags --exact-match
git rev-parse HEAD
```

Se houver alterações, pare e confira antes de trocar de versão. Com a árvore limpa:

```bash
git fetch --tags origin
git switch --detach v2.3.0-rc.1
git describe --tags --exact-match
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml build preflight
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml run --rm preflight
```

O preflight precisa terminar com código zero. Ele valida a configuração; não
substitui os testes de autenticação, provedores e backup. Não copie arquivos de
exemplo sobre os segredos existentes. Com o preflight aprovado:

```bash
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml up -d --build --wait --wait-timeout 300
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml ps -a
curl -I https://revisaorag.tech
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml exec -T app python -m backend.app.operational_health --component full
```

- [ ] `preflight` e `migrate` encerrados com código zero.
- [ ] `db`, `app`, `worker`, `backup-scheduler` e `proxy` saudáveis.
- [ ] HTTPS retorna `200`; menu mostra **Versão 2.3.0-rc.1 · Web privada · Usuário único**.
- [ ] Diagnóstico confirma migração `017` e não aponta problemas operacionais novos.

Uma resposta `502` durante a troca da única instância pode ser transitória. Se
persistir após o prazo de prontidão, investigue antes de prosseguir. Não remova
volumes para tentar corrigir a inicialização.

## 3. Piloto funcional Web

Use um projeto de teste com PDF incluído e figura ou tabela conhecida. A etapa de
interpretação faz chamadas externas e pode gerar cobrança; escolha previamente um
modelo com entrada de imagem. Não é necessário reindexar os PDFs.

- [ ] Login autorizado e navegação funcionam; janela sem sessão não exibe dados.
- [ ] Atualizar catálogo conclui pela fila; atualizar a página não perde a tarefa.
- [ ] Conferir artigo, página, legenda e imagem contra o PDF, inclusive falsos positivos.
- [ ] Aprovar ou corrigir um candidato com descrição e responsável; manter outro pendente.
- [ ] Nova catalogação preserva revisões e legendas corrigidas da mesma detecção.
- [ ] Candidato pendente ou rejeitado não permite interpretação.
- [ ] Sem consentimento, nenhuma solicitação multimodal pode ser iniciada.
- [ ] Autorizar uma imagem e conferir resultado, provedor, modelo e rastreabilidade.
- [ ] Registrar segunda revisão e verificar a mensagem de sucesso com o estado salvo.
- [ ] Atualizar a página confirma persistência da decisão e do histórico.
- [ ] Conferir que a interpretação não foi incorporada ao RAG ou ao relatório final.
- [ ] Executar uma consulta RAG e gerar relatório, preservando referências e funções existentes.

Quando a detecção for **Legenda sem região isolada**, a prévia pode representar a
página inteira. Confira todo o conteúdo que será enviado antes do consentimento.
As duas revisões são etapas distintas; o perfil continua de usuário único e não
impõe contas independentes para os responsáveis.

Para declarar ambos os provedores validados na VPS, repita a interpretação com
Gemini e OpenAI, mediante autorização de cada envio. Caso teste somente um,
registre qual foi e mantenha o outro como pendente, sem presumir cobertura.

## 4. Persistência, portabilidade e recuperação

- [ ] Sem tarefas em curso, reiniciar `app` e `worker`; revisões, histórico e credenciais permanecem.
- [ ] Exportar pacote acadêmico e conferir catálogo, interpretações e eventos de revisão;
  ZIP não contém PDFs nem imagens.
- [ ] Importar pacote em um novo projeto de teste; histórico é preservado e registros
  importados não são tratados como evidência visual atual automaticamente.
- [ ] Backup pós-piloto gerado, baixado e validado com a senha correta.
- [ ] Backup externo solicitado e confirmado como concluído/verificado na aplicação e no R2.
- [ ] Diagnóstico final saudável; ausência de falhas inesperadas durante o piloto.
- [ ] Restauração do backup com catálogo e interpretações conferida em instalação
  descartável, incluindo históricos e renderização com os PDFs restaurados.

Validar um arquivo não equivale a ensaiar sua restauração. Não restaure sobre a
produção apenas para este teste: a operação substitui o estado. Use uma instalação
isolada com volumes próprios e configurações que não disputem o agendamento externo.
Não publique backups, chaves, imagens ou logs brutos como evidência do piloto.

## 5. Promoção ou correção

- [ ] Evidências do piloto registradas, com limitações e pendências explícitas.
- [ ] Após aprovação dos gates, preparar `release/v2.3.0` para `main` e executar os checks.
- [ ] Criar tag e release estável somente depois do merge da promoção.

Não mova a tag da candidata. Correções produzem `v2.3.0-rc.2` e nova validação.
Se for necessário retornar, preserve primeiro os dados e siga
[OPERACAO_E_DIAGNOSTICO.md](OPERACAO_E_DIAGNOSTICO.md). Não presuma que trocar a tag
reverte o schema ou desfaz tarefas já executadas; recuperação de dados exige um
backup compatível, preferencialmente restaurado em instalação isolada.
