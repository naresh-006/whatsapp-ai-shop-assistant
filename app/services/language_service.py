"""Tamil, English, Tanglish and Mixed-Language Normalization Service (Phase 16).

Handles the family shop's spoken vocabulary:
- Tamil number words (oru, rendu, moonu, naalu, anju...)
- Tamil conversational suffixes (-ku, -vuku, -oda)
- Conversational verbs (kudunga, venum, podunga, edukka)
- Packaging slang (packet-u, piece-u, kattu, saram)
"""

import re
import logging

logger = logging.getLogger(__name__)

# Tamil & Tanglish number words to canonical digits
TAMIL_NUMBERS: dict[str, str] = {
    "oru": "1",
    "onnu": "1",
    "rendu": "2",
    "irandu": "2",
    "moonu": "3",
    "moondru": "3",
    "naalu": "4",
    "naangu": "4",
    "anju": "5",
    "aindhu": "5",
    "aaru": "6",
    "elu": "7",
    "yezhu": "7",
    "ettu": "8",
    "onbathu": "9",
    "pathu": "10",
}

# Packaging and unit normalization
TAMIL_UNITS: dict[str, str] = {
    "kattu": "bundle",
    "kattuga": "bundle",
    "kattugal": "bundle",
    "saram": "saram",
    "sarangal": "saram",
    "packetu": "packet",
    "packeta": "packet",
    "packet-u": "packet",
    "packet-a": "packet",
    "pieceu": "piece",
    "piece-u": "piece",
    "piece-a": "piece",
    "boxu": "box",
    "box-u": "box",
}

# Tamil conversational filler verbs to discard
TAMIL_STOP_VERBS = [
    r"\bkudunga\b",
    r"\bkodu\b",
    r"\bthanga\b",
    r"\bvenum\b",
    r"\bvendum\b",
    r"\bpodunga\b",
    r"\bpodu\b",
    r"\beduthukonga\b",
    r"\bedu\b",
    r"\bkeetaru\b",
    r"\bvaanginaaru\b",
]


def normalize_tamil_tanglish_text(text: str) -> str:
    """
    Normalizes mixed Tamil/English/Tanglish shop transcripts.
    Example:
    'Satya-ku three Filter kudunga, rendu Scissor podunga'
    -> 'Satya 3 Filter, 2 Scissor'
    """
    normalized = text.strip()

    # 1. Strip customer dative case markers like "Satya-ku", "Kumar-uku", "Ravi-kku", "Ravi-oda"
    # Matches: [Name]-ku, [Name]-kku, [Name]-uku, [Name] ku
    normalized = re.sub(r"\b([a-zA-Z]+)(?:[-']?(?:kku|ku|uku|oda))\b", r"\1", normalized, flags=re.IGNORECASE)

    # 2. Strip Tamil action / filler verbs
    for pattern in TAMIL_STOP_VERBS:
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)

    # 3. Replace Tamil numbers
    words = normalized.split()
    converted_words = []
    for word in words:
        clean_word = word.lower().strip(" ,.-")
        if clean_word in TAMIL_NUMBERS:
            converted_words.append(TAMIL_NUMBERS[clean_word])
        elif clean_word in TAMIL_UNITS:
            converted_words.append(TAMIL_UNITS[clean_word])
        else:
            converted_words.append(word)

    result = " ".join(converted_words)
    # Clean up double spaces or dangling commas
    result = re.sub(r"\s+", " ", result).strip(" ,")
    return result
