import os

from sarvamai import SarvamAI


class AIHelpdeskError(Exception):
    """Raised when the help-desk provider cannot return an answer."""


SYSTEM_PROMPT = (
    "You are Disha, a concise and empathetic help-desk assistant for an "
    "institution grievance monitoring workspace. Help users understand case "
    "tracking, importing CSV data, statuses, SLAs, and next steps. Never invent "
    "case details, promise an outcome, or request sensitive personal information. "
    "If the question needs an officer or administrator, say so."
)


def ask_sarvam(message):
    api_key = os.getenv("SARVAM_API_KEY", "").strip()
    if not api_key:
        raise AIHelpdeskError("The AI help desk is not configured yet.")

    try:
        client = SarvamAI(api_subscription_key=api_key)
        response = client.chat.completions(
            model="sarvam-105b-conversations",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            max_tokens=500,
        )
        text = (response.choices[0].message.content or "").strip()
    except AIHelpdeskError:
        raise
    except Exception as exc:
        raise AIHelpdeskError("The AI help desk is temporarily unavailable.") from exc

    if not text:
        raise AIHelpdeskError("The AI help desk returned an unexpected response.")
    return text
