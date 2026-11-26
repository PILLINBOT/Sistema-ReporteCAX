"""Punto de entrada para servidores de producción (gunicorn): `gunicorn wsgi:app`."""
from app import app  # noqa: F401
