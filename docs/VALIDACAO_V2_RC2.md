# Validação da candidata v2.0.0-rc.2

Data: 27 de agosto de 2026  
Ambiente: VPS Ubuntu 24.04, Docker Compose, domínio público com HTTPS e login OIDC  
Resultado: funcionalmente aprovada, promoção bloqueada pela auditoria de privacidade

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
- Aceitar a promoção somente se os quatro contadores resultarem em zero.
