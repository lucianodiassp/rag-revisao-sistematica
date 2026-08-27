# Autenticação da Web privada

## Visão geral

O perfil `web_private` usa a autenticação OpenID Connect (OIDC) nativa do
Streamlit. A aplicação não cria nem armazena senhas: o login é realizado por um
provedor de identidade, como Google Identity, Microsoft Entra ID, Okta ou Auth0.

Após o login, a aplicação verifica se o e-mail recebido está na lista explícita de
acesso. No modo `single_user`, exatamente um e-mail deve ser autorizado.

## Proteções aplicadas

- A autenticação é executada antes da criação da navegação e das páginas.
- O perfil Web bloqueia o acesso quando o OIDC ou a lista de e-mails não está
  configurada.
- Uma identidade sem e-mail, com e-mail explicitamente não verificado ou fora da
  lista é recusada.
- O perfil `local` continua funcionando sem login.
- Tokens OIDC não são expostos pela aplicação, armazenados no banco ou exibidos em
  logs.

## Configuração local para validação

### 1. Registrar o aplicativo no provedor

Crie um cliente Web OIDC no provedor escolhido e cadastre esta URI de retorno:

```text
http://localhost:8501/oauth2callback
```

Para uma implantação real, substitua por uma URL HTTPS no domínio definitivo, por
exemplo `https://rag.exemplo.org/oauth2callback`, tanto no provedor quanto no
arquivo de segredos.

### 2. Criar o arquivo de segredos

Windows PowerShell:

```powershell
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Linux ou macOS:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Preencha `cookie_secret`, `client_id`, `client_secret` e `server_metadata_url` com
os valores do provedor. Gere `cookie_secret` como uma sequência aleatória forte e
independente. O arquivo real está ignorado pelo Git e pelo contexto de build do
Docker.

### 3. Ativar o perfil Web privado

No arquivo `backend/.env`, use:

```env
RAG_DEPLOYMENT_PROFILE=web_private
RAG_USER_MODE=single_user
RAG_AUTH_ALLOWED_EMAILS=seu-email@example.org
```

Depois recrie a aplicação:

```bash
docker compose up -d --build
```

Ao abrir a interface, somente a tela de entrada deve ser exibida. Após o login com
o e-mail autorizado, a navegação é liberada e o menu lateral mostra a identidade e
o botão **Sair**.

## Retorno ao perfil local

Altere `RAG_DEPLOYMENT_PROFILE` para `local` e recrie o serviço. O arquivo OIDC pode
permanecer presente, mas não será exigido no perfil local.

## Limite desta etapa

A lista com mais de um e-mail é aceita apenas quando `RAG_USER_MODE=multi_user`,
perfil reservado para a evolução posterior. Isso ainda não implementa propriedade
ou isolamento de dados entre usuários.
