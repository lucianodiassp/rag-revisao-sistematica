#!/bin/sh
set -eu

echo "Aplicando migrações do banco de dados..."

for migration in /migrations/0*.sql; do
    echo "Executando $(basename "$migration")"
    psql --set ON_ERROR_STOP=1 --file "$migration"
done

echo "Migrações concluídas com sucesso."
