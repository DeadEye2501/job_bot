# Разобранные пары

Пары, про которые уже сказано «это не повтор того». Рецензент по повторам читает
файл вместе с картами и такие пары пропускает.

Отпечатки после ссылок проставляет сборка карт — они же и срок годности:
изменилось тело любой стороны, и пара возвращается в разбор.

- `backend/repository/channels.py:channel_blacklist_candidates` `f7d9dca3` ↔ `backend/repository/companies_card.py:company_blacklist_candidates` `7efd9a7b` ↔ `backend/repository/hr_card.py:hr_blacklist_candidates` `74c8523e` — один глагол над тремя разными предметами: каждый собирает написания своего, а общее сравнение живёт в `blacklist_marks.py` и зовётся всеми тремя
- `backend/repository/merging.py:load_merge_pair` `9565ff4c` ↔ `backend/repository/companies_card.py:merge_company` `a8a5748f` ↔ `backend/repository/hr_card.py:merge_hr` `7c617ca9` — вывод общего уже сделан: в `merging.py` лежит ровно совпадавшая часть, а предметные поля (сайт и написания у компании, переписка и учётная запись Telegram у HR) остались своими у каждого
- `backend/repository/vacancies_list.py:_STATUS_PRIORITY_ACTIVE_FIRST` `eed1e63e` ↔ `backend/repository/vacancies_list.py:_STATUS_PRIORITY_NEW_FIRST` `642ef877` ↔ `backend/repository/vacancies_mini.py:_CHANNEL_VAC_STATUS_RANK` `ba804670` — три порядка статусов для трёх разных сортировок на экранах; места внутри у всех трёх разные, общего «правильного» порядка нет
- `config.py:data_files` `f932f5eb` ↔ `backend/wipe.py:_remove_the_data` `2b2d562f` — своего перечня имён снос не держит вовсе, он берёт его отсюда; повтор был раньше и уже вынесен
- `backend/log_buffer.py:install` `be8754b5` ↔ `backend/wipe.py:_close_log_files` `a1346686` — оба ходят по `root.handlers`, но за разным: первый ищет свой обработчик буфера, чтобы не поставить второй, второй снимает и закрывает файловые
- `tests/backend/test_wipe.py:data_dir` `ba8c8a21` ↔ `tests/conftest.py:TMP_ROOT` `f13191bb` — общий каталог стенда живёт всю сессию и держит базу, а снос проверяется настоящим удалением файлов и потому берёт свой каталог на каждую проверку
- `backend/flows/embeddings.py:embed_text` `dc114f9e` ↔ `backend/flows/rerun.py:_refresh_embedding` `7999ea11` — второй зовёт первого и достраивает вокруг правку кэша отсева; общего тела нет
- `backend/repository/vacancies_list.py:_greatest_pair` `e7bea461` ↔ `backend/repository/vacancies_list.py:_greatest` `3dd7e2ca` — пара «одно — много» рядом: второй сворачивает список колонок первым в цикле
- `backend/llm/candidate.py:format_known_skills` `0e1f0272` ↔ `backend/domain/scoring.py:build_skill_lookup` `32252a79` — оба про навыки анкеты, но первый рисует список для промпта, второй строит ключи для счёта баллов; общее уже вынесено в `domain/skill_names.py` и зовётся обоими
- `backend/domain/verdict.py:decide_vacancy_status` `2b1c6d0c` ↔ `backend/flows/parse.py:_verdict_for` `350698a7` — не повтор, а зов: приговор живёт одним объявлением, а разбор только собирает вокруг него данные
- `backend/repository/blacklist.py:_BLACKLIST_FIELD_UNSET` `76236e12` ↔ `backend/repository/companies_card.py:_COMPANY_FIELD_UNSET` `acf705e8` ↔ `backend/repository/hr_card.py:_HR_FIELD_UNSET` `6ef138d0` — одна идиома «довод не передали» над тремя разными предметами; тела правок у всех трёх разные
- `backend/flows/channels.py:poll_one_channel` `b8b53cf9` ↔ `backend/flows/ingest.py:ingest_post` `6daf7233` — обход с отметкой и приём одного поста; между ними зов, а не копия
