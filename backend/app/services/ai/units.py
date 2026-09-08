"""המרת יחידות ופענוח מידות מטקסט בעברית. הקוד (לא המודל) אחראי להמרה."""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

_NUM = r"(\d+(?:[.,]\d+)?)"
_UNIT = r"\s*(מ\"מ|מ״מ|מילימטר|מילימטרים|ממ|mm|ס\"מ|ס״מ|סנטימטר|סנטימטרים|סמ|cm|מטר|מטרים|מ'|מ׳|m)?"

UNIT_TO_CM = {
    "mm": Decimal("0.1"), "cm": Decimal("1"), "m": Decimal("100"),
}


def _normalize_unit(unit: Optional[str]) -> Optional[str]:
    if not unit:
        return None
    if unit in ('מ"מ', "מ״מ", "מילימטר", "מילימטרים", "ממ", "mm"):
        return "mm"
    if unit in ('ס"מ', "ס״מ", "סנטימטר", "סנטימטרים", "סמ", "cm"):
        return "cm"
    if unit in ("מטר", "מטרים", "מ'", "מ׳", "m"):
        return "m"
    return None


def to_cm(value: Decimal, unit: Optional[str]) -> Optional[int]:
    """ממיר ערך ליחידת ס"מ שלמה. ללא יחידה: ערכים קטנים מ-10 נחשבים מטרים, אחרת ס"מ."""
    normalized = _normalize_unit(unit)
    if normalized is None:
        normalized = "m" if value < 10 else "cm"
    cm = value * UNIT_TO_CM[normalized]
    return int(cm.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_length(text: str) -> Optional[int]:
    """מחלץ מידה יחידה מטקסט כגון '2.4 מטר', '240 ס"מ', '2400 מ"מ'."""
    m = re.search(_NUM + _UNIT, text)
    if not m:
        return None
    value = Decimal(m.group(1).replace(",", "."))
    return to_cm(value, m.group(2))


def is_ambiguous_dimension_phrase(text: str) -> bool:
    """מזהה ביטויים עמומים כמו 'שניים על שלוש' או '2 על 3' ללא יחידות."""
    words = r"(אחד|אחת|שניים|שתיים|שלוש|שלושה|ארבע|ארבעה|חמש|חמישה|\d+(?:[.,]\d+)?)"
    pattern = rf"\b{words}\s*(על|x|X|×)\s*{words}\b(?!\s*(מ\"מ|מ״מ|ס\"מ|ס״מ|מטר|מ'|מ׳|cm|mm|m\b))"
    m = re.search(pattern, text)
    if not m:
        return False
    # אם שני המספרים גדולים (למשל 240 על 260) — ברור שמדובר בס"מ, לא עמום
    nums = [g for g in (m.group(1), m.group(3)) if re.fullmatch(r"\d+(?:[.,]\d+)?", g)]
    return not (len(nums) == 2 and all(Decimal(n.replace(",", ".")) >= 50 for n in nums))
