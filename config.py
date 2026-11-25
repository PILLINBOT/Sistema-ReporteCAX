"""
================================================================================
MÓDULO: config.py
TEMA DEL CURSO: Introducción a la gestión de la configuración
================================================================================
Este archivo centraliza TODA la configuración de la aplicación (credenciales,
rutas, parámetros de negocio). Ningún otro módulo debe tener valores "hardcoded".

BENEFICIOS:
  - Cambiar de entorno (dev/prod) NO requiere tocar la lógica de negocio.
  - Los secretos se leen de variables de entorno (.env).
  - Los valores por defecto quedan documentados en un único lugar.

ADAPTACIÓN DE "EcoEco / BarrioVivo" A ESTE PROYECTO:
  Los parámetros que en Android vivían en `build.gradle.kts` (permisos, APIs,
  dependencias) y en constantes de la app, aquí viven en este único archivo:
  umbrales de IA, radio de geofencing, almacenamiento de imágenes y reglas de
  gamificación.
================================================================================
"""
import os
from datetime import timedelta


def _load_dotenv(path: str) -> None:
    """Carga un archivo .env simple (CLAVE=valor) sin dependencias externas.
    Las variables ya definidas en el entorno tienen prioridad."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


class Config:
    """Configuración base compartida por todos los entornos."""

    # --- Seguridad / Sesión ---
    SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esto-en-produccion")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # --- Parámetros de negocio (antes estaban dispersos en app.py) ---
    DEFAULT_LAT = float(os.getenv("DEFAULT_LAT", "-7.1638"))   # Cajamarca
    DEFAULT_LNG = float(os.getenv("DEFAULT_LNG", "-78.5008"))
    CRITICAL_ZONE_THRESHOLD = int(os.getenv("CRITICAL_ZONE_THRESHOLD", "5"))
    PREDICTION_WINDOW_DAYS = int(os.getenv("PREDICTION_WINDOW_DAYS", "7"))

    # --- Ubicación del almacenamiento (JSON plano o BD) ---
    DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
    USERS_FILE = os.path.join(DATA_DIR, "users.json")
    REPORTS_FILE = os.path.join(DATA_DIR, "reports.json")
    MISSIONS_FILE = os.path.join(DATA_DIR, "missions.json")

    # --- Almacenamiento de imágenes (equivalente a Firebase Storage) ---
    UPLOAD_DIR = os.getenv(
        "UPLOAD_DIR",
        os.path.join(os.path.dirname(__file__), "static", "uploads"),
    )
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "bmp"}
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(8 * 1024 * 1024)))  # 8 MB

    # --- IA local (equivalente a TensorFlow Lite on-device) ---
    # Etiquetas que devuelve el clasificador de imágenes local.
    AI_LABELS = ("Basura Detectada", "Daño Estructural", "No Concluyente")
    AI_MIN_CONFIDENCE = float(os.getenv("AI_MIN_CONFIDENCE", "0.55"))

    # --- Geolocalización / Geofencing (equivalente a FusedLocation + Geofencing) ---
    GEOFENCE_RADIUS_KM = float(os.getenv("GEOFENCE_RADIUS_KM", "3.0"))

    # --- Gamificación comunitaria ---
    # Puntos "EcoEco" que otorga cada acción relevante.
    ECO_POINTS = {
        "create_report": int(os.getenv("POINTS_CREATE_REPORT", "10")),
        "upvote_received": int(os.getenv("POINTS_UPVOTE_RECEIVED", "2")),
        "report_in_process": int(os.getenv("POINTS_REPORT_IN_PROCESS", "5")),
        "report_resolved": int(os.getenv("POINTS_REPORT_RESOLVED", "25")),
        "mission_join": int(os.getenv("POINTS_MISSION_JOIN", "15")),
        "mission_complete": int(os.getenv("POINTS_MISSION_COMPLETE", "40")),
    }

    # --- Reporte diario por correo (SMTP) ---
    # Por defecto Gmail. Para Outlook: smtp.office365.com, puerto 587.
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")          # correo que envía
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").replace(" ", "")  # contraseña de aplicación
    REPORT_EMAIL_FROM = os.getenv("REPORT_EMAIL_FROM", "") or SMTP_USER
    # Destinatarios separados por coma.
    REPORT_EMAIL_TO = [e.strip() for e in os.getenv("REPORT_EMAIL_TO", "").split(",") if e.strip()]
    # Si no se indica destinatario, se envía al mismo correo que lo manda.
    if not REPORT_EMAIL_TO and SMTP_USER:
        REPORT_EMAIL_TO = [SMTP_USER]
    # Hora local (HH:MM) a la que se envía el resumen del día.
    DAILY_REPORT_TIME = os.getenv("DAILY_REPORT_TIME", "21:00")
    # Desfase horario respecto a UTC (Perú: -5, sin horario de verano).
    DAILY_REPORT_UTC_OFFSET = int(os.getenv("DAILY_REPORT_UTC_OFFSET", "-5"))
    # "1" activa el envío automático mientras el servidor está encendido.
    DAILY_REPORT_ENABLED = os.getenv("DAILY_REPORT_ENABLED", "1") == "1"
    DAILY_REPORT_STATE_FILE = os.path.join(DATA_DIR, "daily_report_state.json")


class DevelopmentConfig(Config):
    DEBUG = True
    ENV = "development"


class ProductionConfig(Config):
    DEBUG = False
    ENV = "production"
    SESSION_COOKIE_SECURE = True   # solo HTTPS


# Registro de entornos disponibles → Open/Closed: para añadir "testing"
# o "staging" solo se agrega una clase nueva, sin modificar las existentes.
CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config(env: str | None = None):
    """
    PATRÓN: Factory Method.
    Devuelve la clase de configuración adecuada según el entorno.
    """
    env = env or os.getenv("FLASK_ENV", "development")
    return CONFIG_MAP.get(env, DevelopmentConfig)
