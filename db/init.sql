CREATE TABLE orders (
    id           BIGSERIAL PRIMARY KEY,
    sku          TEXT        NOT NULL,
    quantity     INT         NOT NULL,
    status       TEXT        NOT NULL,
    amount_cents BIGINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE inventory (
    sku              TEXT PRIMARY KEY,
    unit_price_cents BIGINT NOT NULL,
    reserved         BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE payments (
    id           BIGSERIAL PRIMARY KEY,
    order_id     BIGINT      NOT NULL,
    amount_cents BIGINT      NOT NULL,
    status       TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO inventory (sku, unit_price_cents) VALUES
    ('SKU-1', 250),
    ('SKU-2', 1299),
    ('SKU-3', 4500);
