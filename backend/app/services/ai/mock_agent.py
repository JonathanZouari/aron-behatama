"""סוכן AI מדומה ודטרמיניסטי למצב דמו ולבדיקות.

מחלץ מידות, דלתות, מגירות, מדפים, תאים, חומרים וגימורים בעזרת regex פשוט,
ומחזיר אותו פלט מובנה כמו הסוכן האמיתי. כל תשובה מסומנת כסימולציה.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from app.schemas.agent_output import AgentOutput
from app.schemas.wardrobe_spec import FIELD_LABELS_HE, SpecPatch, WardrobeSpec

from .units import is_ambiguous_dimension_phrase, to_cm

HEBREW_NUMBERS = {"אחת": 1, "אחד": 1, "שתי": 2, "שתיים": 2, "שני": 2, "שניים": 2, "שלוש": 3, "שלושה": 3,
                  "ארבע": 4, "ארבעה": 4, "חמש": 5, "חמישה": 5, "שש": 6, "שישה": 6, "שבע": 7, "שבעה": 7,
                  "שמונה": 8, "תשע": 9, "תשעה": 9, "עשר": 10, "עשרה": 10}
_NUM_OR_WORD = r"(\d+|" + "|".join(HEBREW_NUMBERS) + r")"
_UNIT = r"\s*(מ\"מ|מ״מ|ס\"מ|ס״מ|סמ|מטר|מטרים|מ'|מ׳|cm|mm|m)?"

MATERIAL_KEYWORDS = {
    "body_material_id": [("סנדוויץ", "SANDWICH17"), ("מלמין", "MELAMINE18"), ("mdf", "MDF18"), ("אם די אף", "MDF18")],
    "front_material_id": [("פורניר", "OAK_VENEER"), ("mdf מצופה", "MDF_COATED"), ("חזית מלמין", "MELAMINE_FRONT"),
                          ("חזיתות מלמין", "MELAMINE_FRONT")],
    "finish_id": [("אלון בהיר", "FIN_OAK_LIGHT"), ("אלון", "FIN_OAK_LIGHT"), ("אגוז", "FIN_WALNUT"),
                  ("לבן מט", "FIN_WHITE_MATTE"), ("לבן", "FIN_WHITE_MATTE"), ("לכה", "FIN_LACQUER")],
}
MANUAL_KEYWORDS = ["הזזה", "פינתי", "פינה", "מעוגל", "מעוגלת", "מגירות חיצוניות", "מגירה חיצונית"]

SIMULATED_PREFIX = "[סימולציה] "


def _num(token: str) -> int:
    return int(token) if token.isdigit() else HEBREW_NUMBERS[token]


def _count(text: str, nouns: str) -> Optional[int]:
    m = re.search(_NUM_OR_WORD + r"\s+(?:" + nouns + r")", text)
    if m:
        return _num(m.group(1))
    if re.search(r"(בלי|ללא|אין)\s+(?:" + nouns + r")", text):
        return 0
    return None


def _dimension(text: str, names: str) -> Optional[int]:
    m = re.search(r"(?:" + names + r")\s*(?:של|:)?\s*(\d+(?:[.,]\d+)?)" + _UNIT, text)
    if not m:
        return None
    return to_cm(Decimal(m.group(1).replace(",", ".")), m.group(2))


def _triple(text: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """'240 על 260 על 60' או '240x260x60' → (רוחב, גובה, עומק)."""
    m = re.search(r"(\d+(?:[.,]\d+)?)" + _UNIT + r"\s*(?:על|x|X|×)\s*(\d+(?:[.,]\d+)?)" + _UNIT
                  + r"(?:\s*(?:על|x|X|×)\s*(\d+(?:[.,]\d+)?)" + _UNIT + r")?", text)
    if not m:
        return None, None, None
    unit = m.group(2) or m.group(4) or m.group(6)
    vals = [to_cm(Decimal(g.replace(",", ".")), unit) for g in (m.group(1), m.group(3), m.group(5)) if g]
    while len(vals) < 3:
        vals.append(None)
    return vals[0], vals[1], vals[2]


def extract_patch(text: str, current: WardrobeSpec) -> tuple[SpecPatch, list[str]]:
    """מחלץ שדות מהודעת הלקוח. מחזיר (patch, סיבות לבדיקה ידנית)."""
    lowered = text.lower()
    data: dict = {}
    for field, names in (("width_cm", "רוחב|ברוחב"), ("height_cm", "גובה|בגובה"), ("depth_cm", "עומק|בעומק")):
        value = _dimension(lowered, names)
        if value is not None:
            data[field] = value
    if not {"width_cm", "height_cm"} & data.keys() and not is_ambiguous_dimension_phrase(lowered):
        w, h, d = _triple(lowered)
        if w and h:
            data.update({"width_cm": w, "height_cm": h})
            if d:
                data["depth_cm"] = d
    for field, nouns in (("doors", "דלתות|דלת"), ("internal_drawers", "מגירות|מגירה"),
                         ("shelves", "מדפים|מדף"), ("compartments", "תאים|תא")):
        value = _count(lowered, nouns)
        if value is not None:
            data[field] = value
    for field, options in MATERIAL_KEYWORDS.items():
        for keyword, code in options:
            if keyword in lowered:
                data[field] = code
                break
    if "חזית" in lowered and "mdf" in lowered and "front_material_id" not in data:
        data["front_material_id"] = "MDF_COATED"
    if "טריקה שקטה" in lowered:
        data["soft_close"] = not re.search(r"(בלי|ללא)\s+טריקה", lowered)
    if "הובלה" in lowered:
        data["delivery"] = not re.search(r"(בלי|ללא)\s+הובלה", lowered)
    if "התקנה" in lowered:
        data["installation"] = not re.search(r"(בלי|ללא)\s+התקנה", lowered)
    city = re.search(r"(?:ב|ל|עיר\s*:?\s*)(תל אביב|רמת גן|חיפה|ירושלים|באר שבע|נתניה|הרצליה|רעננה|אשדוד|חולון|פתח תקווה)", text)
    if city:
        data["city"] = city.group(1)
    reasons = [f"בקשה שאינה נתמכת אוטומטית: {kw}" for kw in MANUAL_KEYWORDS if kw in lowered]
    if reasons:
        data["special_requirements"] = text[:500]
    return SpecPatch(**data), reasons


def next_questions(spec: WardrobeSpec) -> list[str]:
    questions = {
        "width_cm": "מה רוחב הארון הרצוי (בס״מ)?",
        "height_cm": "מה גובה הארון (בס״מ)?",
        "depth_cm": "מה העומק הרצוי? (עומק מקובל לארון בגדים הוא 60 ס״מ)",
        "body_material_id": "איזה חומר לגוף הארון? אפשרויות: סנדוויץ׳, MDF או מלמין.",
        "front_material_id": "איזה חומר לחזיתות? אפשרויות: MDF מצופה, פורניר אלון או מלמין.",
        "finish_id": "איזה גימור וצבע? למשל אלון בהיר, אגוז, לבן מט או לכה בגוון לבחירה.",
        "doors": "כמה דלתות?",
        "internal_drawers": "כמה מגירות פנימיות? אפשר גם לומר ״בלי מגירות״.",
        "shelves": "כמה מדפים?",
        "compartments": "לכמה תאים אנכיים לחלק את הארון?",
        "soft_close": "האם תרצו טריקה שקטה?",
        "delivery": "האם נדרשת הובלה?",
        "installation": "האם נדרשת התקנה?",
        "city": "לאיזו עיר ההובלה או ההתקנה?",
    }
    return [questions[f] for f in spec.missing_fields() if f in questions][:2]


def run_mock_agent(message: str, current: WardrobeSpec) -> AgentOutput:
    if is_ambiguous_dimension_phrase(message):
        return AgentOutput(
            reply=SIMULATED_PREFIX + "לא הבנתי בוודאות: לאילו מידות התכוונתם ובאילו יחידות? "
                                     "למשל ״רוחב 200 ס״מ וגובה 300 ס״מ״.",
            clarification_needed=True,
            missing_fields=current.missing_fields(),
        )
    patch, reasons = extract_patch(message, current)
    updated = current.model_copy(update=patch.model_dump(exclude_unset=True))
    captured = [FIELD_LABELS_HE[f] for f in patch.model_dump(exclude_unset=True) if f in FIELD_LABELS_HE]
    parts = []
    if captured:
        parts.append("רשמתי: " + ", ".join(captured) + ".")
    questions = next_questions(updated)
    if questions:
        parts.append(" ".join(questions))
    elif not captured:
        parts.append("לא זיהיתי פרטים חדשים. אפשר גם לעדכן את המפרט ישירות בטופס.")
    else:
        parts.append("נראה שיש לנו את כל הפרטים. אפשר לעבור לסיכום ולשליחה לנגר.")
    if reasons:
        parts.append("הבקשה תועבר לבדיקה ידנית של הנגר.")
    return AgentOutput(
        reply=SIMULATED_PREFIX + " ".join(parts),
        proposed_spec_patch=patch,
        missing_fields=updated.missing_fields(),
        clarification_needed=bool(questions),
        requires_manual_review=bool(reasons),
        manual_review_reasons=reasons,
    )
