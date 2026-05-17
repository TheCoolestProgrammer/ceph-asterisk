-- Полная схема ps_contacts для ODBC (если вернёте contact=realtime,ps_contacts в sorcery.conf)
-- Сейчас по умолчанию contact=memory в sorcery.conf.

ALTER TABLE ps_contacts
    ADD COLUMN IF NOT EXISTS outbound_proxy VARCHAR(40) NULL,
    ADD COLUMN IF NOT EXISTS path TEXT NULL,
    ADD COLUMN IF NOT EXISTS qualify_timeout FLOAT NULL,
    ADD COLUMN IF NOT EXISTS reg_server VARCHAR(60) NULL,
    ADD COLUMN IF NOT EXISTS authenticate_qualify ENUM('yes','no') NULL,
    ADD COLUMN IF NOT EXISTS via_addr VARCHAR(40) NULL,
    ADD COLUMN IF NOT EXISTS via_port INT NULL,
    ADD COLUMN IF NOT EXISTS call_id VARCHAR(255) NULL,
    ADD COLUMN IF NOT EXISTS endpoint VARCHAR(40) NULL,
    ADD COLUMN IF NOT EXISTS prune_on_boot ENUM('yes','no') NULL;
