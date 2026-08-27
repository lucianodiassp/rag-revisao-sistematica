# Histórico de alterações

Este projeto segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).
A versão da aplicação é independente das versões dos formatos de backup, pacote de
reprodutibilidade, migrações do banco e protocolos científicos.

## [Não publicado]

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

[Não publicado]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.0.0-rc.3...HEAD
[2.0.0-rc.3]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.0.0-rc.2...v2.0.0-rc.3
[2.0.0-rc.2]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v2.0.0-rc.1...v2.0.0-rc.2
[2.0.0-rc.1]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v1.0.0...v2.0.0-rc.1
[1.0.0]: https://github.com/lucianodiassp/rag-revisao-sistematica/releases/tag/v1.0.0
