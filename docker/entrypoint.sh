#!/bin/sh
set -eu

# O volume privado pertence ao Docker e pode conservar o UID de uma imagem antiga.
chown -R ragapp:ragapp /app/data/private

# Volumes nomeados da implantação Web começam pertencendo ao root. Bind mounts da
# instalação local continuam seguindo RAG_UID/RAG_GID e não são alterados.
if [ "${RAG_MANAGED_STORAGE:-false}" = "true" ]; then
    chown -R ragapp:ragapp /app/data/pdfs /app/data/backups
fi

if ! gosu ragapp test -w /app/data/pdfs; then
    echo "Sem permissão de escrita em /app/data/pdfs." >&2
    echo "Em Linux, reconstrua definindo RAG_UID e RAG_GID para o usuário local." >&2
    exit 1
fi

if ! gosu ragapp test -w /app/data/backups; then
    echo "Sem permissão de escrita em /app/data/backups." >&2
    echo "Em Linux, reconstrua definindo RAG_UID e RAG_GID para o usuário local." >&2
    exit 1
fi

exec gosu ragapp "$@"
