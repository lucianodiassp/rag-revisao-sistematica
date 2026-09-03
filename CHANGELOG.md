# Histórico de alterações

Este projeto segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).
A versão da aplicação é independente das versões dos formatos de backup, pacote de
reprodutibilidade, migrações do banco e protocolos científicos.

## [Não publicado]

## [2.4.0-rc.1] — 2026-09-03

### Interpretações visuais revisadas no Assistente

- Uso visual opcional e auditado por projeto, desligado por padrão, restrito a PDFs
  incluídos e interpretações atuais com duas revisões humanas válidas.
- Busca lexical visual combinada ao reranking textual, sem alterar embeddings nem
  transmitir novas imagens. Correções humanas substituem a interpretação original.
- Citações com artigo, página e ID visual, metadados completos e bloqueio de entrega
  se PDF, revisão ou autorização mudarem durante a geração.
- Golden Set por figura/tabela e comparação pareada texto × texto+visual, separando
  recuperação visual e regressão textual. Importação mantém visuais históricos e opt-in desligado.
- Migração 018 reaplicável; fluxo do Relatório Final preservado.
- Fechamento documental da release estável 2.3.0 publicada e validada na VPS.
- Candidata preparada após aprovação da suíte automatizada, ensaio isolado do banco,
  Docker local saudável e validação funcional completa pelo pesquisador.

## [2.3.0] — 2026-09-03

### Promoção do catálogo visual

- Preparada a versão estável após a aprovação de `v2.3.0-rc.1` nos perfis local e
  Web privado, com catálogo, consentimento, interpretação multimodal e duas revisões humanas.
- Confirmada a persistência das revisões, históricos e credenciais após reiniciar
  os serviços, além da regressão do assistente e do relatório final.
- Validada a exportação e importação acadêmica sem substituir o projeto original;
  os registros visuais importados permanecem históricos.
- Validados backup pós-piloto, cópia externa no R2 e restauração em instalação
  isolada, com conferência de consultas, PDFs, catálogo, revisões e históricos.
- Preservados migração `017`, formatos de backup e pacote acadêmico v1 e a
  separação das interpretações em relação ao índice RAG e ao relatório final.

## [2.3.0-rc.1] — 2026-09-03

### Catálogo visual rastreável

- Adicionada detecção local de figuras, estruturas tabulares e legendas nos PDFs
  dos artigos incluídos, preservando artigo, página, região e hash do arquivo.
- Criada revisão humana explícita para aprovar, corrigir ou rejeitar candidatos,
  com descrição, responsável e histórico imutável de cada decisão.
- A catalogação passa pela fila persistente e pode continuar após atualização ou
  fechamento do navegador.
- Metadados e revisões do catálogo entram no pacote de reprodutibilidade; PDFs e
  imagens continuam excluídos do ZIP.
- Adicionada interpretação multimodal opcional somente para candidatos aprovados
  ou corrigidos, com consentimento explícito antes do envio de cada recorte.
- Provedor e modelo são configuráveis por função; hash do recorte, versão do prompt,
  saída estruturada e metadados da chamada permanecem auditáveis sem persistir a imagem.
- Criada uma segunda revisão humana para aprovar, corrigir ou rejeitar a interpretação.
- A confirmação de salvamento da segunda revisão permanece visível após a
  atualização da página, junto ao formulário e com o estado registrado.
- Mesmo depois de revisada, a interpretação não entra automaticamente no índice RAG
  nem no relatório final nesta fase.
- Preparada a primeira candidata do catálogo visual, com roteiro de validação na
  VPS e promoção estável condicionada ao piloto. Migração `017`, backup v1 e pacote
  de reprodutibilidade v1 preservados.

## [2.2.0] — 2026-08-30

### Geração multiprovedor estável

- Promovida a configuração de IA por função depois da aprovação da candidata
  `v2.2.0-rc.1` nos perfis local e Web privado.
- Validados Google Gemini e OpenAI no mesmo projeto para triagem, RAG, extração e
  relatório final, preservando `paper_id`, página e trechos literais.
- Confirmadas a persistência cifrada das credenciais após reinicialização e a
  ausência de formatos reconhecíveis de chaves nos logs dos serviços.
- Preservados os embeddings Gemini em 768 dimensões e a compatibilidade dos PDFs
  já indexados, sem necessidade de nova vetorização.
- Confirmados diagnóstico operacional saudável e backup pós-piloto íntegro.

## [2.2.0-rc.1] — 2026-08-30

### Geração multiprovedor

- Adicionados adaptadores independentes para Google Gemini e OpenAI, com despacho
  por função e compatibilidade com o contrato de resposta usado pelos agentes.
- Permitido combinar provedores em formulação, triagem, RAG, reranking, auditoria,
  extração, qualidade metodológica e relatório sem reindexar PDFs.
