"""The ONLY place where unit conversion happens.

Presets, plans and layout math are all in millimetres and degrees.
The Fusion API's internal length unit is centimetres and angles are radians,
so adapter/dialog code converts through these functions and nowhere else.
"""
import math

CM_PER_MM = 0.1


def mm_to_cm(value_mm: float) -> float:
    return value_mm * CM_PER_MM


def cm_to_mm(value_cm: float) -> float:
    return value_cm / CM_PER_MM


def mm3_to_cm3(value_mm3: float) -> float:
    return value_mm3 / 1000.0


def cm3_to_mm3(value_cm3: float) -> float:
    return value_cm3 * 1000.0


def deg_to_rad(value_deg: float) -> float:
    return math.radians(value_deg)


def rad_to_deg(value_rad: float) -> float:
    return math.degrees(value_rad)


def _fmt(value: float) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def mm_expr(value_mm: float) -> str:
    """Expression for ValueInput.createByString, e.g. '6.5 mm'.

    Always uses '.' as the decimal separator. If Fusion is set to a locale that
    expects ',', Fusion may reject it; the adapter falls back to createByReal
    (via mm_to_cm) in that case.
    """
    return f"{_fmt(value_mm)} mm"


def deg_expr(value_deg: float) -> str:
    return f"{_fmt(value_deg)} deg"
