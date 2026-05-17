-- ODBC realtime: один cat_metric на [context] в extensions.conf.
-- Иначе Asterisk видит только первый блок (1 priority) — см. res_config_odbc.c.
-- БД CDR. После применения: asterisk -rx "dialplan reload"

-- from-external: свести все exten к минимальному cat_metric контекста
SET @fix_inst := 0;
-- Задайте instance_id вручную или выполните через POST /instances/{id}/reload

-- Пример для всех инстансов (перенумерация var_metric):
-- UPDATE выполняется надёжнее из API ensure_voicemail_dialplan().