- Mantidos os embeddings no Gemini e no schema de 768 dimensões nesta primeira
  etapa, evitando incompatibilidade com índices existentes.
- Ampliadas a tela de Configuração de IA, a auditoria e o diagnóstico operacional
  para credenciais e modelos por provedor.
- A integração OpenAI usa Responses API, `store=false`, modo JSON quando solicitado
  e mensagens de erro saneadas sem exposição da credencial.

## [2.1.0] — 2026-08-30

### Backup externo estável

- Promovido o backup externo agendado depois da aprovação da candidata
  `v2.1.0-rc.1` em uma instalação Web real.
- Confirmada a primeira execução diária sem intervenção manual: início às
  `06:00 UTC`, conclusão verificada em aproximadamente cinco segundos e novo
  `.ragbackup` de 55,9 MB no destino privado.
- Confirmados o próximo agendamento, o estado operacional do diagnóstico e a
  ocultação das credenciais na interface e nos registros apresentados ao usuário.
- Mantidos o formato `.ragbackup` v1 e a compatibilidade dos perfis local e Web
  privada de usuário único.

## [2.1.0-rc.1] — 2026-08-29

### Backup externo agendado

- Adicionado serviço independente para criar backups criptografados em horário
  diário e enviá-los a armazenamento compatível com S3.
- Confirmados tamanho e SHA-256 do objeto remoto antes de aplicar retenção local e
  externa, sem remover backups manuais ou cópias pré-restauração.
- Adicionados solicitação manual, estado persistente, health check, diagnóstico e
  webhook HTTPS opcional para falhas.
- Adicionado preflight seguro das credenciais operacionais, sem registrar seus
  valores, além de exemplos e guia de ativação e recuperação.
- Validado o fluxo completo em servidor Web real com bucket S3 compatível privado:
  geração, envio, confirmação de integridade, download e validação do `.ragbackup`.
- Promovida a identidade da aplicação para `2.1.0-rc.1`; a observação da primeira
  execução automática diária permanece como gate para a versão estável `2.1.0`.

## [2.0.1] — 2026-08-27

### Manutenção pós-release

- Adicionada integração contínua para executar testes e validar Compose e Caddy em
  pull requests, alterações na `main` e tags.
- Adicionados contratos que impedem o rastreamento dos arquivos reais de segredos.
- Atualizado o estado da documentação após a promoção estável da `v2.0.0`.
- O procedimento de atualização passa a aguardar serviços saudáveis e documenta
  a breve resposta `502` possível durante a troca da única instância Web.

## [2.0.0] — 2026-08-27

### Web privada estável

- Preservado o perfil local de usuário único e adicionado o perfil Web privado.
- Adicionados login OIDC e autorização explícita para um único e-mail.
- Adicionados proxy HTTPS, configuração segura e armazenamento persistente para
  banco, PDFs, backups e chave-mestra.
- Adicionados fila persistente, worker separado e retomada de tarefas longas após
  atualização ou desconexão do navegador.
- Adicionados diagnóstico operacional, health checks e eventos estruturados.
- Preservadas a compatibilidade do backup `.ragbackup` v1 e a recuperação em uma
  instalação Web limpa.
- Protegidos os logs contra chaves, parâmetros OAuth, e-mails e conteúdo científico.
- Concluídos piloto público, restauração real, teste de falha do worker e auditoria
  final de privacidade com todos os contadores em zero.

## [2.0.0-rc.3] — 2026-08-27

### Privacidade operacional

- Os logs de acesso do Caddy deixam de registrar cabeçalhos e valores temporários
  do fluxo OAuth, além de mascararem os endereços IP de origem.
- O worker preserva eventos operacionais estruturados, mas suprime saídas legadas
  dos processamentos que poderiam conter perguntas, títulos ou trechos científicos.
- O progresso da auditoria quantitativa não imprime mais a pergunta avaliada.
- Adicionados contratos automatizados para impedir regressões na filtragem do
  proxy e na proteção do conteúdo processado pelo worker.
- A correção foi revalidada no VPS com login, navegação e tarefa científica; os
  cinco contadores de e-mail e conteúdo por serviço resultaram em zero.

## [2.0.0-rc.2] — 2026-08-27

### Corrigido após o piloto público

- Corrigido o healthcheck do Caddy para usar uma requisição GET no loopback IPv4,
  eliminando o falso estado não saudável observado no VPS.
- Permitida saída de rede ao worker sem publicar portas, preservando o isolamento
  do PostgreSQL e habilitando Gemini e fontes bibliográficas em tarefas assíncronas.
- Configurações de IA e fontes são recarregadas após restauração, e o worker descarta
  configurações antigas antes de iniciar cada trabalho.
- As páginas de credenciais passam a mostrar dinamicamente o perfil de implantação
  e o modo de usuário, inclusive na Web privada.
- O preflight registra o perfil Web e os limites de armazenamento efetivamente
  solicitados, mantendo os valores sensíveis fora dos logs.
