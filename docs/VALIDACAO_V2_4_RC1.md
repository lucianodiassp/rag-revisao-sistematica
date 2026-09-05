# Validação da candidata v2.4.0-rc.1

Preparação: 2026-09-03. Release estável anterior: `v2.3.0`.
Escopo: uso opcional de interpretações visuais revisadas no Assistente e benchmark.

## Evidências anteriores à candidata

A implementação foi integrada à `main` pelo PR #58. Antes da preparação da release:

- 291 testes automatizados aprovados;
- migração `018` reaplicada duas vezes em PostgreSQL isolado;
- conferidos isolamento por projeto, auditoria, Golden Set visual, portabilidade
  histórica, correção/revogação e validação do hash físico do PDF;
- Docker local saudável, migração concluída e diagnóstico operacional aprovado;
- ausência de padrões conhecidos de chaves nos arquivos alterados;
- roteiro funcional completo aprovado pelo pesquisador, incluindo opção desligada,
  recuperação visual, citações, histórico, comparação e preservação do relatório.

Essas evidências autorizam preparar a candidata, mas não substituem a repetição da
suíte com a identidade final nem o piloto da tag no perfil Web privado.

## Verificação técnica da candidata

- Identidade esperada: `2.4.0-rc.1` no `VERSION`, interface e quatro serviços Web.
- Migração requerida: `018_visual_rag.sql`.
- Backup e pacote acadêmico: formato `1`.
- Embeddings: dimensão e provedor existentes preservados.
- Relatório Final: fluxo textual preservado.
- Suíte automatizada da identidade final: **291 testes aprovados** em 2026-09-03.
- Compose local e Compose Web validados estruturalmente com código zero; o arquivo
  de exemplo foi usado sem resolver ou imprimir os segredos de produção.
- Docker local reconstruído com espera de prontidão: aplicação, worker, agendador e
  PostgreSQL saudáveis; migração encerrada com código zero.
- Identidade efetiva `2.4.0-rc.1` confirmada dentro do contêiner da aplicação.
- Diagnóstico completo saudável às `2026-09-03T22:47:05Z`, com migração `018`,
  interface, armazenamento e provedores operacionais e fila sem falhas recentes.

Comando reproduzível no Windows, usando pasta temporária exclusiva:

```powershell
& .\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp D:\Codex\pytest-rag-v24-rc1-20260903
```

## Limites preservados

- A busca visual é lexical sobre interpretações revisadas, não busca semântica de imagens.
- Nenhuma imagem nova é enviada durante perguntas ao Assistente.
- O recurso começa desligado em cada projeto e não é ativado pela importação.
- A validação determinística confirma a origem da citação, não a verdade semântica da afirmação.
- Mudança do PDF, revisão ou autorização invalida a fonte antes da entrega.
- O piloto pode consumir APIs ao executar perguntas e comparações pareadas.

## Piloto Web

Executado em 2026-09-05 a partir da tag imutável `v2.4.0-rc.1`, integrada pelo PR
#59 e publicada como pré-release.

- Preflight e migração encerraram com código zero. PostgreSQL, aplicação, worker,
  agendador de backup e proxy permaneceram saudáveis.
- HTTPS respondeu `HTTP/2 200`; a interface exibiu `2.4.0-rc.1` no perfil Web
  privado e o diagnóstico completo reconheceu `018_visual_rag.sql`, fila sem falhas,
  armazenamento suficiente, backup externo e provedores configurados.
- O uso visual começou desligado, persistiu por projeto e não alterou outro projeto.
  Com a opção ligada, consultas dirigidas recuperaram a mesma interpretação local e
  Web, com artigo, página, ID visual e indicação de que não era transcrição literal.
- Uma diferença inicial de recuperação foi rastreada a bases com estados distintos,
  não ao código. Um backup validado com 2 projetos, 109 artigos, 21 PDFs e 529
  interações normalizou a VPS; a consulta equivalente passou nos dois ambientes.
- Rejeição controlada tornou a interpretação imediatamente inelegível, separou a
  resposta histórica e suprimiu a fonte em nova consulta. A reaprovação restaurou a
  recuperação; o backup pré-teste foi restaurado para remover os eventos artificiais.
- Golden Set aceitou o alvo visual remapeável e o benchmark pareado concluiu os dois
  modos, exibiu recuperação visual, regressão textual, rankings, exclusões e JSON.
- O Relatório Final foi regenerado sem incorporar automaticamente interpretações
  visuais. Navegação, credenciais e diagnóstico não apresentaram regressão.
- Backup foi gerado, baixado, validado e restaurado. O pacote acadêmico foi exportado
  na Web e importado localmente em projeto temporário: criou novo UUID, preservou o
  julgamento visual remapeado, manteve opt-in desligado e não importou PDFs nem
  credenciais. O projeto temporário foi removido após a conferência.

O smoke test posterior à restauração confirmou dois projetos, interpretação atual
aprovada, citação visual e diagnóstico saudável. Essas evidências aprovaram a
promoção para `v2.4.0`.

## Verificação da identidade estável

A branch `release/v2.4.0` foi preparada em 2026-09-05 sem alterar schema, formatos
ou comportamento funcional. A suíte completa aprovou **291 testes** com a identidade
estável; os contratos dos Compose local e Web encerraram com código zero. A
publicação permanece condicionada aos checks e ao merge do pull request, seguidos
da tag anotada no commit resultante da `main`.

## Fechamento pós-release

O PR #60 integrou a promoção na `main`. A tag anotada `v2.4.0` foi criada no merge
commit `8ceb7decdc2338ab8a0f4f079f1692866d8a75be` e publicada como release estável.

Na VPS, a atualização partiu dessa tag: preflight e migração encerraram com código
zero, os serviços persistentes ficaram saudáveis, HTTPS respondeu `HTTP/2 200` e o
diagnóstico completo permaneceu saudável com `018_visual_rag.sql`. O smoke test
confirmou a identidade `2.4.0`, autenticação e navegação, os dois projetos esperados,
a interpretação aprovada, recuperação com citação visual e configuração do backup
externo preservada. A tag estável não recebeu alterações posteriores.
