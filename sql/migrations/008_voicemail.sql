-- Voicemail: static realtime (voicemail.conf), диалплан *97 / VoiceMail, MWI на 101/102
-- Применять в БД CDR (MYSQL_DATABASE_CDR). instance_id — из ast_config.

-- [general] для каждого инстанса (один раз)
INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT i.instance_id, 1, v.var_metric, 'voicemail.conf', 'general', v.var_name, v.var_val, 0
FROM (SELECT DISTINCT instance_id FROM ast_config) i
CROSS JOIN (
    SELECT 1 AS var_metric, 'format' AS var_name, 'wav49|gsm|wav' AS var_val
    UNION ALL SELECT 2, 'serveremail', 'asterisk'
    UNION ALL SELECT 3, 'attach', 'yes'
    UNION ALL SELECT 4, 'skipms', '3000'
    UNION ALL SELECT 5, 'maxsilence', '10'
    UNION ALL SELECT 6, 'minmessage', '1'
    UNION ALL SELECT 7, 'maxmessage', '300'
    UNION ALL SELECT 8, 'sendvoicemail', 'yes'
    UNION ALL SELECT 9, 'review', 'yes'
) v
WHERE NOT EXISTS (
    SELECT 1 FROM ast_config c
    WHERE c.instance_id = i.instance_id
      AND c.filename = 'voicemail.conf'
      AND c.category = 'general'
);

-- Тестовые ящики 101/102
INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT i.instance_id, 2, 1, 'voicemail.conf', 'default', '101', '4242,Test Operator 101', 0
FROM (SELECT DISTINCT instance_id FROM ast_config) i
WHERE NOT EXISTS (
    SELECT 1 FROM ast_config c
    WHERE c.instance_id = i.instance_id AND c.filename = 'voicemail.conf'
      AND c.category = 'default' AND c.var_name = '101'
);

INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT i.instance_id, 2, 2, 'voicemail.conf', 'default', '102', '4242,Test Operator 102', 0
FROM (SELECT DISTINCT instance_id FROM ast_config) i
WHERE NOT EXISTS (
    SELECT 1 FROM ast_config c
    WHERE c.instance_id = i.instance_id AND c.filename = 'voicemail.conf'
      AND c.category = 'default' AND c.var_name = '102'
);

-- MWI для тестовых endpoint'ов
UPDATE ps_endpoints e
INNER JOIN ps_aors a ON e.aors_id = a.pk
SET e.mailboxes = CONCAT(e.id, '@default')
WHERE e.id IN ('101', '102')
  AND (e.mailboxes IS NULL OR e.mailboxes = '');

-- *97 — прослушивание с софтфона
INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT i.instance_id,
       COALESCE((
           SELECT MAX(c.cat_metric) FROM ast_config c
           WHERE c.instance_id = i.instance_id AND c.filename = 'extensions.conf'
             AND c.category = 'from-internal'
       ), 0) + 1,
       1,
       'extensions.conf', 'from-internal', 'exten', '*97,1,NoOp(Доступ к голосовой почте)', 0
FROM (SELECT DISTINCT instance_id FROM ast_config) i
WHERE NOT EXISTS (
    SELECT 1 FROM ast_config c
    WHERE c.instance_id = i.instance_id AND c.filename = 'extensions.conf'
      AND c.var_val LIKE '*97,%'
);

INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT c.instance_id, c.cat_metric, 2, 'extensions.conf', 'from-internal', 'exten',
       '*97,n,VoiceMailMain(${CALLERID(num)}@default)', 0
FROM ast_config c
WHERE c.filename = 'extensions.conf' AND c.var_val LIKE '*97,1,%'
  AND NOT EXISTS (
    SELECT 1 FROM ast_config x
    WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
      AND x.var_val LIKE '*97,n,VoiceMailMain%'
  );

INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT c.instance_id, c.cat_metric, 3, 'extensions.conf', 'from-internal', 'exten', '*97,n,Hangup()', 0
FROM ast_config c
WHERE c.filename = 'extensions.conf' AND c.var_val LIKE '*97,1,%'
  AND NOT EXISTS (
    SELECT 1 FROM ast_config x
    WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
      AND x.var_val = '*97,n,Hangup()'
  );

-- VoiceMail после Dial для внутренних (_XXX)
INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT c.instance_id, c.cat_metric,
       COALESCE((
           SELECT MAX(x.var_metric) FROM ast_config x
           WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
             AND x.category = 'from-internal' AND x.var_val LIKE '_XXX,%'
       ), 0) + 1,
       'extensions.conf', 'from-internal', 'exten',
       '_XXX,n,GotoIf($["${DIALSTATUS}"="ANSWER"]?vm_done)', 0
