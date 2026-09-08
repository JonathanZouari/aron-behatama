"""קטלוג לדוגמה: חומרי גוף, חומרי חזיתות, גימורים ואזורי הובלה.

הקוד (code) של פריט קטלוג הוא גם הקוד שלו במחירון, כך שהמפרט שומר מזהה
קטלוג ומנוע התמחור מוצא את המחיר לפי אותו קוד.
"""

CATALOG = [
    # חומרי גוף
    {"kind": "body_material", "code": "SANDWICH17", "name_he": "סנדוויץ׳ 17 מ״מ",
     "description_he": "לוח עץ רב-שכבתי חזק ויציב, מתאים לארונות גדולים.", "sort_order": 1},
    {"kind": "body_material", "code": "MDF18", "name_he": "MDF 18 מ״מ",
     "description_he": "לוח סיבים דחוס, משטח חלק וחסכוני.", "sort_order": 2},
    {"kind": "body_material", "code": "MELAMINE18", "name_he": "מלמין 18 מ״מ",
     "description_he": "לוח מצופה מלמין, עמיד לשריטות, מגיע בגוונים.", "sort_order": 3},
    # חומרי חזיתות
    {"kind": "front_material", "code": "MDF_COATED", "name_he": "MDF מצופה",
     "description_he": "חזית MDF עם ציפוי צבע או פורמייקה.", "sort_order": 1},
    {"kind": "front_material", "code": "OAK_VENEER", "name_he": "פורניר אלון",
     "description_he": "שכבת עץ אלון טבעי על לוח, מראה עץ אמיתי.", "sort_order": 2},
    {"kind": "front_material", "code": "MELAMINE_FRONT", "name_he": "מלמין",
     "description_he": "חזית מלמין חסכונית ועמידה.", "sort_order": 3},
    # גימורים
    {"kind": "finish", "code": "FIN_OAK_LIGHT", "name_he": "אלון בהיר",
     "description_he": "גוון עץ בהיר וחם.", "sort_order": 1},
    {"kind": "finish", "code": "FIN_WALNUT", "name_he": "אגוז",
     "description_he": "גוון עץ כהה ועשיר.", "sort_order": 2},
    {"kind": "finish", "code": "FIN_WHITE_MATTE", "name_he": "לבן מט",
     "description_he": "צבע לבן מט נקי.", "sort_order": 3},
    {"kind": "finish", "code": "FIN_LACQUER", "name_he": "לכה בגוון לבחירה",
     "description_he": "צביעה בלכה בגוון לפי בחירה (ציינו את הגוון בשדה צבע).", "sort_order": 4},
    # אזורי הובלה
    {"kind": "delivery_zone", "code": "DELIVERY_CENTER", "name_he": "מרכז (גוש דן)",
     "description_he": "תל אביב, רמת גן, גבעתיים, חולון, בת ים, פתח תקווה, בני ברק", "sort_order": 1},
    {"kind": "delivery_zone", "code": "DELIVERY_SHARON", "name_he": "שרון ושפלה",
     "description_he": "הרצליה, רעננה, כפר סבא, נתניה, ראשון לציון, רחובות, מודיעין", "sort_order": 2},
    {"kind": "delivery_zone", "code": "DELIVERY_NORTH", "name_he": "צפון",
     "description_he": "חיפה, קריות, עפולה, נצרת, כרמיאל, טבריה", "sort_order": 3},
    {"kind": "delivery_zone", "code": "DELIVERY_SOUTH", "name_he": "דרום",
     "description_he": "אשדוד, אשקלון, באר שבע, קריית גת", "sort_order": 4},
]

# מיפוי ערים → אזור הובלה (לדוגמה). עיר שאינה במיפוי → תמחור ידני.
CITY_TO_ZONE = {
    "תל אביב": "DELIVERY_CENTER", "תל-אביב": "DELIVERY_CENTER", "רמת גן": "DELIVERY_CENTER",
    "גבעתיים": "DELIVERY_CENTER", "חולון": "DELIVERY_CENTER", "בת ים": "DELIVERY_CENTER",
    "פתח תקווה": "DELIVERY_CENTER", "בני ברק": "DELIVERY_CENTER",
    "הרצליה": "DELIVERY_SHARON", "רעננה": "DELIVERY_SHARON", "כפר סבא": "DELIVERY_SHARON",
    "נתניה": "DELIVERY_SHARON", "ראשון לציון": "DELIVERY_SHARON", "רחובות": "DELIVERY_SHARON",
    "מודיעין": "DELIVERY_SHARON",
    "חיפה": "DELIVERY_NORTH", "קריית מוצקין": "DELIVERY_NORTH", "עפולה": "DELIVERY_NORTH",
    "נצרת": "DELIVERY_NORTH", "כרמיאל": "DELIVERY_NORTH", "טבריה": "DELIVERY_NORTH",
    "אשדוד": "DELIVERY_SOUTH", "אשקלון": "DELIVERY_SOUTH", "באר שבע": "DELIVERY_SOUTH",
    "קריית גת": "DELIVERY_SOUTH",
}


def zone_for_city(city: str | None) -> str | None:
    if not city:
        return None
    return CITY_TO_ZONE.get(city.strip())
