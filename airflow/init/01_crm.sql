CREATE TABLE IF NOT EXISTS customers (
    id         BIGSERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name  VARCHAR(100) NOT NULL,
    email      VARCHAR(255) NOT NULL UNIQUE,
    phone      VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO customers (first_name, last_name, email, phone, updated_at)
VALUES
    ('Prothetic', 'One',   'prothetic1@example.com', '+79001234567', now() - interval '1 day'),
    ('Prothetic', 'Two',   'prothetic2@example.com', '+79001234568', now() - interval '1 day'),
    ('Prothetic', 'Three', 'prothetic3@example.com', '+79001234569', now() - interval '1 day');