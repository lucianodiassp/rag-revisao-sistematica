# Implantação Web privada

## Escopo desta configuração

O arquivo `docker-compose.web.yml` prepara uma implantação Web privada de usuário
único, separada da instalação local. Ele cria banco, volumes e nomes de contêineres
próprios e não altera o ambiente `docker-compose.yml` usado na v1 local.

O tráfego segue este caminho:

```text
Internet → HTTPS (Caddy) → Streamlit → PostgreSQL
```

Somente o proxy publica portas no servidor:

- `80/tcp`: emissão de certificado e redirecionamento para HTTPS;
- `443/tcp`: aplicação HTTPS;
- `443/udp`: HTTP/3, quando disponível.

Streamlit e PostgreSQL ficam acessíveis apenas pelas redes internas do Docker.

## Pré-requisitos do servidor

- Linux com Docker Engine e Docker Compose atualizados.
- Domínio público controlado pelo pesquisador.
- Registro DNS do domínio apontando para o IP público do servidor.
- Portas `80` e `443` liberadas no firewall e encaminhadas ao servidor.
- Diretório do projeto acessível somente ao administrador da implantação.

O Caddy obtém e renova automaticamente o certificado TLS quando o domínio aponta
para o servidor e as portas públicas estão acessíveis.

## 1. Preparar o ambiente Web

Copie o arquivo de exemplo:

```bash
cp deploy/web.env.example deploy/web.env
```

Edite `deploy/web.env` e substitua todos os valores de exemplo. São obrigatórios:

- `RAG_DOMAIN`: somente o domínio, sem `https://`, porta ou caminho;
- `RAG_DEPLOYMENT_PROFILE=web_private`;
- `RAG_USER_MODE=single_user`;
- `RAG_AUTH_ALLOWED_EMAILS`: exatamente um e-mail;
- `DB_NAME` e `DB_USER` com identificadores simples;
- `DB_PASSWORD` aleatória, com pelo menos 16 caracteres.

O arquivo real é ignorado pelo Git e pelo contexto de build do Docker.

## 2. Configurar o provedor OIDC

Crie `.streamlit/secrets.toml` conforme o guia
[AUTENTICACAO_WEB.md](AUTENTICACAO_WEB.md). Na implantação real, a URL de retorno
deve usar exatamente o domínio configurado:

```toml
[auth]
redirect_uri = "https://rag.exemplo.org/oauth2callback"
cookie_secret = "chave-aleatoria-forte"
client_id = "cliente-do-provedor"
client_secret = "segredo-do-provedor"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Cadastre a mesma URL de retorno no provedor OIDC. Não reutilize o `cookie_secret`
como senha do banco ou segredo do cliente.

## 3. Executar o preflight

Antes de iniciar banco ou aplicação, execute:

```bash
docker compose --env-file deploy/web.env -f docker-compose.web.yml run --rm preflight
```

O comando retorna somente mensagens seguras. Ele não imprime senhas, chaves, e-mail
ou valores recebidos. A implantação é interrompida quando identifica:

- perfil diferente de Web privada e usuário único;
- domínio local, IP, URL com protocolo, porta ou caminho;
- mais de um e-mail ou endereço inválido;
- credencial padrão, ausente ou fraca no PostgreSQL;
- arquivo OIDC ausente ou inválido;
- callback diferente de `https://DOMINIO/oauth2callback`;
- chave de cookie ou credenciais OIDC não configuradas.

O mesmo preflight é uma dependência obrigatória do banco no Compose Web.

## 4. Subir a aplicação

```bash
docker compose --env-file deploy/web.env -f docker-compose.web.yml up -d --build
```

Consulte o estado sem exibir a configuração:

```bash
docker compose --env-file deploy/web.env -f docker-compose.web.yml ps
docker compose --env-file deploy/web.env -f docker-compose.web.yml logs --tail 100 proxy app
```

Acesse `https://SEU_DOMINIO`. A aplicação deve mostrar somente o botão **Entrar**
antes da autenticação. Depois do login com o e-mail autorizado, deve liberar a
navegação e exibir **Web privada · Usuário único** no menu lateral.

## 5. Parar e atualizar

Para parar os contêineres sem remover volumes:

```bash
docker compose --env-file deploy/web.env -f docker-compose.web.yml down
```

Não use `down --volumes`: essa opção remove os volumes persistentes. Antes de uma
atualização, gere e valide um `.ragbackup`. Em seguida, atualize o código e execute
novamente o comando `up -d --build`.

## Separação do perfil local

- `docker-compose.yml`: instalação local, portas restritas a `127.0.0.1`.
- `docker-compose.web.yml`: implantação Web, banco e Streamlit sem portas públicas.
- `backend/.env`: configuração local.
- `deploy/web.env`: configuração Web.

Os volumes Web recebem o prefixo `rag_web_`; portanto, não reutilizam o banco nem
os arquivos da instalação local. A migração segura de dados será validada na etapa
de armazenamento e recuperação do roadmap da v2.
