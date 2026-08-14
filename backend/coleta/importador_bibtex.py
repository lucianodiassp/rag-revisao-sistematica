"""Importação rastreável de arquivos BibTeX para o fluxo de triagem."""

import hashlib
import os
import re
import unicodedata

from backend.app.project_utils import gerar_id_artigo, normalizar_doi, normalizar_titulo
from backend.app.deduplication import (
    ACTION_AUTO_CREATE,
    ACTION_AUTO_MERGE,
    ACTION_PENDING_REVIEW,
)


FONTE_BIBTEX = "BibTeX"
TAMANHO_MAXIMO_BYTES = 20 * 1024 * 1024
TIPOS_IGNORADOS = {"comment", "preamble", "string"}


class ErroBibTeX(ValueError):
    """Erro de validação ou leitura de um arquivo BibTeX."""


def _decodificar(conteudo):
    if not conteudo:
        raise ErroBibTeX("O arquivo BibTeX está vazio.")
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise ErroBibTeX("O arquivo excede o limite de 20 MB.")

    codificacoes = (
        ("utf-8-sig", "cp1252")
        if conteudo.startswith(b"\xef\xbb\xbf")
        else ("utf-8", "cp1252")
    )
    for codificacao in codificacoes:
        try:
            return conteudo.decode(codificacao), codificacao
        except UnicodeDecodeError:
            continue
    raise ErroBibTeX("Não foi possível identificar a codificação do arquivo.")


def _escapado(texto, indice):
    barras = 0
    indice -= 1
    while indice >= 0 and texto[indice] == "\\":
        barras += 1
        indice -= 1
    return barras % 2 == 1


def _ler_valor(texto, indice, fechamento_entrada):
    while indice < len(texto) and texto[indice].isspace():
        indice += 1
    if indice >= len(texto):
        raise ErroBibTeX("Valor de campo incompleto no fim do arquivo.")

    abertura = texto[indice]
    if abertura == "{":
        inicio = indice + 1
        profundidade = 1
        indice += 1
        while indice < len(texto) and profundidade:
            if texto[indice] == "{" and not _escapado(texto, indice):
                profundidade += 1
            elif texto[indice] == "}" and not _escapado(texto, indice):
                profundidade -= 1
            indice += 1
        if profundidade:
            raise ErroBibTeX("Campo com chaves não fechadas.")
        return texto[inicio : indice - 1], indice

    if abertura == '"':
        inicio = indice + 1
        indice += 1
        profundidade_chaves = 0
        while indice < len(texto):
            caractere = texto[indice]
            if caractere == "{" and not _escapado(texto, indice):
                profundidade_chaves += 1
            elif caractere == "}" and not _escapado(texto, indice):
                profundidade_chaves = max(0, profundidade_chaves - 1)
            elif caractere == '"' and not _escapado(texto, indice) and profundidade_chaves == 0:
                return texto[inicio:indice], indice + 1
            indice += 1
        raise ErroBibTeX("Campo entre aspas não foi fechado.")

    inicio = indice
    while indice < len(texto) and texto[indice] not in (",", fechamento_entrada):
        indice += 1
    return texto[inicio:indice].strip(), indice


def _pular_bloco(texto, indice, abertura):
    fechamento = "}" if abertura == "{" else ")"
    profundidade = 1
    indice += 1
    em_aspas = False
    while indice < len(texto) and profundidade:
        caractere = texto[indice]
        if caractere == '"' and not _escapado(texto, indice):
            em_aspas = not em_aspas
        elif not em_aspas and caractere == abertura and not _escapado(texto, indice):
            profundidade += 1
        elif not em_aspas and caractere == fechamento and not _escapado(texto, indice):
            profundidade -= 1
        indice += 1
    if profundidade:
        raise ErroBibTeX("Entrada BibTeX não foi fechada.")
    return indice


