from __future__ import annotations


UNIFIED_BLOOD_CELL_CLASS_NAMES: tuple[str, ...] = (
    "RBC",
    "Platelets",
    "neutrophil",
    "lymphocyte",
    "monocyte",
    "eosinophil",
    "basophil",
)

UNIFIED_BLOOD_CELL_CLASS_TO_ID: dict[str, int] = {
    name: index for index, name in enumerate(UNIFIED_BLOOD_CELL_CLASS_NAMES)
}

WBC_SUBTYPE_TO_UNIFIED_ID: dict[str, int] = {
    "neutrophil": UNIFIED_BLOOD_CELL_CLASS_TO_ID["neutrophil"],
    "lymphocyte": UNIFIED_BLOOD_CELL_CLASS_TO_ID["lymphocyte"],
    "monocyte": UNIFIED_BLOOD_CELL_CLASS_TO_ID["monocyte"],
    "eosinophil": UNIFIED_BLOOD_CELL_CLASS_TO_ID["eosinophil"],
    "basophil": UNIFIED_BLOOD_CELL_CLASS_TO_ID["basophil"],
}
