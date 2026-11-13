"""Small, dependency-free text helpers used by the rule-based router and the guards."""
from __future__ import annotations

import re
import unicodedata

# Hindi (Devanagari) words -> English keywords, so Hindi questions can be routed without any AI.
HINDI_WORDS = {
    "बल": "force", "द्रव्यमान": "mass", "त्वरण": "acceleration", "वेग": "velocity", "चाल": "speed",
    "गति": "motion", "दूरी": "distance", "समय": "time", "धारा": "current", "वोल्टेज": "voltage",
    "विभव": "voltage", "प्रतिरोध": "resistance", "घनत्व": "density", "दाब": "pressure",
    "ऊर्जा": "energy", "शक्ति": "power", "कार्य": "work", "ऊष्मा": "heat", "तापमान": "temperature",
    "मोलरता": "molarity", "मोल": "mole", "अम्ल": "acid", "क्षार": "base", "तरंग": "wave",
    "आवृत्ति": "frequency", "तरंगदैर्ध्य": "wavelength", "लेंस": "lens", "दर्पण": "mirror",
    "घर्षण": "friction", "संवेग": "momentum", "आवेग": "impulse", "पेंडुलम": "pendulum",
    "लोलक": "pendulum", "स्प्रिंग": "spring", "कमानी": "spring", "कोणीय": "angular",
    "बलाघूर्ण": "torque", "गुरुत्व": "gravity", "गुरुत्वाकर्षण": "gravitation", "कक्षीय": "orbital",
    "पलायन": "escape", "प्रक्षेप्य": "projectile", "परास": "range", "ऊँचाई": "height",
    "आयतन": "volume", "सांद्रता": "concentration", "तनुकरण": "dilution", "मोलर": "molar",
    "आणविक": "molecular", "द्रव": "fluid", "उत्प्लावन": "buoyancy", "व्यास": "diameter",
    "त्रिज्या": "radius", "अभिकेंद्र": "centripetal", "वृत्तीय": "circular", "दोलन": "oscillation",
    "ताप": "heat", "ऊष्मागतिकी": "thermodynamics", "घूर्णन": "rotation", "जड़त्व": "inertia",
    "द्रव्यमान-केंद्र": "centre of mass", "टक्कर": "collision", "विद्युत": "electrical", "ओम": "ohm",
    "ऊँचाई": "height", "समाधान": "solution", "ग्राम": "gram", "लीटर": "litre", "किलोग्राम": "kg",
}
_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_SUPER = str.maketrans({"²": "2", "³": "3", "⁻": "-", "¹": "1", "·": " ", "×": "*", "−": "-", "–": "-", "÷": "/"})

STOPWORDS = set(
    "a an the of for to in on at by with and or is are was be what how find calculate compute determine "
    "give me please tell get value its it this that when if then from as using use given have has "
    "can i we you do does did will would should kya hai ka ki ke se ko mein par".split()
)


def normalise(text: str) -> str:
    """Lower-case, convert Devanagari digits, translate Hindi keywords, tidy symbols."""
    t = unicodedata.normalize("NFKC", text or "").translate(_DEV_DIGITS).translate(_SUPER).lower()
    for hi, en in sorted(HINDI_WORDS.items(), key=lambda kv: -len(kv[0])):
        if hi in t:
            t = t.replace(hi, " " + en + " ")
    return re.sub(r"\s+", " ", t).strip()


def tokens(text: str) -> list[str]:
    t = normalise(text)
    return [w for w in re.findall(r"[a-z0-9=^/.]+", t) if w not in STOPWORDS and len(w) > 0]


def squash(text: str) -> str:
    """Question without spaces, so 'f = m a' still matches the keyword 'f=ma'."""
    return re.sub(r"[\s*]+", "", normalise(text))


