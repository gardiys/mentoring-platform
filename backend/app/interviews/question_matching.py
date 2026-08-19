from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal
from uuid import UUID

QuestionMatchType = Literal["exact", "similar"]

LOCAL_MATCH_THRESHOLD = 0.35
EMBEDDING_MATCH_THRESHOLD = 0.72


@dataclass(frozen=True, slots=True)
class QuestionVariant:
    """One known wording of a card, including admin-confirmed aliases."""

    text: str
    embedding: tuple[float, ...] | None
    source: str


@dataclass(frozen=True, slots=True)
class QuestionCandidate:
    card_id: UUID
    asked_count: int
    variants: tuple[QuestionVariant, ...]


@dataclass(frozen=True, slots=True)
class RankedQuestionCandidate:
    card_id: UUID
    similarity: float
    match_type: QuestionMatchType
    matched_source: str
    matched_text: str


@dataclass(frozen=True, slots=True)
class _QuestionFingerprint:
    tokens: frozenset[str]
    technical_concepts: frozenset[str]
    intentions: frozenset[str]
    sequence: str


_WORD_BOUNDARY_START = r"(?<![0-9a-zа-я])"
_WORD_BOUNDARY_END = r"(?![0-9a-zа-я])"


def _alias_pattern(value: str) -> re.Pattern[str]:
    return re.compile(
        f"{_WORD_BOUNDARY_START}(?:{value}){_WORD_BOUNDARY_END}",
        flags=re.IGNORECASE,
    )


# These aliases cover frequent mixed Russian/English spellings and colloquial
# names. The matcher remains useful for unknown technologies through its token
# score; this list only strengthens cases where transliteration is insufficient.
_TECHNICAL_ALIASES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "rabbitmq",
        _alias_pattern(
            r"rabbit[\s-]*mq|rabbit|"
            r"рэббит(?:[\s-]*мкью)?|"
            r"кролик(?:а|и|у|ом|е|ов|ами)?"
        ),
    ),
    (
        "kafka",
        _alias_pattern(r"(?:apache[\s-]+)?kafka|кафк(?:а|и|е|у|ой|ою|ами)?"),
    ),
    ("postgresql", _alias_pattern(r"postgres(?:ql)?|постгрес(?:ql|ку|а|е|ом)?")),
    ("python", _alias_pattern(r"python|пайтон|питон(?:а|е|ом|у)?")),
    ("golang", _alias_pattern(r"golang|go[\s-]+lang|голанг")),
    ("redis", _alias_pattern(r"redis|редис(?:а|е|ом|у)?")),
    ("kubernetes", _alias_pattern(r"kubernetes|k8s|кубер(?:нетес)?(?:а|е|ом|у)?")),
    ("docker", _alias_pattern(r"docker|докер(?:а|е|ом|у)?")),
    ("nginx", _alias_pattern(r"nginx|энджинкс|нгинкс")),
    ("grpc", _alias_pattern(r"g[\s.-]*r[\s.-]*p[\s.-]*c|джиарписи")),
)

_INTENTION_ALIASES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "compare",
        _alias_pattern(
            r"разниц[0-9a-zа-я]*|"
            r"отлич[0-9a-zа-я]*|"
            r"сравн[0-9a-zа-я]*|"
            r"difference|different|differ|versus|vs"
        ),
    ),
    (
        "tradeoffs",
        _alias_pattern(
            r"плюс[0-9a-zа-я]*|"
            r"минус[0-9a-zа-я]*|"
            r"преимуществ[0-9a-zа-я]*|"
            r"недостатк[0-9a-zа-я]*|trade[\s-]*offs?|pros|cons"
        ),
    ),
)

_TOKEN_PATTERN = re.compile(r"[0-9a-zа-я](?:[0-9a-zа-я+#.]*)", flags=re.IGNORECASE)
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s*", flags=re.MULTILINE)
_SPACE_PATTERN = re.compile(r"\s+")

