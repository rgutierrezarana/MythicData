-- ============================================================================
-- MTG Data Warehouse & Pricing Database Schema
-- ============================================================================

-- Crear base de datos mtg_dw si no existe (manejado en script de entrada si es necesario)
-- Extensiones útiles
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ----------------------------------------------------------------------------
-- 1. Tabla de Ediciones / Sets
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sets (
    code VARCHAR(10) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    release_date DATE,
    base_set_size INTEGER,
    total_set_size INTEGER,
    set_type VARCHAR(50),
    block VARCHAR(100),
    keyrune_code VARCHAR(50),
    is_online_only BOOLEAN DEFAULT FALSE,
    is_foil_only BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sets_release_date ON sets(release_date DESC);
CREATE INDEX IF NOT EXISTS idx_sets_type ON sets(set_type);

-- ----------------------------------------------------------------------------
-- 2. Tabla de Cartas (Cards)
-- Una carta puede estar en múltiples sets; cada impresión física tiene su propio uuid único.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cards (
    uuid VARCHAR(64) PRIMARY KEY,
    set_code VARCHAR(10) NOT NULL REFERENCES sets(code) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    collector_number VARCHAR(50),
    rarity VARCHAR(50),
    mana_cost VARCHAR(100),
    mana_value NUMERIC(10,2),
    type_line VARCHAR(255),
    scryfall_id VARCHAR(64),
    tcgplayer_product_id VARCHAR(64),
    finishes VARCHAR(100),
    artist VARCHAR(255),
    availability VARCHAR(100),
    current_price_usd NUMERIC(12,4),
    current_price_eur NUMERIC(12,4),
    current_price_foil NUMERIC(12,4),
    current_price_date DATE,
    current_price_provider VARCHAR(50),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Migraciones seguras para instancias existentes
ALTER TABLE cards ADD COLUMN IF NOT EXISTS oracle_text TEXT;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS colors VARCHAR(50);
ALTER TABLE cards ADD COLUMN IF NOT EXISTS color_identity VARCHAR(50);
ALTER TABLE cards ADD COLUMN IF NOT EXISTS power VARCHAR(20);
ALTER TABLE cards ADD COLUMN IF NOT EXISTS toughness VARCHAR(20);
ALTER TABLE cards ADD COLUMN IF NOT EXISTS loyalty VARCHAR(20);
ALTER TABLE cards ADD COLUMN IF NOT EXISTS current_price_usd NUMERIC(12,4);
ALTER TABLE cards ADD COLUMN IF NOT EXISTS current_price_eur NUMERIC(12,4);
ALTER TABLE cards ADD COLUMN IF NOT EXISTS current_price_foil NUMERIC(12,4);
ALTER TABLE cards ADD COLUMN IF NOT EXISTS current_price_date DATE;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS current_price_provider VARCHAR(50);

CREATE INDEX IF NOT EXISTS idx_cards_set_code ON cards(set_code);
CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);
CREATE INDEX IF NOT EXISTS idx_cards_rarity ON cards(rarity);
CREATE INDEX IF NOT EXISTS idx_cards_scryfall_id ON cards(scryfall_id);
CREATE INDEX IF NOT EXISTS idx_cards_tcgplayer_id ON cards(tcgplayer_product_id);
CREATE INDEX IF NOT EXISTS idx_cards_price_usd ON cards(current_price_usd);
CREATE INDEX IF NOT EXISTS idx_cards_price_date ON cards(current_price_date DESC);

-- ----------------------------------------------------------------------------
-- 3. Tabla de Precios Actuales (Card Current Prices)
-- Snapshot de los precios más recientes por carta, tienda, formato y acabado.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS card_current_prices (
    id BIGSERIAL PRIMARY KEY,
    card_uuid VARCHAR(64) NOT NULL REFERENCES cards(uuid) ON DELETE CASCADE,
    set_code VARCHAR(10) NOT NULL,
    provider VARCHAR(50) NOT NULL,       -- tcgplayer, cardmarket, cardkingdom, manapool, cardsphere
    game_format VARCHAR(20) NOT NULL,    -- paper, mtgo
    price_type VARCHAR(20) NOT NULL,     -- retail, buylist
    finish VARCHAR(20) NOT NULL,         -- normal, foil, etched
    currency VARCHAR(10) NOT NULL,       -- USD, EUR
    price NUMERIC(12,4) NOT NULL,
    price_date DATE NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_card_current_price UNIQUE (card_uuid, provider, game_format, price_type, finish, currency)
);

CREATE INDEX IF NOT EXISTS idx_curr_prices_card_uuid ON card_current_prices(card_uuid);
CREATE INDEX IF NOT EXISTS idx_curr_prices_set_code ON card_current_prices(set_code);
CREATE INDEX IF NOT EXISTS idx_curr_prices_provider ON card_current_prices(provider);
CREATE INDEX IF NOT EXISTS idx_curr_prices_date ON card_current_prices(price_date DESC);

-- ----------------------------------------------------------------------------
-- 4. Tabla de Histórico de Precios (Card Price History)
-- Almacena la serie temporal de precios para generar gráficas de evolución.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS card_price_history (
    id BIGSERIAL PRIMARY KEY,
    card_uuid VARCHAR(64) NOT NULL REFERENCES cards(uuid) ON DELETE CASCADE,
    set_code VARCHAR(10) NOT NULL,
    provider VARCHAR(50) NOT NULL,       -- tcgplayer, cardmarket, cardkingdom, etc.
    game_format VARCHAR(20) NOT NULL,    -- paper, mtgo
    price_type VARCHAR(20) NOT NULL,     -- retail, buylist
    finish VARCHAR(20) NOT NULL,         -- normal, foil, etched
    currency VARCHAR(10) NOT NULL,       -- USD, EUR
    price_date DATE NOT NULL,
    price NUMERIC(12,4) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_card_price_history UNIQUE (card_uuid, provider, game_format, price_type, finish, currency, price_date)
);

CREATE INDEX IF NOT EXISTS idx_hist_prices_card_date ON card_price_history(card_uuid, price_date DESC);
CREATE INDEX IF NOT EXISTS idx_hist_prices_set_date ON card_price_history(set_code, price_date DESC);
CREATE INDEX IF NOT EXISTS idx_hist_prices_date ON card_price_history(price_date DESC);
CREATE INDEX IF NOT EXISTS idx_hist_prices_lookup ON card_price_history(card_uuid, provider, finish, price_date DESC);

-- ----------------------------------------------------------------------------
-- 5. Vistas Analíticas para Frontend / Reportes
-- ----------------------------------------------------------------------------

-- Vista 1: Detalle completo de carta con su edición y precios actuales
CREATE OR REPLACE VIEW v_card_market_summary AS
SELECT 
    c.uuid AS card_uuid,
    c.name AS card_name,
    c.set_code,
    s.name AS set_name,
    s.release_date AS set_release_date,
    c.collector_number,
    c.rarity,
    c.mana_cost,
    c.mana_value,
    c.type_line,
    c.scryfall_id,
    cp.provider,
    cp.game_format,
    cp.price_type,
    cp.finish,
    cp.currency,
    cp.price,
    cp.price_date
FROM cards c
JOIN sets s ON c.set_code = s.code
LEFT JOIN card_current_prices cp ON c.uuid = cp.card_uuid;

-- Vista 2: Evolución histórica con variación día a día para gráficas
CREATE OR REPLACE VIEW v_card_price_trends AS
SELECT 
    h.card_uuid,
    c.name AS card_name,
    c.set_code,
    s.name AS set_name,
    h.provider,
    h.game_format,
    h.price_type,
    h.finish,
    h.currency,
    h.price_date,
    h.price,
    LAG(h.price, 1) OVER (
        PARTITION BY h.card_uuid, h.provider, h.game_format, h.price_type, h.finish, h.currency 
        ORDER BY h.price_date ASC
    ) AS previous_price,
    h.price - LAG(h.price, 1) OVER (
        PARTITION BY h.card_uuid, h.provider, h.game_format, h.price_type, h.finish, h.currency 
        ORDER BY h.price_date ASC
    ) AS price_diff,
    ROUND(
        ( (h.price - LAG(h.price, 1) OVER (
            PARTITION BY h.card_uuid, h.provider, h.game_format, h.price_type, h.finish, h.currency 
            ORDER BY h.price_date ASC
        )) / NULLIF(LAG(h.price, 1) OVER (
            PARTITION BY h.card_uuid, h.provider, h.game_format, h.price_type, h.finish, h.currency 
            ORDER BY h.price_date ASC
        ), 0) ) * 100, 2
    ) AS pct_change
FROM card_price_history h
JOIN cards c ON h.card_uuid = c.uuid
JOIN sets s ON c.set_code = s.code;

-- ----------------------------------------------------------------------------
-- 5. Tabla de Predicciones de Precios con Machine Learning (GBTRegressor)
-- Almacena las proyecciones estimadas del próximo precio calculadas con Apache Spark MLlib.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS card_price_predictions (
    card_uuid VARCHAR(64) PRIMARY KEY REFERENCES cards(uuid) ON DELETE CASCADE,
    current_price NUMERIC(12,4),
    predicted_next_price NUMERIC(12,4),
    expected_change_pct NUMERIC(8,2),
    direction VARCHAR(10),  -- UP, DOWN, STABLE
    confidence_score NUMERIC(5,2),
    model_name VARCHAR(50) DEFAULT 'GBTRegressor',
    features_used VARCHAR(255),
    predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pred_card_uuid ON card_price_predictions(card_uuid);
CREATE INDEX IF NOT EXISTS idx_pred_change ON card_price_predictions(expected_change_pct);
