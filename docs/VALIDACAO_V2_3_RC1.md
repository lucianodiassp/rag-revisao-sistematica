# Validação da candidata v2.3.0-rc.1

Preparação: 2026-09-03. Última release estável: `v2.2.0`.
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
  imprimir os segredos reais. O preflight de produção permanece pendente na VPS.
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
local não comprova envio ao R2. Esse gate será conferido no piloto Web.

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

## Piloto Web — pendente

O [checklist v2.3](CHECKLIST_RELEASE_V2_3.md) contém a sequência operacional, os
testes de navegação, revisão, persistência, portabilidade e recuperação.

Registrar depois da execução, sem incluir segredos ou conteúdo dos artigos:

| Evidência | Estado |
|---|---|
| PR de release, checks, commit integrado e tag publicada | Pendente |
| Backup pré-atualização baixado e validado | Pendente |
| Implantação da tag exata, migrações e serviços saudáveis | Pendente |
| HTTPS, OIDC e identidade no menu | Pendente |
| Catálogo, revisão, recatalogação e consentimento | Pendente |
| Interpretação e segunda revisão; provedor/modelo realmente testados | Pendente |
| Persistência após reinicialização e regressão de RAG/relatório | Pendente |
| Exportação/importação acadêmica em projeto de teste | Pendente |
| Backup pós-piloto, envio externo e ensaio de restauração isolado | Pendente |
| Diagnóstico final e decisão de promoção | Pendente |

## Conclusão

Candidata preparada, verificada tecnicamente e conferida pelo pesquisador no Docker
local, incluindo validação do backup. PR, tag, publicação
da pré-release e implantação Web ainda estão pendentes. A promoção estável depende
dos resultados reais do piloto.
