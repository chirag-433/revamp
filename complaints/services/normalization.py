import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from django.conf import settings


@lru_cache(maxsize=1)
def _abbreviation_map():
    path = Path(settings.BASE_DIR) / "static" / "sample_data" / "institution_abbreviations.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {key.casefold(): value.casefold() for key, value in data.items()}


def normalize_institution_name(value):
    """Normalize common institution abbreviations using the editable demo map."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = value.split()
    abbreviations = _abbreviation_map()
    expanded = [abbreviations.get(token, token) for token in tokens]
    return " ".join(token for token in expanded if token not in {"of", "the"})