_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "can",
        "do",
        "does",
        "explain",
        "have",
        "how",
        "is",
        "me",
        "of",
        "or",
        "please",
        "tell",
        "the",
        "to",
        "what",
        "you",
        "а",
        "бы",
        "в",
        "вам",
        "ваш",
        "вы",
        "где",
        "дай",
        "дайте",
        "для",
        "есть",
        "зачем",
        "знаешь",
        "знаете",
        "и",
        "из",
        "или",
        "к",
        "как",
        "какая",
        "какие",
        "какой",
        "ли",
        "мне",
        "можешь",
        "можете",
        "мы",
        "на",
        "нам",
        "не",
        "но",
        "о",
        "об",
        "он",
        "она",
        "они",
        "от",
        "по",
        "пожалуйста",
        "пользовался",
        "пользовались",
        "про",
        "почему",
        "расскажи",
        "расскажите",
        "такое",
        "ты",
        "у",
        "чем",
        "что",
        "это",
        "я",
    }
)

_RUSSIAN_SUFFIXES = (
    "иями",
    "иях",
    "ами",
    "ями",
    "ого",
    "ему",
    "ому",
    "ыми",
    "ими",
    "ией",
    "иям",
    "ую",
    "юю",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ий",
    "ый",
    "ой",
    "ам",
    "ям",
    "ах",
    "ях",
    "ов",
    "ев",
    "ом",
    "ем",
    "ия",
    "ии",
    "ию",
    "ью",
    "а",
    "я",
    "ы",
    "и",
    "е",
    "у",
    "ю",
)


def normalize_question(value: str) -> str:
    """Normalize harmless formatting differences for exact comparison."""

    normalized = unicodedata.normalize("NFKC", value).replace("\x00", " ").strip()
    normalized = _MARKDOWN_HEADING.sub("", normalized)
    normalized = _SPACE_PATTERN.sub(" ", normalized).casefold().replace("ё", "е")
    return normalized.rstrip(" ?!.,;:")


def _stem_token(token: str) -> str:
    if token.isascii():
        return token
    for suffix in _RUSSIAN_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _fingerprint(value: str) -> _QuestionFingerprint:
    normalized = normalize_question(value)
    canonical = normalized
    technical_concepts: set[str] = set()
    intentions: set[str] = set()
    for concept, pattern in _TECHNICAL_ALIASES:
        if pattern.search(canonical):
            technical_concepts.add(concept)
            canonical = pattern.sub(f" {concept} ", canonical)
    for intention, pattern in _INTENTION_ALIASES:
        if pattern.search(canonical):
            intentions.add(intention)
            canonical = pattern.sub(f" {intention} ", canonical)

    ordered_tokens: list[str] = []
    for raw_token in _TOKEN_PATTERN.findall(canonical):
        token = raw_token.strip(".")
        if not token or token in _STOP_WORDS:
            continue
        token = _stem_token(token)
        if len(token) < 3 and token not in technical_concepts:
            continue
        ordered_tokens.append(token)
    return _QuestionFingerprint(
        tokens=frozenset(ordered_tokens),
        technical_concepts=frozenset(technical_concepts),
        intentions=frozenset(intentions),
        sequence=" ".join(ordered_tokens),
    )


