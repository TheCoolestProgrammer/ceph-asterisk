-- Миграция: изоляция ast_config по АТС (instance_id + VIEW на стороне приложения)
ALTER TABLE ast_config
    ADD COLUMN instance_id INT NOT NULL DEFAULT 0;

CREATE INDEX idx_ast_config_instance_id ON ast_config (instance_id);

-- Привязать существующие строки к инстансу вручную или удалить их перед снятием DEFAULT:
-- UPDATE ast_config SET instance_id = <id> WHERE ...;

ALTER TABLE ast_config
    MODIFY instance_id INT NOT NULL;
