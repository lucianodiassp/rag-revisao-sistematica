# Validação final da candidata v2.0.0-rc.3

Data: 27 de agosto de 2026  
Tag implantada: `v2.0.0-rc.3`  
Commit da tag: `64823e3`  
Ambiente: VPS Ubuntu 24.04, Docker Compose, domínio público com HTTPS e login OIDC  
Resultado: aprovada para promoção estável

## Verificações finais

- O VPS foi colocado exatamente na tag publicada, sem mover ou reutilizar tags.
- A aplicação respondeu pelo domínio público usando HTTPS.
- O menu exibiu `Versão 2.0.0-rc.3 · Web privada · Usuário único`.
- A geração do relatório final foi executada com sucesso pelo worker.
- A aplicação permaneceu navegável e os serviços operacionais.

## Auditoria de privacidade

Após login, navegação e execução da tarefa científica, os novos logs apresentaram:

| Verificação por serviço | Total |
|---|---:|
| E-mails na aplicação | 0 |
| E-mails no worker | 0 |
| E-mails no proxy | 0 |
| Conteúdo científico na aplicação | 0 |
| Conteúdo científico no worker | 0 |

## Decisão

Todos os itens do gate da Web privada de usuário único foram concluídos. A
`v2.0.0-rc.3` está aprovada para promoção, com incorporação da `v2-web` à `main`
e criação posterior da tag estável `v2.0.0` no commit integrado.
