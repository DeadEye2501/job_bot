"""Следствия раздачи по http: что окно получает по своему адресу.

Предмет — дорога от файла на диске до страницы в окне. Сборкой фронта здесь не
занимаются: `dist` кладёт Vite, а этот слой только отдаёт положенное.

Отдаётся всё по http, а не файлами с диска, потому что модули и запросы
страницы требуют настоящего происхождения: с `file://` браузер отказывает им
сам, и разбираться в отказе пришлось бы уже на живом экране.

Каталогов раздача знает два — собранный фронт и вложения переписки, — и
различает их по началу пути. Заслон на выход из каталога у обоих один.
"""

from client.serving import MEDIA_PREFIX, served_files


def _app(front, media=None):
    """Раздача под тест: каталог вложений отдельный, по умолчанию пустой."""
    return served_files(front, media if media is not None else front / "медиа")


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

    status, headers, body = _get(_app(tmp_path), "/")

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

    status, headers, body = _get(_app(tmp_path), "/assets/main.js")

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

    status, _headers, body = _get(_app(tmp_path / "dist"), "a/../../секрет.txt")

    assert status.startswith("404")
    assert "не отдавать" not in body.decode("utf-8", "replace")


def test_a_missing_file_is_named_missing(tmp_path):
    """Ненайденного не выдают за пустое: страница должна узнать, что его нет.

    Пустой ответ с кодом успеха браузер разбирает как испорченный файл, и на
    экране это выглядит поломкой приложения, а не недостачей сборки.
    """
    status, _headers, _body = _get(_app(tmp_path), "/чего-нет.js")

    assert status.startswith("404")


def test_an_attachment_comes_back_by_its_own_address(tmp_path):
    """Вложение переписки приезжает той же раздачей, что и страница.

    Страница отдана по http, и снимок, вставленный в неё адресом `file://`,
    Chromium не загружает вовсе — правила происхождения запрещают такой
    подресурс, а отказ виден только в консоли: в ленте на его месте пусто.
    """
    media = tmp_path / "медиа"
    (media / "1").mkdir(parents=True)
    (media / "1" / "42.jpg").write_bytes(b"\xff\xd8" + "снимок".encode("utf-8"))

    status, headers, body = _get(_app(tmp_path, media), f"{MEDIA_PREFIX}1/42.jpg")

    assert status.startswith("200")
    assert body.endswith("снимок".encode("utf-8"))
    assert headers["Content-Type"].startswith("image/")


def test_a_media_path_leading_out_of_the_folder_is_refused(tmp_path):
    """Из каталога вложений тоже не выпускают.

    Заслон здесь тот же, а нужен он не меньше: адрес вложения приезжает от
    окна обратно, и каталог медиа лежит рядом с базой и ключами.
    """
    media = tmp_path / "медиа"
    (media / "1").mkdir(parents=True)
    (tmp_path / "секрет.txt").write_text("не отдавать", encoding="utf-8")

    status, _headers, body = _get(
        _app(tmp_path, media), f"{MEDIA_PREFIX}1/../../секрет.txt"
    )

    assert status.startswith("404")
    assert "не отдавать" not in body.decode("utf-8", "replace")


def test_a_missing_attachment_is_named_missing(tmp_path):
    """Ненайденного вложения тоже не выдают за пустое.

    Скачивает бот не всё: строка о письме остаётся, а файла под ней нет.
    """
    status, _headers, _body = _get(_app(tmp_path), f"{MEDIA_PREFIX}1/42.jpg")

    assert status.startswith("404")
