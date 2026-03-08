-- PostgreSQL schema for NYC Sample Sales Tracker
-- Run with: psql $DATABASE_URL -f db_schema.sql
-- Or use the /db-migrate skill

CREATE TABLE IF NOT EXISTS sample_sales (
    id SERIAL PRIMARY KEY,
    brand VARCHAR(255) NOT NULL,
    department VARCHAR(255),
    start_date DATE,
    end_date DATE,
    location TEXT,
    link TEXT,
    notes TEXT,
    source VARCHAR(500),
    scraped_at TIMESTAMP DEFAULT NOW(),
    month_year VARCHAR(7),
    dedup_key VARCHAR(32) UNIQUE
);

CREATE TABLE IF NOT EXISTS discovered_accounts (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(20),
    username VARCHAR(255) UNIQUE,
    source_name VARCHAR(500),
    discovered_from TEXT,
    discovered_date DATE,
    relevance_score FLOAT,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id SERIAL PRIMARY KEY,
    run_at TIMESTAMP DEFAULT NOW(),
    web_sales_count INT,
    social_sales_count INT,
    verified_sales_count INT,
    total_unique INT,
    new_accounts_discovered INT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sales_brand ON sample_sales(brand);
CREATE INDEX IF NOT EXISTS idx_sales_dates ON sample_sales(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_sales_month ON sample_sales(month_year);
CREATE INDEX IF NOT EXISTS idx_sales_scraped ON sample_sales(scraped_at);
CREATE INDEX IF NOT EXISTS idx_accounts_platform ON discovered_accounts(platform);
CREATE INDEX IF NOT EXISTS idx_accounts_enabled ON discovered_accounts(enabled);
CREATE INDEX IF NOT EXISTS idx_runs_date ON scrape_runs(run_at);
