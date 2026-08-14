"""Следствия раздачи собранного фронта: что окно получает по своему адресу.

Предмет — дорога от файла на диске до страницы в окне. Сборкой фронта здесь не
занимаются: `dist` кладёт Vite, а этот слой только отдаёт положенное.

Отдаётся всё по http, а не файлами с диска, потому что модули и запросы
страницы требуют настоящего происхождения: с `file://` браузер отказывает им
сам, и разбираться в отказе пришлось бы уже на живом экране.
"""

from client.serving import built_front


def _get(app, path: str) -> tuple[str, dict, bytes]:
    """Один запрос к WSGI-приложению: код, заголовки, тело."""
    caught: dict = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        caught["status"] = status
        caught["headers"] = dict(headers)

    body = b"".join(app({"PATH_INFO": path, "REQUEST_METHOD": "GET"}, start_response))
    return caught["status"], caught["headers"], body


def test_the_root_gives_the_page_itself(tmp_path):
    """Корень отдаёт саму страницу, а не перечень файлов.

    Окно открывается по корню и ничего другого не просит. Отдай мы список
    файлов, человек увидел бы каталог вместо приложения.
    """
    (tmp_path / "index.html").write_text("<html>окно</html>", encoding="utf-8")

    status, headers, body = _get(built_front(tmp_path), "/")

    assert status.startswith("200")
    assert "окно" in body.decode("utf-8")
    assert headers["Content-Type"].startswith("text/html")


def test_a_built_file_comes_back_with_its_own_type(tmp_path):
    """Собранный модуль приезжает с типом, по которому его исполнят.

    Браузер отказывается исполнять модуль, приехавший не тем типом, и отказ
    этот виден только в консоли страницы — экран при этом просто пуст.
    """
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "main.js").write_text("export const a = 1;", encoding="utf-8")

    status, headers, body = _get(built_front(tmp_path), "/assets/main.js")

    assert status.startswith("200")
    assert b"export" in body
    assert "javascript" in headers["Content-Type"]


def test_a_path_leading_out_of_the_folder_is_refused(tmp_path):
    """Путь, ведущий выше каталога сборки, наружу не отдают.

    Раздача слушает на localhost, и постучаться в неё может не только наше
    окно. Выпусти она путь с «..», отдать можно было бы что угодно с диска —
    включая файл базы и ключи.

    Путь берётся без ведущей косой нарочно: с ней приведение схлопывает «..» об
    корень, и запрос остаётся внутри каталога — то есть проверял бы не заслон,
    а отсутствие файла. Файл при этом настоящий и по этому пути лежит: не будь
    заслона, он бы и приехал.
    """
    (tmp_path / "dist").mkdir()
    (tmp_path / "секрет.txt").write_text("не отдавать", encoding="utf-8")

    status, _headers, body = _get(
        built_front(tmp_path / "dist"), "a/../../секрет.txt"
    )

    assert status.startswith("404")
    assert "не отдавать" not in body.decode("utf-8", "replace")


def test_a_missing_file_is_named_missing(tmp_path):
    """Ненайденного не выдают за пустое: страница должна узнать, что его нет.

    Пустой ответ с кодом успеха браузер разбирает как испорченный файл, и на
    экране это выглядит поломкой приложения, а не недостачей сборки.
    """
    status, _headers, _body = _get(built_front(tmp_path), "/чего-нет.js")

    assert status.startswith("404")
