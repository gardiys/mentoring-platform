import hashlib
import re
from collections import Counter
from pathlib import Path

DATA_SHA256 = "4835dd8b16495fae214aaa53e6abb27262cd211a954abc818b99ba3198b7b3ec"
HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$")
LINK_PATTERN = re.compile(r"^\s*-\s+\[(.+)]\((https?://.+)\)\s*$")
PLAIN_TOPIC_PATTERN = re.compile(r"^\s*-\s+(.+?)\s*$")


def test_go_roadmap_source_is_complete_and_parseable() -> None:
    path = Path(__file__).resolve().parent.parent / "migrations" / "data" / "go_backend_roadmap.md"
    raw_data = path.read_bytes()
    assert hashlib.sha256(raw_data).hexdigest() == DATA_SHA256

    sections: list[tuple[str, int]] = []
    descriptions: dict[str, list[str]] = {}
    plain_topics: list[str] = []
    current_title: str | None = None
    current_topics = 0
    linked_topics = 0

    for raw_line in raw_data.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = HEADING_PATTERN.fullmatch(line)
        if heading:
            if current_title is not None:
                sections.append((current_title, current_topics))
            current_title = heading.group(1).strip()
            current_topics = 0
            continue
        link = LINK_PATTERN.fullmatch(line)
        if link:
            assert current_title is not None
            assert link.group(1).strip()
            assert link.group(2).startswith(("https://", "http://"))
            current_topics += 1
            linked_topics += 1
            continue
        plain_topic = PLAIN_TOPIC_PATTERN.fullmatch(line)
        if plain_topic:
            assert current_title is not None
            title = plain_topic.group(1).strip()
            assert title
            plain_topics.append(title)
            current_topics += 1
            continue
        assert current_title is not None
        descriptions.setdefault(current_title, []).append(line)

    assert current_title is not None
    sections.append((current_title, current_topics))

    assert len(sections) == 23
    assert linked_topics == 176
    assert plain_topics == ["Грокаем алгоритмы"]
    assert [title for title, count in sections if count == 0] == [
        "Мок собеседование",
        "Мок собеседование",
        "Составление легенды",
    ]
    assert descriptions == {
        "Практика брокеры сообщений": [
            "Выберите 2 практики, выполните их по ТЗ и отправьте своему ментору на проверку"
        ],
        "Финальный “боевой” проект": [
            "Выбери 1 из проектов, выполни его по ТЗ и отправь своему ментору на проверку"
        ],
    }
    assert Counter(count for _, count in sections) == Counter(
        {
            0: 3,
            2: 2,
            3: 1,
            4: 1,
            5: 1,
            6: 2,
            7: 1,
            8: 2,
            9: 2,
            10: 2,
            12: 1,
            14: 3,
            16: 1,
            18: 1,
        }
    )
