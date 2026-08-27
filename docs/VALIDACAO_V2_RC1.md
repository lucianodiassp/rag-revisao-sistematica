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
da candidata foram concluídos.

## Piloto em servidor público

Em 27 de agosto de 2026, a tag imutável `v2.0.0-rc.1` foi instalada em um VPS com
Ubuntu 24.04 LTS, Docker Engine 29.7.2 e Docker Compose 5.5.0. O domínio
`revisaorag.tech` foi apontado ao servidor sem registrar o endereço IP neste
documento.

Foram validados:

- preflight com os arquivos reais da implantação;
- certificado HTTPS automático e resposta HTTP/2 pelo Caddy;
- login e logout OIDC pelo Google com lista explícita de um e-mail;
- serviços PostgreSQL, aplicação, worker e proxy saudáveis;
- restauração do backup real previamente validado, incluindo banco, 21 PDFs e
  credencial Gemini cifrada;
- consulta ao Assistente RAG com resposta fundamentada;
- geração do Relatório Final pela fila persistente;
- criação, validação e download de um novo `.ragbackup` no servidor.

### Achados da candidata

O piloto revelou quatro ajustes necessários antes da promoção estável:

1. o healthcheck do Caddy consultava `localhost`, que não alcançava o endpoint
   administrativo nessa imagem, apesar de o HTTPS público responder corretamente;
2. o worker estava somente na rede interna do banco e, sem publicar portas, também
   precisava ingressar na rede de saída para alcançar os provedores externos;
3. a restauração substituía banco e chave-mestra, mas a configuração de IA já
   carregada pelo processo podia permanecer em memória até uma nova validação;
4. as páginas de credenciais exibiam o texto fixo "instalação local" mesmo no
   perfil Web privado.

As correções mantêm PostgreSQL, Streamlit e worker sem portas públicas: somente o
proxy publica tráfego da aplicação. A falha de resolução do worker foi apresentada
sem segredo, e a mesma geração de relatório terminou com sucesso após a correção.

### Situação da promoção

O piloto funcional foi concluído após os ajustes, mas a tag `v2.0.0-rc.1` não será
alterada. As correções devem originar uma nova candidata. Permanecem como gates a
reinicialização completa do servidor, o fluxo científico integral pelo domínio, a
desconexão durante tarefa longa e a auditoria final de logs descritos no
[checklist da candidata](CHECKLIST_RELEASE_V2.md).