FROM ast_config c
WHERE c.filename = 'extensions.conf' AND c.var_val LIKE '_XXX,%' AND c.var_val LIKE '%Dial(%'
  AND NOT EXISTS (
    SELECT 1 FROM ast_config x
    WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
      AND x.var_val LIKE '_XXX,%VoiceMail%'
  )
LIMIT 1;

INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT c.instance_id, c.cat_metric,
       COALESCE((
           SELECT MAX(x.var_metric) FROM ast_config x
           WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
             AND x.category = 'from-internal'
       ), 0) + 1,
       'extensions.conf', 'from-internal', 'exten', '_XXX,n,VoiceMail(${EXTEN}@default,u)', 0
FROM ast_config c
WHERE c.filename = 'extensions.conf' AND c.var_val LIKE '_XXX,%' AND c.var_val LIKE '%Dial(%'
  AND NOT EXISTS (
    SELECT 1 FROM ast_config x
    WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
      AND x.var_val LIKE '%VoiceMail(${EXTEN}@default%'
  )
LIMIT 1;

INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT c.instance_id, c.cat_metric,
       COALESCE((
           SELECT MAX(x.var_metric) FROM ast_config x
           WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
             AND x.category = 'from-internal'
       ), 0) + 1,
       'extensions.conf', 'from-internal', 'exten', '_XXX,n(vm_done),Hangup()', 0
FROM ast_config c
WHERE c.filename = 'extensions.conf' AND c.var_val LIKE '_XXX,%' AND c.var_val LIKE '%Dial(%'
  AND EXISTS (
    SELECT 1 FROM ast_config x
    WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
      AND x.var_val LIKE '%VoiceMail(${EXTEN}@default%'
  )
  AND NOT EXISTS (
    SELECT 1 FROM ast_config x
    WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
      AND x.var_val = '_XXX,n(vm_done),Hangup()'
  )
LIMIT 1;

DELETE FROM ast_config
WHERE filename = 'extensions.conf'
  AND var_name = 'exten'
  AND var_val IN ('_XXX,n,Hangup()', '_XXX,n,NoOp(DIALSTATUS=${DIALSTATUS})');

-- Внешний 777 -> voicemail 101
INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT c.instance_id, c.cat_metric,
       COALESCE((
           SELECT MAX(x.var_metric) FROM ast_config x
           WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
             AND x.category = 'from-external' AND x.var_val LIKE '777,%'
       ), 0) + 1,
       'extensions.conf', 'from-external', 'exten',
       '777,n,GotoIf($["${DIALSTATUS}"="ANSWER"]?ext_done)', 0
FROM ast_config c
WHERE c.filename = 'extensions.conf' AND c.var_val LIKE '777,%' AND c.var_val LIKE '%Dial(%'
  AND NOT EXISTS (
    SELECT 1 FROM ast_config x
    WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
      AND x.var_val LIKE '777,%VoiceMail%'
  )
LIMIT 1;

INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT c.instance_id, c.cat_metric,
       COALESCE((
           SELECT MAX(x.var_metric) FROM ast_config x
           WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
             AND x.category = 'from-external'
       ), 0) + 1,
       'extensions.conf', 'from-external', 'exten', '777,n,VoiceMail(101@default,u)', 0
FROM ast_config c
WHERE c.filename = 'extensions.conf' AND c.var_val LIKE '777,%' AND c.var_val LIKE '%Dial(%'
  AND NOT EXISTS (
    SELECT 1 FROM ast_config x
    WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
      AND x.var_val LIKE '777,n,VoiceMail(101@default%'
  )
LIMIT 1;

INSERT INTO ast_config (instance_id, cat_metric, var_metric, filename, category, var_name, var_val, commented)
SELECT c.instance_id, c.cat_metric,
       COALESCE((
           SELECT MAX(x.var_metric) FROM ast_config x
           WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
             AND x.category = 'from-external'
       ), 0) + 1,
       'extensions.conf', 'from-external', 'exten', '777,n(ext_done),Hangup()', 0
FROM ast_config c
WHERE c.filename = 'extensions.conf' AND c.var_val LIKE '777,%'
  AND EXISTS (
    SELECT 1 FROM ast_config x
    WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
      AND x.var_val LIKE '777,n,VoiceMail(101@default%'
  )
  AND NOT EXISTS (
    SELECT 1 FROM ast_config x
    WHERE x.instance_id = c.instance_id AND x.filename = 'extensions.conf'
      AND x.var_val = '777,n(ext_done),Hangup()'
  )
LIMIT 1;

DELETE FROM ast_config
WHERE filename = 'extensions.conf'
  AND var_name = 'exten'
  AND var_val = '777,n,Hangup()';
