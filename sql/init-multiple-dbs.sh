#!/bin/bash
set -e

echo ">>> Creating MTG Data Warehouse Database (mtg_dw)..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE mtg_dw'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mtg_dw')\gexec
    GRANT ALL PRIVILEGES ON DATABASE mtg_dw TO $POSTGRES_USER;
EOSQL

echo ">>> Initializing Schema in mtg_dw..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "mtg_dw" -f /docker-entrypoint-initdb.d/init_db.sql

echo ">>> PostgreSQL Initialization Complete!"
