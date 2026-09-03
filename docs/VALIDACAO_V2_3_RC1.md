# Validação da candidata v2.3.0-rc.1

Preparação e piloto: 2026-09-03. Release estável anterior: `v2.2.0`.
Escopo: catálogo visual, interpretação multimodal opcional e segunda revisão humana.

## Evidências funcionais anteriores à candidata

Durante a linha `2.3.0-dev`, o pesquisador confirmou os testes locais do catálogo,
inclusive a permanência das revisões após atualizar a catalogação. A interpretação
multimodal e a segunda revisão foram validadas em seguida. Após o relato de falta
de retorno no botão de segunda revisão, a confirmação de salvamento foi corrigida
e aprovada pelo pesquisador.

Essas funcionalidades foram incorporadas à `main` pelos PRs #54 e #55. A suíte da
implementação passou com 265 testes antes da preparação desta candidata. Esses
registros não substituem a validação da tag no servidor nem comprovam o uso manual
dos dois provedores multimodais na VPS.

## Verificação técnica da candidata

- Identidade: `2.3.0-rc.1` no arquivo `VERSION`, interface e quatro serviços da imagem Web.
- Adicionado contrato para impedir divergência entre as imagens Web e `VERSION`.
- Migração requerida: `017_visual_interpretations.sql`.
- Backup e pacote acadêmico: formato `1`, sem alteração do índice vetorial existente.
- Suíte automatizada: **266 testes aprovados** em 2026-09-03.
- Compose local validado com `config --quiet`; Compose Web validado estruturalmente
  com o arquivo de exemplo e `config --quiet --no-env-resolution`, sem carregar ou
  imprimir os segredos reais. O preflight de produção foi aprovado posteriormente na VPS.
- Docker local reconstruído com espera de prontidão: banco, interface, worker e
  agendador saudáveis; serviço de migrações encerrado com código zero.
- Versão efetiva `2.3.0-rc.1` confirmada na aplicação, worker e agendador.
- Diagnóstico completo saudável às `2026-09-03T09:14:28Z`, migração `017` atualizada
  e contadores de tarefas em execução, pendentes, em espera de repetição, órfãs e
  falhas nas últimas 24 horas em zero. Endpoint local de saúde retornou HTTP `200`.
- Arquivos reais de ambiente e OIDC não rastreados no Git; nenhuma alteração de segredos.

Comando reproduzível da suíte no Windows (use uma pasta temporária exclusiva):

```powershell
& .\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp D:\Codex\pytest-rag-v23-rc1-20260903
```

O backup externo está desativado nesta instalação local; portanto, o diagnóstico
local não comprova envio ao R2. O envio foi confirmado separadamente no piloto Web.

Nenhuma nova chamada paga de IA faz parte da verificação técnica da identidade.
Os testes automatizados de provedores utilizam substitutos locais das APIs.

## Confirmação manual da candidata local

Após a atualização do Docker local, o pesquisador confirmou a versão no menu,
conferiu o catálogo e validou o backup da candidata. Esta confirmação fecha a
conferência manual local antes do commit de release; não representa um ensaio de
restauração nem substitui o backup e os testes específicos da VPS.

## Limites preservados

- Catalogação local não envia imagens ao provedor.
- Interpretação exige candidato aprovado/corrigido e consentimento para cada envio.
- A prévia pode ser a página inteira quando não há região isolada.
- Interpretações continuam fora do RAG e do relatório, mesmo após segunda aprovação.
- Importação acadêmica preserva o histórico, mas não ativa automaticamente as evidências visuais.
- Imagens não são persistidas nas interpretações nem incluídas no ZIP acadêmico.

## Piloto Web — aprovado

O [checklist v2.3](CHECKLIST_RELEASE_V2_3.md) contém a sequência operacional, os
testes de navegação, revisão, persistência, portabilidade e recuperação.

As evidências abaixo combinam saídas de comandos fornecidas pelo pesquisador,
verificações diretas de GitHub/HTTPS e suas confirmações funcionais. Nenhum backup,
segredo ou conteúdo dos artigos foi anexado a este registro.