def question_retrieval_terms(value: str) -> frozenset[str]:
    """Return stable terms suitable for bounded duplicate-candidate retrieval.

    Full question matching remains the responsibility of ``rank_question_candidates``.
    This smaller representation is only used to avoid comparing every card with every
    other card before the real matcher runs.
    """

    fingerprint = _fingerprint(value)
    return frozenset(
        (*fingerprint.tokens, *fingerprint.technical_concepts, *fingerprint.intentions)
    )


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _local_similarity(left: _QuestionFingerprint, right: _QuestionFingerprint) -> float:
    shared_tokens = left.tokens & right.tokens
    if not shared_tokens:
        return 0.0

    technical_union = left.technical_concepts | right.technical_concepts
    token_score = _jaccard(left.tokens, right.tokens)
    sequence_score = SequenceMatcher(None, left.sequence, right.sequence).ratio()
    common_intention = bool(left.intentions & right.intentions)

    if technical_union:
        score = (
            0.50 * _jaccard(left.technical_concepts, right.technical_concepts)
            + 0.35 * token_score
            + 0.15 * sequence_score
        )
    else:
        score = 0.75 * token_score + 0.25 * sequence_score

    # Jaccard alone heavily penalizes a short interview wording when the
    # canonical card expands the same subject into several explicit clauses.
    # Use containment as a retrieval-only boost so e.g. "какие индексы
    # знаешь" remains a moderation candidate for a detailed card about index
    # types.  The cap stays well below the automatic semantic-link threshold;
    # a human or the independent pairwise judge still decides equivalence.
    shorter_token_count = min(len(left.tokens), len(right.tokens))
    containment = len(shared_tokens) / shorter_token_count if shorter_token_count else 0.0
    retrieval_score = 0.45 * containment + 0.30 * token_score + 0.25 * sequence_score
    if len(shared_tokens) == 1:
        retrieval_score = min(retrieval_score + 0.15, 0.69)
    score = max(score, retrieval_score)
    if common_intention:
        score += 0.08

    shared_technical = left.technical_concepts & right.technical_concepts
    shared_non_technical = shared_tokens - shared_technical - left.intentions - right.intentions
    # One shared technology alone is not enough: "Kafka vs RabbitMQ" and
    # "Kafka delivery guarantees" are different cards despite sharing Kafka.
    if len(shared_technical) == 1 and not shared_non_technical and not common_intention:
        score = min(score, LOCAL_MATCH_THRESHOLD - 0.001)
    return min(score, 0.99)


def _cosine_similarity(left: Sequence[float] | None, right: Sequence[float] | None) -> float | None:
    if left is None or right is None or not left or len(left) != len(right):
        return None
    if not all(math.isfinite(value) for value in (*left, *right)):
        return None
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return None
    value = sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
    return max(0.0, min(1.0, value))


def rank_question_candidates(
    question_text: str,
    question_embedding: Sequence[float] | None,
    candidates: Iterable[QuestionCandidate],
    *,
    limit: int = 5,
) -> list[RankedQuestionCandidate]:
    """Rank possible duplicate cards without making an automatic merge decision."""

    if limit <= 0:
        return []
    normalized_question = normalize_question(question_text)
    question_fingerprint = _fingerprint(question_text)
    ranked_with_counts: list[tuple[RankedQuestionCandidate, int]] = []

    for candidate in candidates:
        best: RankedQuestionCandidate | None = None
        include_best = False
        for variant in candidate.variants:
            exact = (
                bool(normalized_question)
                and normalize_question(variant.text) == normalized_question
            )
            local_similarity = (
                1.0
                if exact
                else _local_similarity(question_fingerprint, _fingerprint(variant.text))
            )
            embedding_similarity = _cosine_similarity(question_embedding, variant.embedding)
            similarity = max(local_similarity, embedding_similarity or 0.0)
            included = (
                exact
                or local_similarity >= LOCAL_MATCH_THRESHOLD
                or (
                    embedding_similarity is not None
                    and embedding_similarity >= EMBEDDING_MATCH_THRESHOLD
                )
            )
            if not included:
                continue
            current = RankedQuestionCandidate(
                card_id=candidate.card_id,
                similarity=similarity,
                match_type="exact" if exact else "similar",
                matched_source=variant.source,
                matched_text=variant.text,
            )
            if (
                best is None
                or current.similarity > best.similarity
                or (
                    current.similarity == best.similarity
                    and current.match_type == "exact"
                    and best.match_type != "exact"
                )
            ):
                best = current
                include_best = True
        if best is not None and include_best:
            ranked_with_counts.append((best, max(candidate.asked_count, 0)))

    ranked_with_counts.sort(
        key=lambda item: (
            -item[0].similarity,
            -item[1],
            str(item[0].card_id),
        )
    )
    return [item[0] for item in ranked_with_counts[:limit]]