def _parsear_entradas(texto):
    entradas = []
    indice = 0
    while True:
        inicio_entrada = texto.find("@", indice)
        if inicio_entrada < 0:
            break
        indice = inicio_entrada + 1
        while indice < len(texto) and texto[indice].isspace():
            indice += 1
        inicio_tipo = indice
        while indice < len(texto) and (texto[indice].isalnum() or texto[indice] in "_-:"):
            indice += 1
        tipo = texto[inicio_tipo:indice].strip().lower()
        while indice < len(texto) and texto[indice].isspace():
            indice += 1
        if not tipo or indice >= len(texto) or texto[indice] not in "{(":
            continue

        abertura = texto[indice]
        fechamento = "}" if abertura == "{" else ")"
        if tipo in TIPOS_IGNORADOS:
            indice = _pular_bloco(texto, indice, abertura)
            continue

        indice += 1
        while indice < len(texto) and texto[indice].isspace():
            indice += 1
        inicio_chave = indice
        while indice < len(texto) and texto[indice] not in (",", fechamento):
            indice += 1
        chave = texto[inicio_chave:indice].strip()
        if indice >= len(texto) or texto[indice] == fechamento:
            raise ErroBibTeX(f"Entrada '{chave or tipo}' não possui campos.")
        indice += 1

        campos = {}
        while indice < len(texto):
            while indice < len(texto) and (texto[indice].isspace() or texto[indice] == ","):
                indice += 1
            if indice >= len(texto):
                raise ErroBibTeX(f"Entrada '{chave or tipo}' não foi fechada.")
            if texto[indice] == fechamento:
                indice += 1
                break

            inicio_campo = indice
            while indice < len(texto) and (texto[indice].isalnum() or texto[indice] in "_-"):
                indice += 1
            nome_campo = texto[inicio_campo:indice].strip().lower()
            while indice < len(texto) and texto[indice].isspace():
                indice += 1
            if not nome_campo or indice >= len(texto) or texto[indice] != "=":
                raise ErroBibTeX(f"Campo inválido na entrada '{chave or tipo}'.")
            valor, indice = _ler_valor(texto, indice + 1, fechamento)
            campos[nome_campo] = valor.strip()

        entradas.append(
            {
                "entry_type": tipo,
                "citation_key": chave,
                "fields": campos,
                "raw_entry": texto[inicio_entrada:indice].strip(),
            }
        )
    return entradas


_ACENTOS_LATEX = {
    "'": "\u0301",
    "`": "\u0300",
    '"': "\u0308",
    "^": "\u0302",
    "~": "\u0303",
    "=": "\u0304",
    ".": "\u0307",
    "u": "\u0306",
    "v": "\u030c",
    "H": "\u030b",
    "c": "\u0327",
    "k": "\u0328",
}


def _substituir_acento(casamento):
    acento, letra = casamento.group(1), casamento.group(2)
    return unicodedata.normalize("NFC", letra + _ACENTOS_LATEX[acento])


def _limpar_latex(valor):
    if not valor:
        return ""
    texto = valor.replace("\r", " ").replace("\n", " ")
    texto = re.sub(
        r"\{?\\([`'\"\^~=\.uvHck])\s*\{?([A-Za-z])\}?\}?",
        _substituir_acento,
        texto,
    )
    substituicoes = {
        r"\&": "&",
        r"\_": "_",
        r"\%": "%",
        r"\#": "#",
        r"\$": "$",
        r"\textasciitilde": "~",
        r"\textendash": "–",
        r"\textemdash": "—",
        r"\ss": "ß",
        r"\ae": "æ",
        r"\AE": "Æ",
        r"\oe": "œ",
        r"\OE": "Œ",
        r"\o": "ø",
        r"\O": "Ø",
        r"\l": "ł",
        r"\L": "Ł",
    }
    for origem, destino in substituicoes.items():
        texto = texto.replace(origem, destino)
    texto = re.sub(r"\\(?:textit|textbf|emph|mathrm|textrm|url)\s*\{([^{}]*)\}", r"\1", texto)
    texto = texto.replace(r"\{", "{").replace(r"\}", "}")
    texto = texto.replace("{", "").replace("}", "")
    return " ".join(texto.split()).strip()


def _separar_autores(valor):
    return [
        autor
        for autor in (_limpar_latex(item) for item in re.split(r"\s+and\s+", valor or ""))
        if autor
    ]