| Evidência | Estado |
|---|---|
| PR de release, checks, commit integrado e tag publicada | PR #56; commit `c1d59e9`; dois checks aprovados; tag `v2.3.0-rc.1` publicada como pré-release |
| Backup pré-atualização | Validado antes da troca da versão `v2.2.0`, revisão `bcafadb`, com árvore de trabalho limpa |
| Implantação da tag exata, migrações e serviços saudáveis | Preflight Web aprovado às `09:50:56Z`; preflight e migrações com saída 0; aplicação, worker, agendador, banco e proxy saudáveis |
| HTTPS e identidade no menu | HTTP `200` confirmado externamente às `09:57:05Z`; versão e perfil Web privado confirmados pelo pesquisador |
| Navegação, catálogo, revisão e recatalogação | Conferidos na VPS, com permanência das decisões |
| Interpretação e segunda revisão | Fluxo com consentimento e confirmação de salvamento aprovado; provedor e modelo usados não foram informados no relato |
| Persistência após reinicialização | Catálogo, interpretação, revisões, histórico e credenciais conferidos após reiniciar aplicação e worker |
| Regressão de RAG/relatório | Consulta ao assistente e geração do relatório final aprovadas |
| Exportação/importação acadêmica | ZIP conferido, importado em novo projeto e reexportado com histórico; original preservado |
| Backup pós-piloto e envio externo | Cópia baixada/validada e backup externo gerado/verificado no destino R2 |
| Recuperação isolada | Backup restaurado com sucesso; consultas, PDFs, catálogo, revisões e históricos conferidos |
| Diagnóstico operacional | Todos os componentes reportados como operacionais |

### Interrupção de conectividade durante a preparação

Houve perda temporária de acesso SSH e HTTPS antes da atualização dos serviços.
O acesso voltou sem alteração de configuração ou reinicialização da VPS: o uptime
continuava superior a seis dias, e os contêineres da `2.2.0` estavam saudáveis.
O build e o preflight foram repetidos antes de aplicar a candidata. A causa da
interrupção não foi determinada; não foi necessária correção de código.

### Ensaio de recuperação

Foi usada a sobreposição `deploy/restore-validation.compose.yml`, com projeto Docker
`rag-v2-restore-validation`, porta local `18501` e volumes próprios. Não havia
contêineres nem volumes anteriores desse ambiente na checagem prévia. Apenas banco,
migrações, aplicação e worker foram iniciados, sem o agendador externo.

O pesquisador confirmou restauração e conferência bem-sucedidas. Depois encerrou o
ambiente com `down`, sem `-v`, preservando temporariamente os volumes. A VPS e a
instalação local principal não foram usadas como destino da restauração.

### Limites das evidências

O relato não identifica o provedor/modelo escolhido para a interpretação nem afirma
que ambos os provedores foram exercitados manualmente. Não se declara dupla cobertura
multimodal no piloto. O acesso não autenticado permanece coberto pela suíte de
regressão; não foi relatada uma nova checagem em janela sem sessão. Os bloqueios para
candidatos não aprovados e ausência de consentimento foram conferidos no código,
sem extrapolar isso para uma repetição manual de todos os cenários negativos na VPS.

## Verificação da promoção estável

Em `release/v2.3.0`, a identidade foi atualizada para `2.3.0` sem alterações na
lógica da aplicação, nas dependências ou nas migrações. A suíte voltou a passar
com **266 testes**, e os contratos Compose local/Web foram validados sem imprimir
segredos. As imagens locais foram reconstruídas e os serviços ficaram saudáveis.

O diagnóstico de `2026-09-03T16:06:23Z` confirmou `2.3.0`, migração `017`, fila sem
pendências ou falhas recentes e saúde geral aprovada. Worker e agendador também
informaram `2.3.0`, e o endpoint de saúde local respondeu HTTP `200`. A VPS não foi
alterada nesta preparação; permanece na candidata validada até a publicação da
tag estável.

## Conclusão

Candidata aprovada para promoção a `2.3.0`, com fluxo funcional, persistência,
portabilidade, backup externo e recuperação isolada confirmados. A promoção altera
identidade e documentação, sem mudar a lógica funcional testada. A publicação e a
implantação da tag estável ocorrerão somente depois do merge da branch de promoção.
