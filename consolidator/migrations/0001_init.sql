-- 0001_init.sql
-- Esquema base del maestro SQLite. Idempotente (IF NOT EXISTS) para que
-- reaplicar las migraciones sea seguro.

-- Control de migraciones aplicadas (lo usa el runner).
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Maestro de registros. Llave de identidad por fuente: (fuente, id).
-- id se guarda como TEXT para no perder precisión de los bigint de las fuentes.
CREATE TABLE IF NOT EXISTS registros (
    id                     TEXT NOT NULL,
    fuente                 TEXT NOT NULL,
    nombre                 TEXT,
    cedula                 TEXT,
    edad                   INTEGER,
    ultima_ubicacion       TEXT,
    telefono_contacto      TEXT,
    observaciones          TEXT,
    estado                 TEXT,
    ubicacion_encontrado   TEXT,
    encontrado_por         TEXT,
    encontrado_por_cedula  TEXT,
    foto_url               TEXT,
    fecha_registro         TEXT,
    fecha_actualizacion    TEXT,
    es_menor               INTEGER,            -- 0/1
    content_hash           TEXT NOT NULL,      -- hash del contenido (sin fecha_actualizacion)
    first_seen             TEXT NOT NULL,      -- nunca se sobrescribe en UPDATE
    last_seen              TEXT NOT NULL,
    presente               INTEGER NOT NULL DEFAULT 1,  -- visto en la última corrida
    PRIMARY KEY (fuente, id)
);

CREATE INDEX IF NOT EXISTS idx_registros_hash   ON registros(content_hash);
CREATE INDEX IF NOT EXISTS idx_registros_fuente ON registros(fuente);

-- Bitácora de cada corrida del consolidador (la llenan las corridas, no el seed).
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    started_at    TEXT NOT NULL,
    procesados    INTEGER NOT NULL DEFAULT 0,
    nuevos        INTEGER NOT NULL DEFAULT 0,
    actualizados  INTEGER NOT NULL DEFAULT 0,
    sin_cambio    INTEGER NOT NULL DEFAULT 0,
    rechazados    INTEGER NOT NULL DEFAULT 0
);
