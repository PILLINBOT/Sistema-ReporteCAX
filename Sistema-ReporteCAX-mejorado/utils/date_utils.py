"""Funciones auxiliares para manejar fechas de forma consistente."""
from datetime import datetime, timezone
from typing import Optional


def parse_datetime_utc(value: Optional[str]) -> Optional[datetime]:
    """Convierte una fecha ISO 8601 a datetime con zona horaria UTC.

    Acepta fechas antiguas sin zona horaria y fechas que terminan en 'Z'.
    Devuelve None cuando el valor está vacío o no tiene un formato válido.
    """
    if not value or not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)