def _separar_palavras_chave(valor):
    return [item.strip() for item in _limpar_latex(valor).split(";") if item.strip()]


def _fonte_da_entrada(campos):
    identificador = _limpar_latex(campos.get("unique-id", ""))
    if identificador.upper().startswith("WOS:"):
        return "Web of Science (BibTeX)"
    return FONTE_BIBTEX


def _normalizar_entrada(entrada, nome_arquivo, hash_arquivo):
    campos = entrada["fields"]
    titulo = _limpar_latex(campos.get("title", ""))
    if not titulo:
        return None, "Título ausente"

    abstract = _limpar_latex(campos.get("abstract", ""))
    doi = normalizar_doi(_limpar_latex(campos.get("doi", "")))
    identificador_wos = _limpar_latex(campos.get("unique-id", "")) or None
    ano_texto = _limpar_latex(campos.get("year", ""))
    ano = int(ano_texto[:4]) if re.match(r"^\d{4}", ano_texto) else None
    revista = _limpar_latex(campos.get("journal") or campos.get("booktitle") or "")
    palavras_chave = _separar_palavras_chave(
        campos.get("keywords") or campos.get("author-keywords") or ""
    )
    fonte = _fonte_da_entrada(campos)
    external_ids = {
        "doi": doi,
        "bibtex_key": entrada["citation_key"] or None,
    }
    if identificador_wos:
        external_ids["wos"] = identificador_wos

    fontes_dict = {
        "sources": [fonte],
        "external_ids": external_ids,
        "metadata": {
            "publication_year": ano,
            "authors": _separar_autores(campos.get("author", "")),
            "journal_name": revista or "Periódico não informado",
            "language": _limpar_latex(campos.get("language", "")) or "não informado",
            "document_type": entrada["entry_type"],
            "volume": _limpar_latex(campos.get("volume", "")) or None,
            "pages": _limpar_latex(campos.get("pages", "")) or None,
            "url": _limpar_latex(campos.get("url", "")) or None,
            "import_file": nome_arquivo,
            "import_sha256": hash_arquivo,
        },
        "concepts": palavras_chave,
    }
    artigo = {
        "titulo": titulo,
        "abstract": abstract or "Abstract indisponível no arquivo BibTeX.",
        "fontes_dict": fontes_dict,
        "registro_bruto": {
            "format": "BibTeX",
            "source": fonte,
            "file_name": nome_arquivo,
            "file_sha256": hash_arquivo,
            "entry_type": entrada["entry_type"],
            "citation_key": entrada["citation_key"],
            "fields": campos,
            "raw_entry": entrada["raw_entry"],
        },
        "possui_abstract": bool(abstract),
        "possui_doi": bool(doi),
    }
    return artigo, None


def analisar_bibtex(conteudo, nome_arquivo="importacao.bib", limite_preview=10):
    """Lê, valida e normaliza um BibTeX sem alterar o banco."""
    if not str(nome_arquivo).lower().endswith(".bib"):
        raise ErroBibTeX("Selecione um arquivo com extensão .bib.")
    texto, codificacao = _decodificar(conteudo)
    entradas = _parsear_entradas(texto)
    if not entradas:
        raise ErroBibTeX("Nenhuma entrada bibliográfica foi encontrada no arquivo.")

    nome_seguro = os.path.basename(str(nome_arquivo))
    hash_arquivo = hashlib.sha256(conteudo).hexdigest()
    artigos = []
    invalidos = []
    for entrada in entradas:
        artigo, motivo = _normalizar_entrada(entrada, nome_seguro, hash_arquivo)
        if motivo:
            invalidos.append(
                {"citation_key": entrada.get("citation_key") or "sem chave", "motivo": motivo}
            )
        else:
            artigos.append(artigo)

    identidades = []
    for artigo in artigos:
        doi = artigo["fontes_dict"]["external_ids"].get("doi")
        identidade = f"doi:{doi}" if doi else f"titulo:{normalizar_titulo(artigo['titulo'])}"
        identidades.append(identidade)

    preview = []
    for artigo in artigos[:limite_preview]:
        metadados = artigo["fontes_dict"]["metadata"]
        preview.append(
            {
                "Título": artigo["titulo"],
                "Ano": metadados["publication_year"],
                "Autores": "; ".join(metadados["authors"][:3]),
                "DOI": artigo["fontes_dict"]["external_ids"].get("doi") or "",
                "Abstract": "Sim" if artigo["possui_abstract"] else "Não",
            }
        )

    return {
        "file_name": nome_seguro,
        "file_sha256": hash_arquivo,
        "encoding": codificacao,
        "total_entries": len(entradas),
        "valid_entries": len(artigos),
        "invalid_entries": len(invalidos),
        "without_abstract": sum(not artigo["possui_abstract"] for artigo in artigos),
        "without_doi": sum(not artigo["possui_doi"] for artigo in artigos),
        "duplicates_in_file": len(identidades) - len(set(identidades)),
        "invalid_details": invalidos,
        "preview": preview,
        "articles": artigos,
    }


