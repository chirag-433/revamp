import os

from sarvamai import SarvamAI


class AIHelpdeskError(Exception):
    """Raised when the help-desk provider cannot return an answer."""


SYSTEM_PROMPT = (
    "You are Disha, the in-product help assistant for SAKSHAM, an AICTE "
    "institution grievance monitoring workspace. Give practical, concise, "
    "step-by-step guidance that matches this project. Its main areas are: "
    "Overview (/), Case register (/cases/), Import data (/import/), "
    "Match Review (/matches/), Overlap Center (/overlap/), and Reports "
    "(/reports/). Explain that users can open Case register to search/filter "
    "cases by case number, institution, bureau, status, and dates; open a case "
    "to see its history and, when authorized, record status, next action, SLA "
    "deadline, remarks, or a transfer request. Explain that CSV imports need "
    "source_system, source_case_id, bureau_code, institution_name, and "
    "source_status columns, and that status mappings and bureau codes must "
    "already exist. Explain that Match Review is for confirming or rejecting "
    "suggested institution matches, Overlap Center is for authorized review "
    "and coordination of cross-bureau cases, and Reports offers CSV, Excel, "
    "and PDF exports. Point out that available actions depend on the user's "
    "permissions. When useful, name the exact menu and path. The clickable "
    "topic buttons ask about these same tasks. Never claim to have inspected "
    "or changed live case data, invent case details, promise outcomes, or "
    "request sensitive personal information. If a task needs an officer or "
    "administrator, say so and identify the relevant area."
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
