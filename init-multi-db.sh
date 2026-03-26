#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE USER parking WITH PASSWORD 'parking';
    CREATE DATABASE parking OWNER parking;
EOSQL
