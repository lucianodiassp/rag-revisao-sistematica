# Histórico de alterações

Este projeto segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).
A versão da aplicação é independente das versões dos formatos de backup, pacote de
reprodutibilidade, migrações do banco e protocolos científicos.

## [Não publicado]

### Em desenvolvimento

- Criada a linha de integração `v2-web` a partir da versão estável `v1.0.0`.
- Identificada a aplicação como `2.0.0-dev` durante o desenvolvimento.
- Documentado o roadmap incremental da Web privada e seus critérios de aceite.
- Preparação da implantação Web privada, inicialmente de usuário único.

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

[Não publicado]: https://github.com/lucianodiassp/rag-revisao-sistematica/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lucianodiassp/rag-revisao-sistematica/releases/tag/v1.0.0
