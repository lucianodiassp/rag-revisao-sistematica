# Catálogo visual rastreável

## Objetivo e escopo

O catálogo visual identifica candidatos a figuras e tabelas nos PDFs dos artigos
incluídos. Cada registro preserva o artigo, a página, o recorte, a legenda próxima,
o contexto textual, o método de detecção e o SHA-256 do PDF examinado.

O fluxo é deliberadamente conservador:

- a catalogação local não envia imagens ou tabelas a provedores de IA;
- somente candidatos aprovados ou corrigidos podem ser interpretados;
- cada envio exige autorização explícita para um único recorte;
- não insere descrições ou células no índice RAG;
- não transforma uma detecção automática em evidência aprovada;
- exige conferência humana para aprovar, corrigir ou rejeitar cada candidato e
  uma segunda decisão humana para a interpretação da IA.

## Fluxo de uso

1. Conclua a triagem e associe os PDFs aos artigos marcados como **Incluir**.
2. Abra **Catálogo Visual** e selecione **Atualizar catálogo visual**.
3. Aguarde a tarefa persistente concluir; o navegador pode ser atualizado ou fechado.
4. Confira o recorte contra o PDF, a página, a legenda e o contexto exibidos.
5. Registre a decisão humana, uma descrição verificável e o responsável.
6. Opcionalmente, confirme o envio daquele recorte ao provedor configurado e
   solicite a interpretação multimodal.
7. Compare a resposta estruturada com o recorte e o PDF original; aprove, corrija
   ou rejeite a interpretação e identifique o segundo responsável.

Uma nova varredura preserva decisões ligadas à mesma detecção. Legendas corrigidas
por uma pessoa não são substituídas pela legenda automática em varreduras futuras.
Quando o PDF muda, as detecções anteriores permanecem como histórico e as atuais
voltam a exigir revisão.

## Reprodutibilidade e backup

O backup integral `.ragbackup` preserva o banco e os PDFs, portanto consegue
restaurar o catálogo e renderizar novamente seus recortes. O pacote acadêmico ZIP
inclui metadados e eventos de revisão, mas continua sem PDFs ou imagens por motivos
de portabilidade e direitos autorais. As interpretações estruturadas, seus hashes,
modelo, provedor e duas trilhas de revisão entram no pacote. Ao importar esse ZIP,
o catálogo e as interpretações permanecem históricos até que os PDFs sejam
novamente associados, catalogados e conferidos.

## Limitações conhecidas

PDFs digitalizados, imagens compostas, tabelas sem linhas e legendas afastadas
podem produzir omissões ou falsos positivos. A visualização e a decisão humana são
obrigatórias. A interpretação multimodal depende da capacidade do modelo selecionado,
pode omitir ou interpretar incorretamente elementos e não substitui a leitura do PDF.
Na versão estável 2.3, mesmo uma saída aprovada permanece fora do RAG e do relatório.
Na linha 2.4, o Assistente pode recuperar interpretações revisadas quando o projeto
ativa explicitamente essa opção; o índice vetorial textual não muda e o Relatório
Final continua fora do escopo. Veja [RAG_VISUAL.md](RAG_VISUAL.md).
