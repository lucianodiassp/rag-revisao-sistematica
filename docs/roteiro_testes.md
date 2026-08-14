# 🧪 Roteiro de Testes Funcionais (UAT)

**Plataforma de Apoio à Revisão Sistemática (RAG)**

Bem-vindo(a)!

Este documento guia a sua experiência de teste na plataforma. O objetivo é avaliar a fluidez, precisão e utilidade do sistema de triagem e extração de conhecimento baseado em Inteligência Artificial.

**⏱️ Duração estimada:** 15 a 20 minutos.

---

## 📍 Cenário 1: Configuração e Coleta

**Contexto:** É necessário iniciar um novo projeto de revisão e definir a estratégia de busca.

### Passos

1. Aceda ao menu lateral e clique em **"Configuração Pesquisa"**.

2. Insira uma pergunta de pesquisa no campo correspondente.

   *Exemplo:* *"Como a IA apoia o diagnóstico em exames de imagem?"*

3. Gere a string de busca (PICO).
4. Na seção de coleta, abra a aba **"Importar BibTeX"** e selecione um arquivo `.bib`.
5. Confira a prévia, as contagens e importe os registros para o projeto ativo.
6. Opcionalmente, use também a aba **"Consultar APIs"** para combinar as duas formas de coleta.

### ✅ Critério de Sucesso

A plataforma deve:

* Gerar a string de busca corretamente.
* Exibir a prévia do BibTeX e informar entradas válidas, sem DOI e sem abstract.
* Registrar os artigos importados e encaminhá-los para a triagem.
* Consolidar artigos repetidos por DOI ou título, preservando a proveniência.
* Quando a coleta por API for utilizada, comunicar com a base externa sem erros.

---

## 📍 Cenário 2: Triagem (Human-in-the-Loop)

**Contexto:** O sistema filtrou os artigos, mas a decisão final sobre o que entra na revisão é sempre humana.

### Passos

1. Navegue para o menu **"Triagem"**.
2. Leia a sugestão e a justificativa fornecidas pela Inteligência Artificial para o primeiro artigo da lista.
3. Concorde ou discorde da recomendação clicando em **"Aprovar"** ou **"Rejeitar"**.

### ✅ Critério de Sucesso

* O painel de progresso deve ser atualizado automaticamente.
* O artigo deve transitar para a próxima fase.
* Nenhuma mensagem de erro deve ser apresentada.

### Reavaliação por indisponibilidade do PDF

1. Inclua um artigo na triagem e abra **Gestão de PDFs**.
2. Selecione o artigo ainda sem PDF e abra **"Não consegui obter este PDF"**.
3. Informe a categoria e uma justificativa; escolha **"Voltar para a Triagem"**.
4. Confirme que o artigo reaparece na Triagem com o motivo registrado.
5. Após nova decisão de inclusão, repita o fluxo escolhendo **"Excluir da revisão"**.

O artigo deve sair da lista de PDFs pendentes e cada alteração deve permanecer
registrada em `screening_reassessments`, sem apagar a decisão anterior.

---

## 📍 Cenário 3: Interação com o Motor RAG (O Cérebro da Plataforma)

**Contexto:** Fazer perguntas diretamente à literatura utilizando a base de artigos previamente aprovada.

### Passos

1. No terminal do sistema, observe a execução do Motor de Busca (RAG).
2. O sistema responderá a uma pergunta científica baseada na literatura indexada.
3. Em seguida, será realizada uma pergunta fora do escopo.

   *Exemplo:* *"Qual é a capital do Brasil?"*

### ✅ Critério de Sucesso

* O sistema deve citar os IDs dos artigos utilizados para fundamentar as respostas científicas.
* Perguntas fora do escopo da literatura indexada devem ser recusadas de forma educada.
* Não devem ocorrer alucinações ou respostas sem fundamentação documental.

---

## 📍 Cenário 4: Auditoria e Relatório Final

**Contexto:** Verificação da transparência do sistema e das métricas de qualidade produzidas pelo Juiz IA (*LLM-as-a-Judge*).

### Passos

1. Aceda ao menu **"Relatório Final"**.
2. Analise o funil quantitativo apresentado no topo da página (**Artigos Únicos × Artigos Aprovados**).
3. Clique em **"Ver detalhes dos testes"** na secção de Auditoria.

### ✅ Critério de Sucesso

* Os gráficos devem refletir corretamente o fluxo de triagem realizado no Cenário 2.
* A tabela de auditoria deve apresentar as avaliações produzidas pelo Agente Avaliador.
* As métricas de qualidade devem estar visíveis e compreensíveis.

---

## 📋 Tabela de Feedback do Avaliador

Após concluir os cenários, por favor, preencha a tabela abaixo e partilhe as suas impressões.

O seu feedback é fundamental para a evolução da pesquisa.

| Cenário de Teste             | Concluído? (Sim/Não) | Dificuldade (1 = Fácil / 5 = Difícil) | Observações e Sugestões |
| ---------------------------- | -------------------- | ------------------------------------- | ----------------------- |
| 1. Configuração e Coleta     |                      |                                       |                         |
| 2. Triagem de Artigos        |                      |                                       |                         |
| 3. Interação com o Motor RAG |                      |                                       |                         |
| 4. Relatório e Auditoria     |                      |                                       |                         |

---

## 💬 Feedback Geral

**O que achou da confiança transmitida pela plataforma ao exigir a citação rigorosa dos artigos científicos e ao submeter as respostas a uma auditoria independente realizada por um Juiz IA?**

Descreva livremente:

* Pontos positivos.
* Dificuldades encontradas.
* Sugestões de melhoria.
* Funcionalidades desejadas para versões futuras.
