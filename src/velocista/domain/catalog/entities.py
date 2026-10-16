"""Dominio del contexto `catalog`.

Los IDs de tipo de componente son códigos cortos y estables (tipo SKU) que comparten
backend, frontend y semillas; se mantienen como están (no se traducen). El tipo de campo
de una especificación usa `number`/`text` (antes n/t).
"""

from __future__ import annotations

# IDs de tipo de componente (estables; usados también por las ranuras del builder).
COMPONENT_TYPE_IDS: tuple[str, ...] = (
    "mcu",
    "exp",
    "linea",
    "mux",
    "motor",
    "driver",
    "bat",
    "reg",
    "rueda",
    "chasis",
    "sw",
    "enc",
    "imu",
    "turb",
)