NUM = r"[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?"
_UNIT = r"(?:kg|mg|g|m/s2|m/s|km/h|kmph|km/hr|newtons?|n|joules?|kj|j|watts?|kw|w|volts?|v|amps?|amperes?|a|ohms?|ω|hz|mol/l|moles?|mol|ml|l|litres?|liters?|cm3|m3|cm|km|mm|m|sec|seconds?|s|mins?|minutes?|hrs?|hours?|h|kpa|pa|atm|k|°c|°f|deg(?:rees?)?|°|kg/m3|g/cm3|rad/s|rad|m)"
QUANTITY_RE = re.compile(r"(?<![\w.])(" + NUM + r")\s*(" + _UNIT + r")?(?![a-z0-9])", re.I)

# unit text -> physical class; used to match a number to a calculator field like "Mass (kg)"
UNIT_CLASS = {
    "kg": "mass", "g": "mass", "mg": "mass",
    "m/s": "velocity", "km/h": "velocity", "kmph": "velocity", "km/hr": "velocity",
    "m/s2": "acceleration",
    "n": "force", "newton": "force", "newtons": "force",
    "j": "energy", "joule": "energy", "joules": "energy", "kj": "energy",
    "w": "power", "watt": "power", "watts": "power", "kw": "power",
    "v": "voltage", "volt": "voltage", "volts": "voltage",
    "a": "current", "amp": "current", "amps": "current", "ampere": "current", "amperes": "current",
    "ohm": "resistance", "ohms": "resistance", "ω": "resistance",
    "hz": "frequency", "mol": "moles", "mole": "moles", "moles": "moles", "mol/l": "molarity",
    "ml": "volume", "l": "volume", "litre": "volume", "litres": "volume", "liter": "volume", "liters": "volume",
    "m3": "volume", "cm3": "volume",
    "m": "length", "cm": "length", "km": "length", "mm": "length",
    "s": "time", "sec": "time", "second": "time", "seconds": "time", "min": "time", "mins": "time",
    "minute": "time", "minutes": "time", "h": "time", "hr": "time", "hrs": "time", "hour": "time", "hours": "time",
    "pa": "pressure", "kpa": "pressure", "atm": "pressure",
    "k": "temperature", "°c": "temperature", "°f": "temperature",
    "°": "angle", "deg": "angle", "degree": "angle", "degrees": "angle", "rad": "angle",
    "kg/m3": "density", "g/cm3": "density", "rad/s": "angular_velocity",
}
# words inside a field label that tell us its class when there is no unit in the label
LABEL_WORD_CLASS = {
    "mass": "mass", "force": "force", "velocity": "velocity", "speed": "velocity", "acceleration": "acceleration",
    "time": "time", "current": "current", "voltage": "voltage", "resistance": "resistance", "power": "power",
    "energy": "energy", "work": "energy", "distance": "length", "length": "length", "radius": "length",
    "height": "length", "depth": "length", "displacement": "length", "position": "length", "wavelength": "length",
    "frequency": "frequency", "density": "density", "pressure": "pressure", "volume": "volume", "area": "area",
    "temperature": "temperature", "angle": "angle", "moles": "moles", "molarity": "molarity", "period": "time",
}


def digits_to_ascii(text: str) -> str:
    return (text or "").translate(_DEV_DIGITS)


def extract_numbers(text: str) -> list[float]:
    out: list[float] = []
    for m in re.finditer(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?", digits_to_ascii(text or "")):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            continue
    return out


def unit_class(unit: str | None) -> str | None:
    if not unit:
        return None
    return UNIT_CLASS.get(unit.lower().replace("²", "2").replace("³", "3"))


def label_class(label: str) -> str | None:
    """Class of a calculator field from its label, e.g. 'Mass (kg)' -> mass, 'Acceleration (m/s²)' -> acceleration."""
    low = normalise(label)
    m = re.search(r"\(([^)]*)\)", low)
    if m:
        c = unit_class(m.group(1).strip())
        if c:
            return c
    for w in re.findall(r"[a-z]+", low):
        if w in LABEL_WORD_CLASS:
            return LABEL_WORD_CLASS[w]
    return None
