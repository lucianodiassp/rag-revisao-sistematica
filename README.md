## 🚀 Como rodar o projeto localmente

**Pré-requisitos:**
* [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado (Para usuários de Windows, certifique-se de habilitar o WSL 2 durante a instalação).
* Git instalado.

**Passo a passo para subir o Banco de Dados:**
1. Clone este repositório: `git clone https://github.com/lucianodiassp/rag-revisao-sistematica.git`
2. Entre na pasta do projeto: `cd rag-revisao-sistematica`
3. Suba os containers do PostgreSQL e pgAdmin: `docker compose up -d`

O banco de dados estará rodando na porta 5432 e o pgAdmin (interface gráfica) estará acessível no seu navegador em `http://localhost:5050` (Login: admin@rag.com | Senha: admin).