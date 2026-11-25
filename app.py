"""
================================================================================
ARCHIVO: app.py
Rol: Application Factory + Composition Root
================================================================================
Este archivo YA NO contiene lógica de negocio. Solo:
  1. Crea la aplicación Flask (Application Factory).
  2. Registra blueprints.
  3. Cablea (wiring) las dependencias concretas → abstracciones
     (esto es el corazón del Principio de Inversión de Control).

TEMAS DEL CURSO CUBIERTOS EN ESTE ARCHIVO:
  ✔ Ingeniería Inversa            → sección "MAPA DE DEPENDENCIAS"
  ✔ Refactorización + SRP + DRY   → sección "FACTORY + WIRING"
  ✔ Principio Abierto/Cerrado     → sección "REGISTRO DE BLUEPRINTS"
  ✔ Principio de Inversión de Control → sección "COMPOSITION ROOT"
  ✔ Gestión de la configuración   → sección "CARGA DE CONFIG"
  ✔ Gestión del cambio            → sección "VERSIONADO Y MIGRACIONES"
================================================================================
"""
import os
from flask import Flask

# --- Configuración ---------------------------------------------------------
from config import get_config

# --- Modelos / repositorios / servicios (abstracciones e implementaciones) --
from repositories.user_repository import JsonUserRepository
from repositories.report_repository import JsonReportRepository
from repositories.mission_repository import JsonMissionRepository
from services.auth_service import AuthService
from services.report_service import ReportService, KeywordClassifier
from services.analytics_service import AnalyticsService
from services.image_classifier import get_default_classifier
from services.storage_service import LocalStorageService
from services.gamification_service import GamificationService
from services.community_service import CommunityService
from services.email_service import EmailNotifier
from services.daily_report_service import DailyReportService, DailyReportScheduler

# --- Blueprints (rutas) ----------------------------------------------------
from routes.auth_routes import auth_bp
from routes.main_routes import main_bp
from routes.community_routes import community_bp


# ============================================================================
# 🔍 INGENIERÍA INVERSA — MAPA DE DEPENDENCIAS
# ----------------------------------------------------------------------------
# Antes de refactorizar, mapeamos las dependencias del app.py original:
#
#   app.py  ──▶  flask (framework)
#     │
#     ├──▶  hash/session         (seguridad)
#     ├──▶  json.load / json.dump (persistencia)
#     ├──▶  rutas /login /register /  (presentación)
#     ├──▶  keywords ("bache", "luz"...) (dominio)
#     └──▶  Counter / estadísticas (analytics)
#
# Conclusión de la ingeniería inversa:
#   - app.py tenía DEMASIADAS responsabilidades → viola SRP.
#   - Las rutas, la persistencia y el dominio estaban acoplados.
#   - El código no era testeable sin arrancar Flask.
#
# Refactorización aplicada (equivalente a "Extract Class" + "Extract Module"):
#   - Persistencia    → repositories/*
#   - Reglas negocio  → services/*
#   - HTTP            → routes/*
#   - Configuración   → config.py
#   - Wiring          → app.py (este archivo, ahora delgado)
# ============================================================================


