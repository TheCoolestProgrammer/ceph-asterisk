-- AOR id должен совпадать с user в REGISTER To: (101, не 101-aor)

UPDATE ps_aors SET id = SUBSTRING(id, 1, CHAR_LENGTH(id) - 4)
WHERE id LIKE '%-aor';

UPDATE ps_endpoints SET aors = SUBSTRING(aors, 1, CHAR_LENGTH(aors) - 4)
WHERE aors LIKE '%-aor';
