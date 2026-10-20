"""WinForms, системные диалоги и права фокуса Windows."""

import ctypes
import logging

logger = logging.getLogger(__name__)


def show_trouble(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, "Job Bot", 0x10)


def unlock_frame(form, size: tuple[int, int]) -> None:
    """Разрешить окну тянуться и поднять ему наименьший размер.

    Рамку, наименьший размер и растягиваемость pywebview отдаёт системе один
    раз, когда создаёт форму, и своего способа передумать у него нет — отсюда и
    правка самой формы WinForms напрямую.

    Правится она из потока моста, а форма принимает правку только своим: у
    WinForms доступ к живому окну не из его потока кончается броском. Отсюда
    `Invoke` — тот же способ, которым ходит к форме сам pywebview.

    Множитель `_scale` — доля экрана: размеры формы система считает в точках
    самого экрана, а наши названы в тех, в которых нарисована разметка.
    """
    from webview.platforms.winforms import Func, Size, Type, WinForms

    def apply() -> None:
        form.FormBorderStyle = WinForms.FormBorderStyle.Sizable
        form.MaximizeBox = True
        form.MinimumSize = Size(
            int(size[0] * form._scale), int(size[1] * form._scale)
        )

    if form.InvokeRequired:
        form.Invoke(Func[Type](apply))
    else:
        apply()


def own_taskbar_icon() -> None:
    """Назвать себя системе до того, как поднимется окно.

    Windows складывает окна в панели задач по этому имени. Без него приложение
    садится под именем интерпретатора и делит значок с любым другим питоном.
    """
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DeadEye.JobBot.UI")
    except (AttributeError, OSError):
        logger.warning("имя для панели задач не принято", exc_info=True)


def allow_foreground() -> None:
    """Отдать право на передний план — иначе окно первой копии только мигнёт.

    Только Windows: на прочих системах права переднего плана так не устроены,
    и отдавать нечего.
    """
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(-1)
    except (AttributeError, OSError):
        logger.exception("raise_window: не отдать право на передний план")
