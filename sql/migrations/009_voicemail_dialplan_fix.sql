-- Починка voicemail dialplan (после 008). БД CDR.
-- *97 с Answer(); 777 в from-internal; BUSY -> VoiceMail(,b)

-- Удалить старый *97 без Answer
DELETE FROM ast_config
WHERE filename = 'extensions.conf'
  AND var_name = 'exten'
  AND var_val LIKE '*97,%'
  AND var_val NOT LIKE '%Answer()%';

-- Пересоздание *97 — проще через API POST /instances/{id}/reload
-- или Python ensure_voicemail_dialplan().