- Registradas as evidências e pendências do primeiro piloto em domínio público.

## [2.0.0-rc.1] — 2026-08-26

### Candidata Web privada

- Criada a linha de integração `v2-web` a partir da versão estável `v1.0.0`.
- Identificada a aplicação como `2.0.0-dev` durante o desenvolvimento.
- Documentado o roadmap incremental da Web privada e seus critérios de aceite.
- Adicionada autenticação OIDC obrigatória no perfil Web privado.
- Adicionada autorização explícita por e-mail, com bloqueio seguro de configurações
  incompletas e preservação do acesso local sem login.
- Adicionado Compose exclusivo para Web privada com Caddy, HTTPS automático,
  PostgreSQL e Streamlit sem portas públicas.
- Adicionado preflight que bloqueia configurações Web incompletas ou inseguras sem
  exibir os valores recebidos.
- Preparação da implantação Web privada, inicialmente de usuário único.
- Adicionados limites separados para PDFs e backups, reserva mínima de armazenamento
  e gravação atômica de uploads.
- Exibida a capacidade dos volumes persistentes e documentadas a cópia externa e a
  recuperação da implantação Web em ambiente limpo.
- Centralizados os caminhos persistentes usados por upload, indexação, backup e
  restauração, preservando o formato `.ragbackup` v1.
- Adicionada fila persistente no PostgreSQL e processo separado para coleta,
  indexação de PDFs, extração, relatório final e benchmark quantitativo.
- Preservados progresso, falhas e tentativas após atualização ou desconexão do
  navegador, com concorrência unitária para proteger as cotas das APIs.
- Adicionados eventos operacionais estruturados em JSON, com versão, perfil,
  categoria e ocultação preventiva de campos sensíveis.
- Adicionados registro verificável de migrações, sinais de vida da aplicação e do
  worker e health checks compostos para banco, interface e armazenamento.
- Criada a página Diagnóstico Operacional, com classificação de falhas e exportação
  de um relatório seguro para suporte.
- Documentados diagnóstico, atualização segura e retorno para uma revisão anterior.
- Corrigidos os health checks independentes da aplicação e do worker no Compose
  Web e adicionado um teste de contrato para impedir regressões.
- Adicionado o gate documentado de candidata, piloto em domínio real e promoção
  segura para `v2.0.0`.
- Corrigida a restauração de backups v1 em bancos v2 que já possuam tabelas com
  novas dependências, substituindo o schema de destino antes do `pg_restore`.
- A restauração passa a registrar novamente os checksums das migrações reaplicadas,
  preservando o diagnóstico operacional depois da recuperação.
- Adicionados um Compose isolado e um registro de evidências para repetir com
  segurança a validação de backups entre as versões v1 e v2.
- Promovida a identidade da aplicação para `2.0.0-rc.1` após a conclusão do gate
  local de integridade, recuperação e validação funcional.

## [1.0.0] — 2026-08-22

### Adicionado

- Projetos de revisão isolados e protocolos científicos versionados.
- Coleta configurável em OpenAlex, Semantic Scholar e PubMed, além de importação BibTeX.
- Calibração da estratégia com artigos sentinela e revisão humana PRESS.
- Deduplicação explicável e triagem assistida com decisão humana rastreável.
- Gestão de PDFs, OCR, indexação vetorial e RAG híbrido com RRF e reranking.
- Matriz de evidências rastreável, revisão humana e exportação em CSV.
- Avaliação metodológica versionada e painel de limitações e confiança na síntese.
- Fluxo PRISMA, Golden Set, benchmark quantitativo e relatório final fundamentado.
- Projeto demonstrativo, backup criptografado e pacote de reprodutibilidade importável.
- Configuração central e cifrada de IA e fontes bibliográficas.
- Instalação local completa com Docker Compose.

### Perfil da versão

- Implantação: local.
- Acesso: usuário único.
- Estado: primeira versão estável documentada.

[Não publicado]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.4.0-rc.1...HEAD
[2.4.0-rc.1]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.3.0...v2.4.0-rc.1
[2.3.0]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.2.0...v2.3.0
[2.3.0-rc.1]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.2.0...v2.3.0-rc.1
[2.2.0]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.1.0...v2.2.0
[2.2.0-rc.1]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.1.0...v2.2.0-rc.1
[2.1.0]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.0.1...v2.1.0
[2.1.0-rc.1]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.0.1...v2.1.0-rc.1
[2.0.1]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v1.0.0...v2.0.0
[2.0.0-rc.3]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.0.0-rc.2...v2.0.0-rc.3
[2.0.0-rc.2]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.0.0-rc.1...v2.0.0-rc.2
[2.0.0-rc.1]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v1.0.0...v2.0.0-rc.1
[1.0.0]: https://github.com/lucianodiassp/rag-revisao-sistematica/releases/tag/v1.0.0
