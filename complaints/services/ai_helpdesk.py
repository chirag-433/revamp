import json
import os
from urllib import error, request


class AIHelpdeskError(Exception):
    """Raised when the help-desk provider cannot return an answer."""


def ask_gemini(message):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise AIHelpdeskError("The AI help desk is not configured yet.")

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.1-flash-lite:generateContent"
    )
    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": (
                        "You are Casework Guide, a concise and empathetic help-desk "
                        "assistant for an institution grievance monitoring workspace. "
                        "Help users understand case tracking, importing CSV data, "
                        "statuses, SLAs, and next steps. Never invent case details, "
                        "promise an outcome, or request sensitive personal information. "
                        "If the question needs an officer or administrator, say so."
                    )
                }
            ]
        },
        "contents": [{"role": "user", "parts": [{"text": message}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500},
    }
    api_request = request.Request(
        f"{endpoint}?key={api_key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(api_request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AIHelpdeskError("The AI help desk is temporarily unavailable.") from exc

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise AIHelpdeskError("The AI help desk returned an unexpected response.") from exc
