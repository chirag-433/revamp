import re
import unicodedata


def normalize_institution_name(value):
    """Return a conservative normalized form for exact name lookup."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