def _metadados_relatorio(analise, status, **adicionais):
    metadados = {
        "operation": "bibtex_import",
        "status": status,
        "file_name": analise["file_name"],
        "file_sha256": analise["file_sha256"],
        "encoding": analise["encoding"],
        "total_entries": analise["total_entries"],
        "valid_entries": analise["valid_entries"],
        "invalid_entries": analise["invalid_entries"],
        "without_abstract": analise["without_abstract"],
        "without_doi": analise["without_doi"],
        "duplicates_in_file": analise["duplicates_in_file"],
        "invalid_details": analise["invalid_details"][:100],
    }
    metadados.update(adicionais)
    return metadados


def importar_bibtex(project_id, conteudo, nome_arquivo="importacao.bib", _repositorio=None):
    """Importa o arquivo para o projeto e registra um relatório da execução."""
    if _repositorio is None:
        from backend.app import database as _repositorio

    analise = analisar_bibtex(conteudo, nome_arquivo)
    busca_id = _repositorio.registrar_busca(
        project_id,
        FONTE_BIBTEX,
        analise["file_name"],
        _metadados_relatorio(analise, "processing"),
    )
    novos = 0
    mesclados = 0
    pendentes_revisao = 0
    erros = []

    for artigo in analise["articles"]:
        try:
            artigo_id = gerar_id_artigo(artigo, project_id)
            resultado_persistencia = _repositorio.salvar_artigo_coletado(
                project_id=project_id,
                id_artigo=artigo_id,
                titulo=artigo["titulo"],
                abstract=artigo["abstract"],
                fontes_dict=artigo["fontes_dict"],
                search_query_id=busca_id,
                fonte=artigo["fontes_dict"]["sources"][0],
                registro_bruto=artigo["registro_bruto"],
            )
            if isinstance(resultado_persistencia, dict):
                status_deduplicacao = resultado_persistencia.get("status")
            else:
                # Compatibilidade com repositórios de teste e integrações antigas.
                status_deduplicacao = (
                    ACTION_AUTO_CREATE if resultado_persistencia else ACTION_AUTO_MERGE
                )
            if status_deduplicacao == ACTION_AUTO_CREATE:
                novos += 1
            elif status_deduplicacao == ACTION_AUTO_MERGE:
                mesclados += 1
            elif status_deduplicacao == ACTION_PENDING_REVIEW:
                pendentes_revisao += 1
        except Exception as erro:
            erros.append(
                {
                    "citation_key": artigo["registro_bruto"].get("citation_key") or "sem chave",
                    "motivo": str(erro)[:500],
                }
            )

    status = "completed" if not erros else "completed_with_errors"
    relatorio = _metadados_relatorio(
        analise,
        status,
        new_papers=novos,
        merged_records=mesclados,
        pending_deduplication_review=pendentes_revisao,
        persistence_errors=len(erros),
        persistence_error_details=erros[:100],
    )
    _repositorio.atualizar_metadados_busca(project_id, busca_id, relatorio)
    return {
        **relatorio,
        "search_query_id": str(busca_id),
    }
