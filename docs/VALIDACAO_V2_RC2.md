# Validação da candidata v2.0.0-rc.2

Data: 27 de agosto de 2026  
Ambiente: VPS Ubuntu 24.04, Docker Compose, domínio público com HTTPS e login OIDC  
Resultado: a tag permaneceu bloqueada; sua correção de privacidade foi revalidada
com sucesso para compor a próxima candidata

## Evidências aprovadas

- Certificado HTTPS válido e redirecionamento para conexão segura.
- Banco, aplicação, worker e proxy saudáveis após reinicialização do servidor.
- Fluxo funcional completo validado pelo domínio público.
- Tarefa longa continuou após desconexão do navegador.
- Interrupção controlada do worker apareceu no diagnóstico e a fila retomou após
  sua recuperação.
- Backup real restaurado, novo backup gerado, validado e guardado fora do VPS.

## Auditoria de privacidade dos logs

A inspeção inicial encontrou:

| Verificação | Total | Origem confirmada |
|---|---:|---|
| Chaves ou segredos com padrão conhecido | 0 | — |
| Endereços de e-mail | 22 | proxy |
| Parâmetros temporários do retorno OAuth | 8 | proxy |
| Perguntas, títulos ou conteúdo científico | 17 | worker |

Nenhuma chave de API foi encontrada. Entretanto, e-mails, parâmetros OAuth e
conteúdo científico não atendem ao gate de privacidade. Por isso, a tag
`v2.0.0-rc.2` permanece como pré-lançamento e não deve ser promovida a estável.

## Correção exigida para a próxima candidata

- Remover cabeçalhos dos logs de acesso, filtrar parâmetros OAuth e mascarar IPs.
- Suprimir saídas legadas dos jobs sem remover os eventos operacionais estruturados.
- Repetir a auditoria considerando apenas os logs gerados após a implantação.
- Aceitar o gate somente se todas as categorias auditadas resultarem em zero.

## Revalidação da correção

A branch `feature/v2-privacidade-logs`, no commit `6803546`, foi implantada no
mesmo VPS. Após recriar aplicação, worker e proxy, foram repetidos o login OIDC,
a navegação e a execução de uma tarefa científica em segundo plano.

Os contadores dos novos logs foram:

| Verificação por serviço | Total |
|---|---:|
| E-mails na aplicação | 0 |
| E-mails no worker | 0 |
| E-mails no proxy | 0 |
| Conteúdo científico na aplicação | 0 |
| Conteúdo científico no worker | 0 |

O gate de privacidade foi aprovado sem regressão funcional. A tag
`v2.0.0-rc.2` não será alterada; a correção validada deve ser incorporada à
`v2-web` e publicada em uma nova candidata `v2.0.0-rc.3`.
