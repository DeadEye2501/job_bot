"""Поверхность моста, доступная окну: две формы окна и мотор под ними.

Предметы окна разложены по файлам примесями. Подмешивающий у них один — канал
регистрирует ровно один объект «api», так что все предметы обязаны сойтись в
нём; исключение одно, `TelegramLoginSlots`: вход в Telegram нужен и основному
окну, и мастеру первого запуска. Всё остальное — разрезание класса на файлы, а
не абстракция под будущую замену, и второй реализации там не будет.

SECURITY — cleartext secrets through QWebChannel:
Несколько slot'ов сознательно отдают plaintext-секреты во фронт (это
single-user app, JS живёт в embedded WebView, не по сети). Перечень таких
слотов живёт рядом с ними самими — в докстроках примесей. Прежде чем
добавлять новый slot, отдающий секреты, подумайте: заслуживает ли поле
статус «можно вернуть как есть», или его лучше скрыть/подменить (eye-toggle
паттерн на UI). Audit-trail см. git blame по соответствующим slot'ам.
"""

from client.bridge.main_api import MainApi
from client.bridge.runner import AsyncRunner
from client.bridge.wizard import WizardApi


__all__ = ["AsyncRunner", "MainApi", "WizardApi"]
