# Этап 5. Длинные и многодоводные функции

Правило 5 манифеста: функция — 40 строк, 3 уровня вложенности, 4 довода. Больше —
разнимать. Замер 11 августа 2026 по `backend/`, `adapters/`, `main.py`:
**71 функция длиннее сорока строк** и **32 функции с более чем четырьмя
доводами**, худшая — семнадцать.

Старая роадмапа называла 128 и 29: первое число измерено до разбиения больших
файлов и с тех пор упало почти вдвое.

**Берётся после этапов 2 и 4:** сведение повторов и переезд запросов в
репозиторий сами укорачивают часть тел, и мерить их до этого бессмысленно.

**Признак закрытия:** функций длиннее сорока строк не осталось; у каждой
многодоводной либо настоящая свёртка, либо запись «довод остаётся доводом» с
объяснением.

## Соглашение по доводам — принято человеком

**Свёртку заводим только там, где группа значений настоящая** — как `ChannelPost`
(`backend/payloads.py`), где четыре довода были об одном предмете. Где группы нет,
довод остаётся доводом, а нарушение записывается.

По этому правилу `Bot.send` свёртке **не подлежит**: шесть его доводов — шесть
разных живых вещей. Он чинится разниманием тела.

## Как это брать: заходами по модулю, а не по функции

Разнимание — единственный этап, где дробить **по одной** бывает правильно: у
двухсотстрочной функции свой дифф и свой риск. Но у мелочи (41–59 строк) это
чистая переплата за обвязку.

- [ ] **Замер заново** — числа ниже сняты 11 августа, этапы 2 и 4 часть тел
      укоротят; список пересчитывается перед первым заходом, и по нему правятся
      галочки ниже
- [ ] **`repository/vacancies_list.list_vacancies`** — 213 строк, 17 доводов
- [ ] **`repository/companies_matching.find_or_create_company`** — 199
- [ ] **`repository/stats_pipeline.get_stats_channels_pipeline`** — 189
- [ ] **`bot/send.send`** — 180
- [ ] **`flows/dm.process_dm`** — 177
- [ ] **`flows/parse.parse_and_update_vacancy`** — 165
- [ ] **`flows/dm_backfill.backfill_hr_dm_history`** — 150, 9 доводов
- [ ] **100–149 строк, девять штук** — по двое-трое, группируя по модулю
- [ ] **60–99 строк, двадцать две штуки** — заходом на модуль, а не на функцию
- [ ] **41–59 строк, тридцать три штуки** — тем же порядком, пачками по модулю

Многодоводные чинятся тем же заходом, что и длина: у восьми из десяти худших
это одна и та же функция.

**Замер повторяется перед этапом.** Числа выше сняты 11 августа; этапы 2 и 4
укоротят часть тел, и брать в работу надо свежий список, а не этот.

## Порядок: сверху вниз по размеру

### Свыше 150 строк — семь штук, каждая своим заходом

| Функция | Строк | Доводов |
|---|---|---|
| `repository/vacancies_list.py list_vacancies` | 213 | 17 |
| `repository/companies_matching.py find_or_create_company` | 199 | 5 |
| `repository/stats_pipeline.py get_stats_channels_pipeline` | 189 | — |
| `bot/send.py send` | 180 | 6 |
| `flows/dm.py process_dm` | 177 | 6 |
| `flows/parse.py parse_and_update_vacancy` | 165 | 5 |
| `flows/dm_backfill.py backfill_hr_dm_history` | 150 | 9 |

`list_vacancies` — худшая по обоим измерениям разом, и семнадцать доводов у неё
**группа настоящая**: это отбор списка вакансий, то есть кандидат на свёртку, а
не на разнимание.

### 100–149 строк — девять штук

`flows/apply.py send_application` 148 · `llm/cover_letter.py
generate_cover_letter` 138 · `bot/loop.py run` 137 · `bot/client.py __init__` 135
· `repository/hr_list.py list_hr_with_counts` 128 · `llm/fit.py
validate_vacancy_fit` 113 · `repository/stats_summary.py get_stats_hr_responses`
108 · `bot/updates.py on_dm_delete` 102 · `repository/profile.py save_parsed_cv`
101.

`bot/client.py __init__` на 135 строк и `flows/pipeline.py __init__` на 97 — оба
конструктора; там разнимается не логика, а сборка, и это отдельный разговор.

### 60–99 строк — двадцать две штуки

`flows/pipeline.py __init__` 97 · `repository/vacancies_life.py
mark_ghosted_vacancies` 96 · `flows/rerun.py rerun_pipeline_for_vacancy` 88 ·
`flows/parse.py _persist_parse_outcome` 85 · `flows/dm_classify.py
classify_and_apply_for_hr` 84 · `repository/stats_summary.py get_stats_kpi` 81 ·
`repository/companies_matching.py _create_company_row` 75 ·
`repository/blacklist.py create_blacklist` 72 · `llm/company.py
dedupe_company_with_llm` 72 · `repository/hr_card.py merge_hr` 71 ·
`llm/hr_reply.py classify_hr_reply` 70 · `llm/vacancy.py parse_vacancy` 69 ·
`repository/channels.py get_channel_detail` 68 · `repository/profile.py
save_experience` 67, `build_profile_block` 67 · `repository/stats_summary.py
get_stats_skills` 66 · `flows/dm_classify.py cancel_pending_dm_classifications`
63 · `flows/ingest.py ingest_post` 63 · `llm/vacancy.py _parse_vacancy_json` 63 ·
`llm/factcheck.py factcheck_cover_letter` 62 · `repository/vacancies_list.py
list_vacancy_filter_options` 62 · `repository/profile.py save_skills` 61.

### 41–59 строк — остальные тридцать три

Мелочь по одной строке на слайс не берут: они собираются пачками по модулю —
`flows/channels.py` (три), `repository/vacancies_card.py` (две),
`repository/companies_card.py` (две), `telegram_login.py` (две) и так далее.

## Многодоводные сверх названных

Худшие после `list_vacancies:17`: `flows/dm_backfill.py backfill_hr_dm_history`
и `catch_up_missed_dms` (9 и 8), `flows/pipeline.py __init__` (9),
`repository/messages.py save_incoming_message` (9).

`save_incoming_message` — самый вероятный кандидат на настоящую свёртку: девять
доводов там об одном предмете, входящем сообщении.

## Признак, стоящий рядом

**`E402` — импорт после кода:** `adapters/telegram.py:49`. Директивой не чинится;
почти всегда означает, что модуль держит и общее, и поверхность сразу. Смотреть
вместе с разниманием, а не отдельно.

## Как мерить

Ruff считает не то же самое, и его числа ниже: `C901` 16, `PLR0912` 10,
`PLR0913` 9 (порог у него пять доводов, а не четыре), `PLR0915` 6. Мерять по
манифесту — длиной тела и числом доводов; ruff держит только прирост и
проваливает пятый довод.
