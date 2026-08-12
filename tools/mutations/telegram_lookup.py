"""Поломки для походов в Telegram `backend/telegram_lookup.py`.

Набор отпочковался от `helpers` заходом Д этапа 4 вместе с самим модулем:
гонять поломки надо против проверок своего предмета, а они разъехались по
трём файлам.
"""

# (файл, что заменить, на что заменить) — по одной осмысленной поломке.
MUTATIONS = [
    # fetch_telegram_avatar: перепутан приоритет small/big file_id
    (
        "backend/telegram_lookup.py",
        'file_id = getattr(photo, "small_file_id", None) or getattr(photo, "big_file_id", None)',
        'file_id = getattr(photo, "big_file_id", None) or getattr(photo, "small_file_id", None)',
    ),
    # resolve_hr_telegram: удалённый аккаунт больше не отсеивается
    (
        "backend/telegram_lookup.py",
        'if getattr(user, "is_bot", False) or getattr(user, "is_deleted", False):',
        'if getattr(user, "is_bot", False):',
    ),
]
