# Operação, diagnóstico, atualização e retorno de versão

Este guia cobre a instalação local e a Web privada. Os comandos de exemplo não
imprimem credenciais. Na Web, acrescente sempre:

```bash
--env-file deploy/web.env -f docker-compose.web.yml
```

entre `docker compose` e o restante do comando.

## Diagnóstico rápido

A página **Diagnóstico Operacional** apresenta uma visão segura de:

- versão, perfil e modo de usuário;
- conexão com PostgreSQL e migração mais recente;
- escrita e reserva livre dos volumes persistentes;
- resposta interna da interface e sinal de vida do worker;
- fila, falhas recentes e novas tentativas;
- disponibilidade da configuração de IA, sem mostrar a chave;
- fontes bibliográficas habilitadas e presença de autenticação, sem mostrar valores.

O mesmo diagnóstico pode ser executado no servidor:

```bash
docker compose exec -T app python -m backend.app.operational_health --component full
```

O resultado é JSON e pode ser compartilhado para suporte. Ele não contém e-mails,
senhas, tokens, chaves de API, caminhos privados ou conteúdo científico.

## Identificar a categoria da falha

| Categoria | Indício principal | Primeira ação |
|---|---|---|
| `configuration` | preflight ou configuração da aplicação inválida | revisar os arquivos locais e executar novamente o preflight |
| `database` | PostgreSQL ou migração indisponível | conferir `db`, depois `migrate` |
| `storage` | volume sem escrita ou reserva livre | conferir montagem, permissão e espaço do volume |
| `ai_provider` | modelo, cota, 429, 503 ou timeout de IA | conferir Configuração de IA e aguardar a tentativa automática |
| `bibliographic_source` | OpenAlex, PubMed ou Semantic Scholar indisponível | conferir Fontes Bibliográficas e o status da fonte |
| `worker` | fila parada ou sinal de vida vencido | conferir e reiniciar somente o serviço `worker` |
| `application` | interface ou processamento interno | consultar o ID do evento e os logs de `app`/`worker` |

## Logs estruturados

Eventos operacionais próprios da aplicação são emitidos como uma linha JSON. Cada
evento inclui horário UTC, nível, componente, categoria, versão e perfil. Campos
sensíveis são ocultados antes da escrita.

```bash
docker compose logs --since 30m app worker migrate
```

Exemplos de eventos úteis: `service_started`, `job_started`, `job_succeeded`,
`job_failed`, `web_preflight_failed`, `migration_started` e
`storage_startup_failed`.

Não publique o arquivo `.env`, `deploy/web.env`, `.streamlit/secrets.toml`, dumps do
banco ou logs de bibliotecas externas sem revisá-los. O filtro da aplicação protege
os eventos próprios, mas não controla mensagens produzidas por todos os componentes
de terceiros.

## Verificações de saúde

O Compose verifica componentes diferentes separadamente:

- `db`: disponibilidade nativa do PostgreSQL;
- `migrate`: termina com código zero somente após aplicar e registrar as migrações;
- `app`: interface HTTP, banco, migrações e armazenamento;
- `worker`: banco, migrações e sinal de vida do processo de tarefas;
- `proxy` na Web: processo e configuração interna do Caddy.

```bash
docker compose ps
docker compose logs --tail 100 migrate app worker
```

Um contêiner `unhealthy` deve ser diagnosticado pela categoria antes de reiniciar
toda a instalação. Reiniciar apenas `worker` não interrompe a interface:

```bash
docker compose restart worker
```

## Atualização segura

1. Avise o usuário para não iniciar novas tarefas e aguarde a fila ficar sem itens
   em execução.
2. Gere e valide um `.ragbackup` na interface.
3. Guarde o identificador da revisão atual:

   ```bash
   git rev-parse --short HEAD
   ```

4. Atualize a branch destinada à implantação.
5. Reconstrua e suba os serviços sem remover volumes:

   ```bash
   docker compose up -d --build
   ```

6. Confirme `db`, `app` e `worker` como saudáveis e `migrate` concluído.
7. Execute o diagnóstico completo e um teste curto de navegação.

Nunca use `docker compose down -v` numa atualização: essa opção remove os dados
persistentes.

## Retorno para a revisão anterior

Use retorno de código quando a nova imagem falhar, mas os dados permanecerem
íntegros:

1. Pare `app`, `worker` e, na Web, `proxy`.
2. Volte o repositório para o commit anotado antes da atualização.
3. Reconstrua os serviços da aplicação e mantenha os volumes existentes.
4. Execute o diagnóstico e valide um projeto.

As migrações deste ciclo são aditivas; a versão anterior pode ignorar tabelas novas.
Não tente desfazer migrações manualmente. Se uma atualização futura alterar dados de
forma incompatível, restaure o `.ragbackup` pré-atualização em uma instalação limpa,
aceitando que registros criados depois daquele backup não serão preservados.

## Dados úteis ao solicitar suporte

- JSON baixado da página **Diagnóstico Operacional**;
- hash do commit e versão exibida no menu;
- horário aproximado e identificador da tarefa que falhou;
- linhas estruturadas dos serviços `app`, `worker` e `migrate` no mesmo intervalo.

Não envie credenciais nem PDFs para diagnosticar uma falha operacional.
