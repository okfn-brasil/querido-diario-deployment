#!/bin/bash
set -e

# Create additional databases and users
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create companies database and user for API
    CREATE DATABASE companiesdb;
    CREATE USER companies WITH ENCRYPTED PASSWORD 'companies';
    GRANT ALL PRIVILEGES ON DATABASE companiesdb TO companies;
    
    -- Grant necessary permissions
    \c companiesdb
    GRANT ALL ON SCHEMA public TO companies;
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO companies;
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO companies;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO companies;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO companies;
EOSQL

echo "Multiple databases and users created successfully!"