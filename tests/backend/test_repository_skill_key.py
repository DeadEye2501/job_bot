"""Следствия приведения названия навыка к сравнимому виду.

Ключ нужен там, где название навыка приходит со стороны: в стеке места
работы из разобранного резюме. Он даёт «Postgres» из стека найти навык
«PostgreSQL» с таким написанием, а «Docker-Compose» — «docker compose».
"""

from backend.repository.profile import _normalize_skill_key


def test_a_skill_key_ignores_case_spacing_and_punctuation():
    """Ключ сравнения навыков не различает регистр, пробелы и разделители.

    Это даёт стеку вакансии «Postgres» найти навык «PostgreSQL» с таким
    написанием, а «Docker-Compose» — «docker compose».
    """
    assert _normalize_skill_key("  Docker-Compose ") == "docker compose"
    assert _normalize_skill_key("docker compose") == "docker compose"
    assert _normalize_skill_key("Docker_Compose") == "docker compose"
    assert _normalize_skill_key("Docker/Compose") == "docker compose"
    assert _normalize_skill_key("Docker.Compose") == "docker compose"
    assert _normalize_skill_key("PostgreSQL") == "postgresql"
