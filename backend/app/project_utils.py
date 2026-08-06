import re
import unicodedata
import uuid
from copy import deepcopy


def normalizar_doi(doi):
    if not doi:
        return None
    valor = str(doi).strip().lower()
    valor = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", valor)
    return valor or None


def normalizar_titulo(titulo):
    valor = unicodedata.normalize("NFKD", titulo or "")
    valor = "".join(char for char in valor if not unicodedata.combining(char))
    valor = re.sub(r"[^a-z0-9]+", " ", valor.lower())
    return " ".join(valor.split())


def gerar_id_artigo(artigo, project_id):
    """Cria um ID estável para o artigo dentro de um único projeto."""
    doi = normalizar_doi(artigo.get("fontes_dict", {}).get("external_ids", {}).get("doi"))
    if doi:
        identidade_artigo = f"doi:{doi}"
    else:
        identidade_artigo = f"titulo:{normalizar_titulo(artigo.get('titulo', 'Sem título'))}"
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"project:{project_id}|{identidade_artigo}",
        )
    )


def mesclar_proveniencia(atual, nova):
    """Mescla metadados preservando fontes e valores já conhecidos."""
    atual = deepcopy(atual or {})
    nova = nova or {}

    for chave, valor_novo in nova.items():
        valor_atual = atual.get(chave)
        if isinstance(valor_atual, dict) and isinstance(valor_novo, dict):
            atual[chave] = mesclar_proveniencia(valor_atual, valor_novo)
        elif isinstance(valor_atual, list) and isinstance(valor_novo, list):
            atual[chave] = list(dict.fromkeys([*valor_atual, *valor_novo]))
        elif valor_novo not in (None, "", [], {}):
            atual[chave] = valor_novo

    return atual
