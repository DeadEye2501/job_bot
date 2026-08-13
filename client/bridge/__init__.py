"""Поверхность моста, доступная окну: две формы окна и мотор под ними.

SECURITY — cleartext secrets through QWebChannel:
Несколько slot'ов сознательно отдают plaintext-секреты во фронт (это
single-user app, JS живёт в embedded WebView, не по сети):
- ``initial_state`` / ``request_system_settings`` — chat/embed api_key,
  Telegram api_id+api_hash, расшифрованный CV-path.
- ``request_profile`` — PII профиля (email, phone, telegram_username,
  github_url, location, education) + абсолютный путь к CV.
Прежде чем добавлять новые slot'ы, отдающие секреты, подумайте:
заслуживает ли поле статус «можно вернуть как есть», или его лучше
скрыть/подменить (eye-toggle паттерн на UI). Audit-trail см. git blame
по соответствующим slot'ам.
"""

from client.bridge.main_api import MainApi, WizardApi
from client.bridge.runner import AsyncRunner


__all__ = ["AsyncRunner", "MainApi", "WizardApi"]
