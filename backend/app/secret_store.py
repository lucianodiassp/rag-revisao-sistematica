import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from platformdirs import user_data_path


MASTER_KEY_ENV = "AI_LOCAL_MASTER_KEY"
MASTER_KEY_PATH_ENV = "AI_LOCAL_MASTER_KEY_PATH"
APP_DATA_NAME = "rag-revisao-sistematica"


def get_master_key_path():
    configurado = os.getenv(MASTER_KEY_PATH_ENV)
    if configurado:
        return Path(configurado).expanduser().resolve()
    return Path(user_data_path(APP_DATA_NAME, appauthor=False)) / "master.key"


def _validar_chave(chave):
    try:
        Fernet(chave)
    except (TypeError, ValueError) as erro:
        raise RuntimeError(
            f"{MASTER_KEY_ENV} não contém uma chave Fernet válida."
        ) from erro
    return chave


def _ler_ou_criar_chave(criar=False):
    chave_ambiente = os.getenv(MASTER_KEY_ENV)
    if chave_ambiente:
        return _validar_chave(chave_ambiente.strip().encode("ascii"))

    caminho = get_master_key_path()
    if caminho.exists():
        return _validar_chave(caminho.read_bytes().strip())
    if not criar:
        raise RuntimeError(
            "A chave-mestra local não foi encontrada. Salve uma credencial por uma "
            "tela de configuração ou restaure o arquivo de chave-mestra."
        )

    caminho.parent.mkdir(parents=True, exist_ok=True)
    chave = Fernet.generate_key()
    try:
        descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descritor, "wb") as arquivo:
            arquivo.write(chave)
    except FileExistsError:
        chave = caminho.read_bytes().strip()
    return _validar_chave(chave)


def encrypt_secret(segredo):
    segredo = str(segredo or "").strip()
    if not segredo:
        raise ValueError("A chave de API não pode ficar vazia.")
    return Fernet(_ler_ou_criar_chave(criar=True)).encrypt(
        segredo.encode("utf-8")
    ).decode("ascii")


def decrypt_secret(conteudo_cifrado):
    try:
        return Fernet(_ler_ou_criar_chave(criar=False)).decrypt(
            str(conteudo_cifrado).encode("ascii")
        ).decode("utf-8")
    except InvalidToken as erro:
        raise RuntimeError(
            "Não foi possível decifrar a credencial. A chave-mestra local pode ter "
            "sido removida ou pertencer a outra instalação."
        ) from erro


def secret_hint(segredo):
    segredo = str(segredo or "").strip()
    if len(segredo) <= 4:
        return "••••"
    return f"••••{segredo[-4:]}"
