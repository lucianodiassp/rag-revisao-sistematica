# Registro de validação para a candidata v2.0.0-rc.1

## Escopo

Validação executada em 26 de agosto de 2026 para comprovar a restauração de um
backup da linha v1 em uma instalação v2 limpa, sem alterar a instalação principal.

O ambiente usou o projeto Docker `rag-v2-restore-validation`, a porta local `18501`
e volumes exclusivos para PostgreSQL, PDFs, backups e chave-mestra. Antes da
restauração, as contagens de projetos, artigos, PDFs indexados e interações eram
zero.

## Backup de origem e recuperação

- Origem: `backup-20260822-141857-3c8cd6e6.ragbackup`, validado pela interface.
- A primeira tentativa expôs uma dependência de tabelas v2 durante o
  `pg_restore --clean`.
- O retorno automático preservou corretamente o estado vazio e gerou um backup
  `pre-restore`.
- A rotina foi corrigida para substituir o schema de destino antes da importação e
  registrar os checksums das migrações reaplicadas.
- A segunda tentativa terminou com restauração e validação bem-sucedidas.

## Evidências após a restauração

| Evidência | Resultado |
|---|---:|
| Projetos | 4 |
| Registros coletados | 1.194 |
| Artigos deduplicados | 360 |
| Registros de indexação | 943 |
| Evidências extraídas | 30 |
| Interações de agentes após consulta RAG | 1.184 |
| PDFs físicos | 21 |
| Migrações registradas | 14 |
| Checksums de migração inválidos | 0 |
| Health check da aplicação | saudável |
| Health check do worker | saudável |

A navegação, a Gestão de PDFs e uma consulta RAG foram validadas. Ao final foi
criado e validado o backup v2
`backup-20260826-222641-d98f62d5.ragbackup`, com 58.238.380 bytes.

## Resultado

Os blocos locais de integridade, compatibilidade, recuperação e validação funcional
da candidata foram concluídos. A promoção para a versão estável ainda depende do
piloto em servidor com domínio público, HTTPS e callback OIDC reais descrito no
[checklist da candidata](CHECKLIST_RELEASE_V2.md).
