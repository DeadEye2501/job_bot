"""Поломки для буфера логов, которым живёт экран «Логи».

Файл лёг в дерево с юниксовыми переводами строк — в отличие от соседей по
бэкенду. Многострочные поломки пишутся через `LF`: поиск не той парой не
находит ничего и молчит об этом.
"""

LF = "\n"

MUTATIONS = [
    # emit: об упавшем подписчике снова молчат
    (
        "backend/log_buffer.py",
        "                self.handleError(record)",
        "                pass",
    ),
    # emit: упавший подписчик снова роняет логирование
    (
        "backend/log_buffer.py",
        "            except Exception:" + LF
        + "                # Уронить логирование подписчик не должен",
        "            except ValueError:" + LF
        + "                # Уронить логирование подписчик не должен",
    ),
    # filter: о неразбираемой записи снова молчат
    (
        "backend/log_buffer.py",
        '                report_own_failure("запись не собирается", record)',
        "                pass",
    ),
    # emit: о неразбираемой записи снова молчат
    (
        "backend/log_buffer.py",
        '            report_own_failure("сообщение записи не собирается", record)',
        "            pass",
    ),
    # emit: о несобравшейся трассировке снова молчат
    (
        "backend/log_buffer.py",
        '                report_own_failure("трассировка записи не собирается", record)',
        "                pass",
    ),
    # handleError: беда обработчика снова уходит в поток ошибок, а не в файл
    (
        "backend/log_buffer.py",
        '        report_own_failure("обработчик буфера подавился записью", record)',
        "        super().handleError(record)",
    ),
    # filter: отметка снята, и об одной записи сообщает каждый обработчик
    (
        "backend/log_buffer.py",
        '            if not getattr(record, "own_failure_reported", False):' + LF
        + "                record.own_failure_reported = True" + LF,
        "            if True:" + LF,
    ),
    # report_own_failure: шаблон записи уезжает в файл без вымарывания
    (
        "backend/log_buffer.py",
        '            f"{_redact(repr(record.msg))}',
        '            f"{repr(record.msg)}',
    ),
    # report_own_failure: трассировка перестаёт дописываться к строке
    (
        "backend/log_buffer.py",
        "            out.write(line + traceback.format_exc())",
        "            out.write(line)",
    ),
    # report_own_failure: недоступный файл снова означает молчание
    (
        "backend/log_buffer.py",
        "                traceback.print_exc()" + LF,
        "                pass" + LF,
    ),
]
