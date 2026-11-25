"""
Envía (o muestra) el reporte diario por correo sin tener el servidor abierto.

  python enviar_reporte.py                 → envía el reporte de hoy
  python enviar_reporte.py --dry-run       → solo lo muestra en pantalla
  python enviar_reporte.py --fecha 2026-10-15 --dry-run

Útil para el Programador de tareas de Windows (ver README, sección Correo).
"""
import argparse
import sys
from datetime import date

from app import create_app


def main() -> int:
    parser = argparse.ArgumentParser(description="Reporte diario por correo")
    parser.add_argument("--dry-run", action="store_true", help="no envía, solo imprime")
    parser.add_argument("--fecha", help="día a reportar (YYYY-MM-DD); por defecto hoy")
    args = parser.parse_args()

    service = create_app().extensions["daily_report_service"]
    day = date.fromisoformat(args.fecha) if args.fecha else None

    if args.dry_run:
        print(service.build_message(day))
        return 0
    try:
        service.send(day)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Reporte enviado por correo.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
