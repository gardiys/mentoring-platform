import hashlib
import re
from collections import Counter
from pathlib import Path

DATA_SHA256 = "2ebac91e39dd97c5f64f4df2d97e58c9b24d23eacae819d7d4887c5b79d60a45"
HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$")
LINK_PATTERN = re.compile(r"^\s*-\s+\[(.+)]\((https?://.+)\)\s*$")


def test_python_roadmap_source_is_complete_and_parseable() -> None:
    path = (
        Path(__file__).resolve().parent.parent / "migrations" / "data" / "python_backend_roadmap.md"
    )
    raw_data = path.read_bytes()
    assert hashlib.sha256(raw_data).hexdigest() == DATA_SHA256

    sections: list[tuple[str, int]] = []
    subgroup_labels: list[str] = []
    current_title: str | None = None
    current_links = 0
    linked_topics = 0

    for raw_line in raw_data.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = HEADING_PATTERN.fullmatch(line)
        if heading:
            if current_title is not None:
                sections.append((current_title, current_links))
            current_title = heading.group(1).strip()
            current_links = 0
            continue
        link = LINK_PATTERN.fullmatch(line)
        if link:
            assert current_title is not None
            assert link.group(1).strip()
            assert link.group(2).startswith(("https://", "http://"))
            current_links += 1
            linked_topics += 1
            continue
        assert current_title == "Продвинутый Python"
        subgroup_labels.append(line)

    assert current_title is not None
    sections.append((current_title, current_links))

    assert len(sections) == 22
    assert linked_topics == 253
    assert Counter(link_count for _, link_count in sections) == Counter(
        {
            0: 2,
            1: 2,
            3: 2,
            4: 1,
            5: 1,
            6: 2,
            7: 1,
            8: 1,
            9: 1,
            12: 2,
            16: 2,
            17: 1,
            18: 1,
            25: 1,
            39: 1,
            45: 1,
        }
    )
    assert subgroup_labels == [
        "ООП",
        "Генераторы и Итераторы",
        "Асинхронность",
        "Конкурентность, Потоки и GIL",
        "Сеть, API и микросервисы",
        "Файловая система и Управление памятью",
    ]
    assert [title for title, count in sections if count == 0] == [
        "Запишись на мок собеседование к своему тимлиду",
        "Запишись на мок собеседование к своему тимлиду",
    ]