# ============================================================================
# 🏭 APPLICATION FACTORY + WIRING (Refactorización + SRP + DRY + IoC)
# ----------------------------------------------------------------------------
# - SRP: este archivo solo construye y configura la app.
# - DRY: hay UNA sola función que crea la app; tests y prod la reutilizan.
# - IoC: los servicios reciben sus dependencias desde aquí (Composition Root).
#   Ninguna capa instancia sus propias dependencias; todas las reciben.
# ============================================================================
def create_app(env: str | None = None) -> Flask:
    app = Flask(__name__)

    # ------------------------------------------------------------------------
    # ⚙️ GESTIÓN DE LA CONFIGURACIÓN
    # Cargamos la clase adecuada según el entorno. Toda la config vive en
    # config.py: aquí NO hay valores "hardcoded".
    # ------------------------------------------------------------------------
    cfg = get_config(env)
    app.config.from_object(cfg)

    # ------------------------------------------------------------------------
    # 🧩 COMPOSITION ROOT — PRINCIPIO DE INVERSIÓN DE CONTROL (IoC)
    # Aquí, y solo aquí, se decide QUÉ implementación concreta se usará.
    # Los servicios y rutas dependen de las ABSTRACCIONES (DIP).
    # Cambiar JSON → SQL solo toca estas 3 líneas.
    # ------------------------------------------------------------------------
    user_repo = JsonUserRepository(app.config["USERS_FILE"])
    report_repo = JsonReportRepository(app.config["REPORTS_FILE"])
    mission_repo = JsonMissionRepository(app.config["MISSIONS_FILE"])

    # Adaptación "EcoEco / BarrioVivo":
    #   - classifier (OCP)  → IA local de imágenes + clasificador de texto
    #   - storage           → equivalente a Firebase Storage (disco local)
    #   - gamification      → puntos e insignias comunitarias
    image_classifier = get_default_classifier(
        min_confidence=app.config["AI_MIN_CONFIDENCE"]
    )
    storage = LocalStorageService(
        upload_dir=app.config["UPLOAD_DIR"],
        allowed_extensions=app.config["ALLOWED_IMAGE_EXTENSIONS"],
        static_folder=app.static_folder,
        static_url="/static",
    )
    gamification = GamificationService(user_repo, app.config["ECO_POINTS"])

    auth_service = AuthService(user_repo)
    report_service = ReportService(report_repo, classifier=KeywordClassifier())
    analytics_service = AnalyticsService(
        critical_threshold=app.config["CRITICAL_ZONE_THRESHOLD"]
    )
    community_service = CommunityService(
        report_repo=report_repo,
        mission_repo=mission_repo,
        user_repo=user_repo,
        gamification=gamification,
    )

    # Exponemos los servicios vía `app.extensions` para que las rutas
    # los resuelvan sin acoplarse a implementaciones (IoC).
    app.extensions["user_repo"] = user_repo
    app.extensions["report_repo"] = report_repo
    app.extensions["mission_repo"] = mission_repo
    app.extensions["auth_service"] = auth_service
    app.extensions["report_service"] = report_service
    app.extensions["analytics_service"] = analytics_service
    app.extensions["image_classifier"] = image_classifier
    app.extensions["storage_service"] = storage
    app.extensions["gamification_service"] = gamification
    app.extensions["community_service"] = community_service

    # --- Reporte diario por correo -----------------------------------------
    daily_report = DailyReportService(
        report_repo=report_repo,
        mission_repo=mission_repo,
        user_repo=user_repo,
        notifier=EmailNotifier(
            host=app.config["SMTP_HOST"],
            port=app.config["SMTP_PORT"],
            user=app.config["SMTP_USER"],
            password=app.config["SMTP_PASSWORD"],
            sender=app.config["REPORT_EMAIL_FROM"],
            recipients=app.config["REPORT_EMAIL_TO"],
        ),
        utc_offset_hours=app.config["DAILY_REPORT_UTC_OFFSET"],
    )
    app.extensions["daily_report_service"] = daily_report

    # ------------------------------------------------------------------------
    # 🧱 REGISTRO DE BLUEPRINTS — PRINCIPIO ABIERTO/CERRADO (OCP)
    # Para añadir un nuevo módulo (ej. /admin, /api/v2) NO modificamos este
    # bloque más allá de una línea nueva. Está ABIERTO a extensión pero
    # CERRADO a modificación.
    # ------------------------------------------------------------------------
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(community_bp)

    # ------------------------------------------------------------------------
    # 🔁 GESTIÓN DEL CAMBIO — VERSIONADO Y MIGRACIONES
    # Exponemos la versión de la app para que el frontend / logs puedan
    # identificar cambios. Si en el futuro migramos de JSON a SQL,
    # esta sección es el punto único de migración (patrón "Migration Hook").
    # ------------------------------------------------------------------------
    app.config.setdefault("APP_VERSION", "1.1.0")
    _run_migrations(app)

    return app


# ============================================================================
# 🔁 GESTIÓN DEL CAMBIO — MIGRACIONES / COMPATIBILIDAD
# ----------------------------------------------------------------------------
# Cuando cambia el esquema de datos, esta función aplica migraciones
# incrementales. Así, actualizar la app en producción no rompe datos viejos.
# ============================================================================
def _run_migrations(app: Flask) -> None:
    """Aplica migraciones incrementales idempotentes."""
    current = app.config.get("APP_VERSION", "1.0.0")
    app.logger.info(f"[migraciones] versión actual: {current}")

    # Ejemplo: si vienes de <1.1.0, normaliza el campo "severity".
    # (Solo un placeholder — se activa cuando exista el cambio real).
    # if current < "1.1.0":
    #     ...migrar datos...


# ============================================================================
# 🚀 PUNTO DE ENTRADA
# ============================================================================
app = create_app()

if __name__ == "__main__":
    # Config vía variables de entorno (Gestión de configuración).
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))

    # Envío automático del reporte diario por correo. Con debug=True Flask
    # arranca 2 procesos (reloader): solo lo iniciamos en el proceso "real".
    if app.config["DAILY_REPORT_ENABLED"] and (
        not app.config["DEBUG"] or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    ):
        DailyReportScheduler(
            app.extensions["daily_report_service"],
            send_at=app.config["DAILY_REPORT_TIME"],
            state_file=app.config["DAILY_REPORT_STATE_FILE"],
        ).start()
        print(f"[correo] Reporte diario programado a las {app.config['DAILY_REPORT_TIME']} "
              f"→ {', '.join(app.config['REPORT_EMAIL_TO']) or '(sin destinatario)'}")

    app.run(host=host, port=port, debug=app.config["DEBUG"])