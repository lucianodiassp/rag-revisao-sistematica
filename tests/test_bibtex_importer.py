import unittest
from types import SimpleNamespace

from backend.coleta.importador_bibtex import ErroBibTeX, analisar_bibtex, importar_bibtex


class BibTeXImporterTests(unittest.TestCase):
    def test_importa_campos_multilinha_e_normaliza_latex(self):
        conteudo = br"""
@article{ WOS:TESTE001,
Author = {Garc{\'i}a, Ana and M{\"u}ller, Jochen},
Title = {Revis{\~a}o de RAG \& manuten{\c c}{\~a}o},
Journal = {Journal of Tests},
Year = {2025},
Abstract = {Primeira linha
  com {texto entre chaves}.},
DOI = {10.1000/teste\_01},
Keywords = {RAG; Systematic review},
Unique-ID = {WOS:TESTE001},
}
"""

        resultado = analisar_bibtex(conteudo, "teste.bib")
        artigo = resultado["articles"][0]

        self.assertEqual(resultado["total_entries"], 1)
        self.assertEqual(resultado["valid_entries"], 1)
        self.assertEqual(artigo["titulo"], "Revisão de RAG & manutenção")
        self.assertEqual(
            artigo["fontes_dict"]["external_ids"]["doi"],
            "10.1000/teste_01",
        )
        self.assertEqual(
            artigo["fontes_dict"]["metadata"]["authors"],
            ["García, Ana", "Müller, Jochen"],
        )
        self.assertEqual(artigo["fontes_dict"]["sources"], ["Web of Science (BibTeX)"])
        self.assertIn("raw_entry", artigo["registro_bruto"])

    def test_aceita_entrada_sem_doi_e_sem_abstract(self):
        conteudo = b"""
@inproceedings{chave,
  title = {A paper without DOI},
  booktitle = {Conference},
  year = 2024
}
"""

        resultado = analisar_bibtex(conteudo, "sem_doi.bib")

        self.assertEqual(resultado["valid_entries"], 1)
        self.assertEqual(resultado["without_doi"], 1)
        self.assertEqual(resultado["without_abstract"], 1)
        self.assertEqual(
            resultado["articles"][0]["abstract"],
            "Abstract indisponível no arquivo BibTeX.",
        )

    def test_ignora_diretivas_e_relata_entrada_sem_titulo(self):
        conteudo = b"""
@comment{Export generated for testing}
@string{journal = "Journal"}
@article{sem-titulo,
  author = {Doe, Jane},
  year = {2023}
}
@article{valido,
  title = "Valid title",
  year = 2024
}
"""

        resultado = analisar_bibtex(conteudo, "misto.bib")

        self.assertEqual(resultado["total_entries"], 2)
        self.assertEqual(resultado["valid_entries"], 1)
        self.assertEqual(resultado["invalid_entries"], 1)
        self.assertEqual(resultado["invalid_details"][0]["motivo"], "Título ausente")

    def test_detecta_duplicata_interna_por_doi(self):
        conteudo = b"""
@article{primeiro, title={Primeiro titulo}, doi={10.1/ABC}}
@article{segundo, title={Outro titulo}, doi={https://doi.org/10.1/abc}}
"""

        resultado = analisar_bibtex(conteudo, "duplicatas.bib")

        self.assertEqual(resultado["duplicates_in_file"], 1)

    def test_aceita_windows_1252(self):
        conteudo = "@article{x, title={Revisão sistemática}}".encode("cp1252")

        resultado = analisar_bibtex(conteudo, "cp1252.bib")

        self.assertEqual(resultado["encoding"], "cp1252")
        self.assertEqual(resultado["preview"][0]["Título"], "Revisão sistemática")

    def test_rejeita_arquivo_vazio_ou_extensao_incorreta(self):
        with self.assertRaises(ErroBibTeX):
            analisar_bibtex(b"", "vazio.bib")
        with self.assertRaises(ErroBibTeX):
            analisar_bibtex(b"@article{x, title={Teste}}", "teste.txt")

    def test_importacao_registra_lote_raw_e_relatorio(self):
        conteudo = b"""
@article{novo, title={Novo artigo}, doi={10.1/novo}}
@article{existente, title={Artigo existente}, doi={10.1/existente}}
"""
        chamadas = {"artigos": [], "relatorios": []}

        def registrar_busca(project_id, fonte, query_text, parametros):
            self.assertEqual(project_id, "projeto-1")
            self.assertEqual(fonte, "BibTeX")
            self.assertEqual(query_text, "lote.bib")
            self.assertEqual(parametros["status"], "processing")
            return "busca-1"

        def salvar_artigo_coletado(**kwargs):
            chamadas["artigos"].append(kwargs)
            return len(chamadas["artigos"]) == 1

        def atualizar_metadados_busca(project_id, busca_id, parametros):
            chamadas["relatorios"].append((project_id, busca_id, parametros))

        repositorio = SimpleNamespace(
            registrar_busca=registrar_busca,
            salvar_artigo_coletado=salvar_artigo_coletado,
            atualizar_metadados_busca=atualizar_metadados_busca,
        )

        relatorio = importar_bibtex(
            "projeto-1",
            conteudo,
            "lote.bib",
            _repositorio=repositorio,
        )

        self.assertEqual(relatorio["new_papers"], 1)
        self.assertEqual(relatorio["merged_records"], 1)
        self.assertEqual(relatorio["status"], "completed")
        self.assertEqual(len(chamadas["artigos"]), 2)
        self.assertIn("raw_entry", chamadas["artigos"][0]["registro_bruto"])
        self.assertEqual(chamadas["relatorios"][0][1], "busca-1")


if __name__ == "__main__":
    unittest.main()
