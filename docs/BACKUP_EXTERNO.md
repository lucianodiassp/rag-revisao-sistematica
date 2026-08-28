# Backup externo agendado

## Objetivo

O serviço `backup-scheduler` cria diariamente o mesmo `.ragbackup` criptografado e
portátil disponível na interface, confirma sua integridade em um armazenamento
compatível com S3 e aplica retenção controlada. Assim, uma falha total do disco do
VPS não elimina simultaneamente a aplicação e todas as cópias de recuperação.

O recurso é opcional e inicia desabilitado. Os perfis locais continuam funcionando
sem configurar um provedor externo. Na instalação local, as mesmas variáveis podem
ser adicionadas a `backend/.env`; na Web privada, use `deploy/web.env`.

## Provedores compatíveis

O destino pode ser AWS S3 ou um serviço com API S3 compatível, como Cloudflare R2,
Backblaze B2, MinIO ou outro provedor que ofereça bucket, região, endpoint e
credenciais de acesso.

Use uma credencial exclusiva, limitada ao bucket e ao prefixo da aplicação. As
permissões mínimas normalmente correspondem a listar o prefixo e criar, consultar
e remover seus objetos. Não reutilize uma credencial administrativa do provedor.

## Configuração segura

Edite apenas `deploy/web.env` no servidor. Esse arquivo é ignorado pelo Git e não
entra na imagem Docker:

```dotenv
RAG_EXTERNAL_BACKUP_ENABLED=true
RAG_EXTERNAL_BACKUP_BUCKET=nome-do-bucket
RAG_EXTERNAL_BACKUP_PREFIX=rag-revisao-sistematica
RAG_EXTERNAL_BACKUP_REGION=us-east-1
RAG_EXTERNAL_BACKUP_ENDPOINT_URL=https://endpoint-s3-do-provedor
RAG_EXTERNAL_BACKUP_ACCESS_KEY_ID=identificador-da-credencial
RAG_EXTERNAL_BACKUP_SECRET_ACCESS_KEY=credencial-secreta
RAG_EXTERNAL_BACKUP_PASSWORD=senha-forte-e-exclusiva-do-ragbackup
RAG_EXTERNAL_BACKUP_SCHEDULE_HOUR_UTC=3
RAG_EXTERNAL_BACKUP_RETRY_MINUTES=60
RAG_EXTERNAL_BACKUP_LOCAL_RETENTION=3
RAG_EXTERNAL_BACKUP_REMOTE_RETENTION=14
RAG_EXTERNAL_BACKUP_ADDRESSING_STYLE=auto
```

Para AWS S3, `RAG_EXTERNAL_BACKUP_ENDPOINT_URL` pode permanecer ausente. Em
provedores compatíveis, use o endpoint HTTPS informado pelo serviço. Alguns exigem
`RAG_EXTERNAL_BACKUP_ADDRESSING_STYLE=path`; mantenha `auto` quando não houver uma
orientação específica.

A senha do `.ragbackup` deve possuir ao menos 12 caracteres e ser guardada fora do
VPS. Ela não é enviada como metadado do objeto. Sem essa senha, o arquivo externo
não poderá ser restaurado.

Opcionalmente, configure um endpoint HTTPS que aceite JSON para receber avisos de
falha:

```dotenv
RAG_EXTERNAL_BACKUP_ALERT_WEBHOOK_URL=https://endpoint-privado-de-alertas
```

O alerta contém somente o tipo do evento, data, versão e uma mensagem operacional;
não contém credenciais, nomes de projetos, PDFs ou conteúdo científico.

## Ativação

Depois de editar o arquivo seguro, valide antes de reiniciar a aplicação:

```bash
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml build preflight
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml run --rm preflight
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml up -d --build --wait --wait-timeout 300
```

Abra **Backup e Restauração**, confirme os dados públicos da configuração e use
**Solicitar backup externo agora**. O pedido é persistido no volume privado e
processado em até 30 segundos, mesmo que a página seja fechada.

Considere a configuração validada somente depois de:

1. a tela registrar o primeiro sucesso;
2. o objeto aparecer no bucket com o tamanho esperado;
3. o Diagnóstico Operacional marcar **Backup externo** como operacional;
4. uma cópia baixada do bucket passar em **Validar backup** na aplicação.

## Integridade e retenção

Antes do envio, o serviço calcula o SHA-256 do `.ragbackup`. Depois do upload, ele
confirma no destino o tamanho e o hash registrado nos metadados. A retenção só é
aplicada após essa confirmação.

- `RAG_EXTERNAL_BACKUP_LOCAL_RETENTION` preserva as cópias agendadas mais recentes
  no volume do VPS;
- `RAG_EXTERNAL_BACKUP_REMOTE_RETENTION` preserva as cópias agendadas mais recentes
  no bucket;
- backups manuais e arquivos `pre-restore-*` não são removidos por essa política;
- somente objetos do prefixo configurado cujo nome começa com `scheduled-backup-`
  entram na limpeza remota.

Ativar versionamento e regras de proteção no próprio bucket acrescenta uma camada
independente contra exclusão acidental. Confira os custos e a retenção de versões
antigas no provedor escolhido.

## Falhas e recuperação

Uma falha deixa o arquivo local preservado, registra um estado seguro, torna o
health check do serviço não saudável e aparece no Diagnóstico Operacional. O
agendador tenta novamente após `RAG_EXTERNAL_BACKUP_RETRY_MINUTES`.

Um bloqueio compartilhado no volume privado impede que o agendador execute durante
uma criação manual ou uma restauração. Se uma operação já estiver em andamento, a
segunda é recusada com segurança e poderá ser repetida depois.

Para recuperar outro servidor, baixe um `.ragbackup` do bucket, prepare uma
instalação limpa e use o fluxo **Validar backup** e **Restaurar instalação**. O
arquivo de ambiente Web, as credenciais OIDC e a senha do backup continuam sendo
administrados separadamente e não fazem parte do objeto restaurado.
