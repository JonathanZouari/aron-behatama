"""מעברי סטטוס מותרים לפנייה ולהצעה. נאכף בשרת בכל פעולה."""
from __future__ import annotations

INQUIRY_STATUSES = ("collecting_details", "awaiting_carpenter", "quote_available",
                    "change_requested", "accepted", "closed")
QUOTE_STATUSES = ("draft", "published", "accepted", "superseded", "expired", "cancelled")

INQUIRY_TRANSITIONS: dict[str, set[str]] = {
    "collecting_details": {"awaiting_carpenter", "closed"},
    "awaiting_carpenter": {"quote_available", "closed"},
    "quote_available": {"change_requested", "accepted", "awaiting_carpenter", "closed"},
    "change_requested": {"quote_available", "awaiting_carpenter", "closed"},
    "accepted": {"closed", "awaiting_carpenter"},  # שינוי נוסף מחייב תהליך הצעה חדש
    "closed": set(),
}

QUOTE_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"published", "cancelled"},
    "published": {"accepted", "superseded", "expired", "cancelled"},
    "accepted": set(),  # הצעה שאושרה נשמרת ללא שינוי
    "superseded": set(),
    "expired": set(),
    "cancelled": set(),
}

STATUS_LABELS_HE = {
    "collecting_details": "איסוף פרטים",
    "awaiting_carpenter": "ממתינה לנגר",
    "quote_available": "הצעה זמינה",
    "change_requested": "בקשת שינוי",
    "accepted": "אושרה",
    "closed": "סגורה",
    "draft": "טיוטה",
    "published": "פורסמה",
    "superseded": "הוחלפה",
    "expired": "פג תוקף",
    "cancelled": "בוטלה",
}


class InvalidTransition(Exception):
    pass


def assert_inquiry_transition(current: str, new: str) -> None:
    if new not in INQUIRY_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"לא ניתן להעביר פנייה מ-{STATUS_LABELS_HE.get(current, current)} "
                                f"ל-{STATUS_LABELS_HE.get(new, new)}")


def assert_quote_transition(current: str, new: str) -> None:
    if new not in QUOTE_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"לא ניתן להעביר הצעה מ-{STATUS_LABELS_HE.get(current, current)} "
                                f"ל-{STATUS_LABELS_HE.get(new, new)}")
