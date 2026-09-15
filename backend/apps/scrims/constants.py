"""Vocabularies for the scrim slice."""

# Warp-in labels from the sheet's Configurables list, in sheet order (call-outs, not distances).
WARP_IN_LABELS: list[str] = [
    *"ABCD",
    "1",
    "2",
    "3",
    "4",
    "A Baby Carrot",
    "Baby Carrot",
    "Carrot Baby",
    "Da Baby Carrot",
    "1 Baby Carrot",
    "2 Baby Carrots",
    "3 Baby Carrots",
    "4 Baby Carrots",
    *[f"Red {n}" for n in (1, 2, 3, 4)],
    *[f"Blue {n}" for n in (1, 2, 3, 4)],
    *[f"Red {c}" for c in "ABCD"],
    *[f"Blue {c}" for c in "ABCD"],
    *[f"Visitor {n}" for n in (1, 2, 3, 4)],
    *[f"Home {n}" for n in (1, 2, 3, 4)],
    *[f"Visitor {c}" for c in "ABCD"],
    *[f"Home {c}" for c in "ABCD"],
]

WARP_CALLS_PER_SET = 4
