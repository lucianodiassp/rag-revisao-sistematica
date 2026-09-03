# Checklist da candidata v2.3

Objetivo: validar `v2.3.0-rc.1` antes de promover o catálogo visual para `v2.3.0`.
A candidata foi aprovada no piloto Web e no ensaio de restauração isolado em
2026-09-03. A promoção para `v2.3.0` está em preparação; publicação e implantação
estáveis dependem do merge da promoção.
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
- [x] PR de `release/v2.3.0-rc.1` para `main`, checks e merge concluídos (PR #56).
- [x] Tag anotada `v2.3.0-rc.1` no commit integrado e publicada como pré-release.

## 2. Preparação da VPS

Execute esta etapa somente depois da publicação da tag. Não implante a branch de
desenvolvimento em lugar da candidata.

- [x] Atualização controlada concluída, sem falhas de tarefas reportadas.
- [x] Backup anterior à atualização validado pelo pesquisador.
- [x] Revisão anterior anotada (`bcafadb`, `v2.2.0`) e árvore de trabalho limpa.
- [x] Arquivos reais de ambiente e OIDC preservados, fora do Git.

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

- [x] `preflight` e `migrate` encerrados com código zero.
- [x] `db`, `app`, `worker`, `backup-scheduler` e `proxy` saudáveis.
- [x] HTTPS retorna `200`; menu mostra **Versão 2.3.0-rc.1 · Web privada · Usuário único**.
- [x] Diagnóstico operacional informado como saudável, incluindo migrações.

Uma resposta `502` durante a troca da única instância pode ser transitória. Se
persistir após o prazo de prontidão, investigue antes de prosseguir. Não remova
volumes para tentar corrigir a inicialização.

## 3. Piloto funcional Web

Use um projeto de teste com PDF incluído e figura ou tabela conhecida. A etapa de
interpretação faz chamadas externas e pode gerar cobrança; escolha previamente um
modelo com entrada de imagem. Não é necessário reindexar os PDFs.

- [x] Navegação autenticada funciona; bloqueio sem autenticação coberto pela suíte de regressão.
- [x] Atualização do catálogo e conferência de figura/tabela conhecidas aprovadas.
- [x] Primeira revisão humana registrada e preservada após nova catalogação.
- [x] Bloqueio para candidato pendente/rejeitado conferido no código, sem nova execução manual declarada.
- [x] Exigência de consentimento na interface conferida no código e usada no fluxo positivo.
- [x] Interpretação autorizada, resultado e rastreabilidade conferidos pelo pesquisador.
- [x] Segunda revisão salva com mensagem de sucesso e estado persistente.
- [x] Atualização da página preserva decisão e histórico.
- [x] Separação do catálogo em relação ao RAG/relatório mantida, sem mudanças nessa integração.
- [x] Consulta RAG e relatório final executados com sucesso.

Quando a detecção for **Legenda sem região isolada**, a prévia pode representar a
página inteira. Confira todo o conteúdo que será enviado antes do consentimento.
As duas revisões são etapas distintas; o perfil continua de usuário único e não
impõe contas independentes para os responsáveis.

Para declarar ambos os provedores validados na VPS, repita a interpretação com
Gemini e OpenAI, mediante autorização de cada envio. Caso teste somente um,
registre qual foi e mantenha o outro como pendente, sem presumir cobertura.

## 4. Persistência, portabilidade e recuperação

- [x] Reiniciar `app` e `worker`; revisões, histórico e credenciais permanecem.
- [x] Exportar pacote acadêmico e conferir catálogo, interpretações e eventos de revisão;
  ZIP não contém PDFs nem imagens.
- [x] Importar pacote em um novo projeto de teste; histórico é preservado e registros
  importados não são tratados como evidência visual atual automaticamente.
- [x] Backup pós-piloto gerado, baixado e validado com a senha correta.
- [x] Backup externo solicitado e confirmado como concluído/verificado na aplicação e no R2.
- [x] Diagnóstico saudável; testes funcionais concluídos sem erros reportados.
- [x] Restauração do backup com catálogo e interpretações conferida em instalação
  descartável, incluindo históricos e renderização com os PDFs restaurados.

Validar um arquivo não equivale a ensaiar sua restauração. Não restaure sobre a
produção apenas para este teste: a operação substitui o estado. Use uma instalação
isolada com volumes próprios e configurações que não disputem o agendamento externo.
Não publique backups, chaves, imagens ou logs brutos como evidência do piloto.

## 5. Promoção ou correção

- [x] Evidências do piloto registradas, com limites de cobertura explícitos.
- [x] Preparar `release/v2.3.0`: 266 testes locais aprovados, Compose validado e Docker local saudável.
- [ ] PR de promoção para `main`, checks remotos e merge concluídos.
- [ ] Criar tag e release estável somente depois do merge da promoção.

Não mova a tag da candidata. Correções produzem `v2.3.0-rc.2` e nova validação.
Se for necessário retornar, preserve primeiro os dados e siga
[OPERACAO_E_DIAGNOSTICO.md](OPERACAO_E_DIAGNOSTICO.md). Não presuma que trocar a tag
reverte o schema ou desfaz tarefas já executadas; recuperação de dados exige um
backup compatível, preferencialmente restaurado em instalação isolada.
