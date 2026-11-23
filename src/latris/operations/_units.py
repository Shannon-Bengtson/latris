"""pint adapter — the ONLY module that owns the unit registry.

Every SD unit string is parsed against this one registry, so quantities from
different equations are always comparable (pint refuses to mix registries).
pint's defaults already cover time, mass, length, volume, money-free physical
units and ``dimensionless``; the definitions below add the non-physical
quantities SD models routinely count.
"""

from __future__ import annotations

import re

import pint

# Custom base dimensions for things SD models count but physics doesn't.
# Extending the set is a one-line addition here.
_CUSTOM_UNITS = (
    "person = [population] = people = persons",
    "dollar = [money] = USD = dollars",
    "item = [item] = items",
)

_ureg = pint.UnitRegistry()
for _definition in _CUSTOM_UNITS:
    _ureg.define(_definition)

Quantity = _ureg.Quantity
PINT_ERRORS: tuple[type[Exception], ...] = (pint.errors.PintError,)


class UnitError(ValueError):
    """A unit string that the registry can't interpret."""


def registry() -> pint.UnitRegistry:
    return _ureg


def parse_unit(spec: str) -> pint.Unit:
    """Parse a unit string, raising :class:`UnitError` with a model-facing message."""
    text = (spec or "").strip()
    if not text:
        raise UnitError("units must not be empty (use 'dimensionless' for a pure number)")
    try:
        return _ureg.parse_units(text)
    except Exception as exc:  # user input: pint surfaces malformed text as many error types (incl. TokenError)
        raise UnitError(
            f"unknown or malformed units {spec!r} — use pint syntax such as "
            f"'liter', 'person/year', '1/year', 'dollar/month' or 'dimensionless'; count other things "
            f"(bikes, patients, trees) as 'item', e.g. 'item/year'"
        ) from exc


def quantity(value: float, units: str) -> pint.Quantity:
    return Quantity(value, parse_unit(units))


def is_compatible(a: pint.Unit, b: pint.Unit) -> bool:
    return _ureg.Quantity(1.0, a).is_compatible_with(b)


def describe(unit: pint.Unit) -> str:
    """Human-readable unit text (``dimensionless`` rather than an empty string)."""
    return str(unit) or "dimensionless"


_SUPERSCRIPT = {"2": "²", "3": "³"}


def display(spec: str) -> str:
    """A unit string as a reader sees it: ``m**3/s`` → ``m³/s``, ``s/m**(1/3)`` → ``s/m^(1/3)``, and nothing
    for ``dimensionless``. For text shown to people; the stored string stays in pint syntax."""
    text = (spec or "").strip()
    if text == "dimensionless":
        return ""
    text = re.sub(r"\*\*\s*([23])(?![\d.])", lambda m: _SUPERSCRIPT[m.group(1)], text)
    return text.replace("**", "^")


def with_units(number: str, spec: str) -> str:
    """``number`` followed by its displayed units (just the number when dimensionless)."""
    shown = display(spec)
    return f"{number} {shown}" if shown else number


def library_version() -> str:
    return pint.__version__
