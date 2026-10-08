"""Буквы двух алфавитов, на которых пишут резюме и вакансии.

По ним судят, на каком языке текст и латинское ли это имя технологии, а по
русскому слову в перечне навыков — где кончается имя и начинается уточнение:
«Docker в продакшене» называет Docker, а «продакшене» — не второе имя.
"""

import re

CYRILLIC_LETTER = re.compile(r"[а-яё]", re.IGNORECASE)
LATIN_LETTER = re.compile(r"[a-z]", re.IGNORECASE)
CYRILLIC_WORD = re.compile(r"[а-яё]+", re.IGNORECASE)
