-- Внутренние звонки: Echo() заменён на Dial(PJSIP/${EXTEN})
-- PJSIP realtime: колонка mailboxes, которую запрашивает Asterisk при старте

ALTER TABLE ps_endpoints
    ADD COLUMN mailboxes VARCHAR(80) DEFAULT NULL;

UPDATE ast_config
SET var_val = '_XXX,n,Dial(PJSIP/${EXTEN},20)'
WHERE filename = 'extensions.conf'
  AND var_name = 'exten'
  AND var_val LIKE '%Echo()%';

DELETE FROM ast_config
WHERE filename = 'extensions.conf'
  AND var_name = 'exten'
  AND (
    var_val LIKE '%Playback%'
    OR var_val = '_XXX,n,Answer()'
  );
