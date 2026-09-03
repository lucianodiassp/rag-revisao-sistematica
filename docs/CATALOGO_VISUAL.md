# Catálogo visual rastreável

## Objetivo e escopo

O catálogo visual identifica candidatos a figuras e tabelas nos PDFs dos artigos
incluídos. Cada registro preserva o artigo, a página, o recorte, a legenda próxima,
o contexto textual, o método de detecção e o SHA-256 do PDF examinado.

Esta primeira etapa é deliberadamente conservadora:

- não envia imagens ou tabelas a provedores de IA;
- não atribui significado científico ao conteúdo;
- não insere descrições ou células no índice RAG;
- não transforma uma detecção automática em evidência aprovada;
- exige conferência humana para aprovar, corrigir ou rejeitar cada candidato.

## Fluxo de uso

1. Conclua a triagem e associe os PDFs aos artigos marcados como **Incluir**.
2. Abra **Catálogo Visual** e selecione **Atualizar catálogo visual**.
3. Aguarde a tarefa persistente concluir; o navegador pode ser atualizado ou fechado.
4. Confira o recorte contra o PDF, a página, a legenda e o contexto exibidos.
5. Registre a decisão humana, uma descrição verificável e o responsável.

Uma nova varredura preserva decisões ligadas à mesma detecção. Legendas corrigidas
por uma pessoa não são substituídas pela legenda automática em varreduras futuras.
Quando o PDF muda, as detecções anteriores permanecem como histórico e as atuais
voltam a exigir revisão.

## Reprodutibilidade e backup

O backup integral `.ragbackup` preserva o banco e os PDFs, portanto consegue
restaurar o catálogo e renderizar novamente seus recortes. O pacote acadêmico ZIP
inclui metadados e eventos de revisão, mas continua sem PDFs ou imagens por motivos
de portabilidade e direitos autorais. Ao importar esse ZIP, o catálogo permanece
histórico até que os PDFs sejam novamente associados e catalogados.

## Limitações conhecidas

PDFs digitalizados, imagens compostas, tabelas sem linhas e legendas afastadas
podem produzir omissões ou falsos positivos. A visualização e a decisão humana são
obrigatórias. A futura interpretação multimodal deverá consumir apenas candidatos
aprovados, registrar o provedor e o modelo e manter ligação explícita com página e
região de origem.
