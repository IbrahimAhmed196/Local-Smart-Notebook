"""Slide geometry and renderer labels."""

SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.75
BODY_TOP, BODY_H = 1.8, 4.85
MAX_TABLE_ROWS_PER_SLIDE = 8
LABELS = {  # the few words the renderer adds itself
    "en": {
        "sources": "Sources",
        "footer": "Sources:",
        "page": "page",
        "pages": "pages",
        "cont": "(cont.)",
        "audience": "For:",
    },
    "ar": {
        "sources": "\u0627\u0644\u0645\u0635\u0627\u062f\u0631",
        "footer": "\u0627\u0644\u0645\u0635\u0627\u062f\u0631:",
        "page": "\u0635\u0641\u062d\u0629",
        "pages": "\u0635\u0641\u062d\u0627\u062a",
        "cont": "(\u062a\u0627\u0628\u0639)",
        "audience": "\u0627\u0644\u062c\u0645\u0647\u0648\u0631:",
    },
}
