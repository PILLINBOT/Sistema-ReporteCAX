"""
================================================================================
MÓDULO: services/daily_report_service.py
PRINCIPIO SOLID: SRP + DIP
================================================================================
Arma el resumen diario (reportes del día + jornada ganadora con su equipo de
participantes) y lo envía por correo a través de un `Notifier`.

  DailyReportService.build_message(day) → texto del resumen
  DailyReportService.send(day)          → construye y envía
  DailyReportScheduler                  → hilo que lo envía cada día a la hora
                                          configurada (DAILY_REPORT_TIME)
================================================================================
"""
import json
import logging
import os
import threading
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from models.mission import CleanupMission
from models.report import Report
from repositories.base import MissionRepository, ReportRepository, UserRepository
from services.email_service import Notifier

log = logging.getLogger(__name__)

STATUS_RANK = {"COMPLETADA": 2, "EN_CURSO": 1, "PENDIENTE": 0}
MEDALS = ["🥇", "🥈", "🥉"]


class DailyReportService:
    def __init__(
        self,
        report_repo: ReportRepository,
        mission_repo: MissionRepository,
        user_repo: UserRepository,
        notifier: Notifier,
        utc_offset_hours: int = -5,
    ):
        self.report_repo = report_repo
        self.mission_repo = mission_repo
        self.user_repo = user_repo
        self.notifier = notifier
        self.tz = timezone(timedelta(hours=utc_offset_hours))

    # --- Fechas ---------------------------------------------------------------
    def today(self) -> date:
        return datetime.now(self.tz).date()

    def _local_date(self, value: Optional[str]) -> Optional[date]:
        """Convierte un ISO (con o sin hora/zona) a fecha local."""
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if len(value) <= 10:            # solo "YYYY-MM-DD": ya es fecha local
            return dt.date()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(self.tz).date()

    # --- Datos ----------------------------------------------------------------
    def reports_of(self, day: date) -> List[Report]:
        return [r for r in self.report_repo.list_all() if self._local_date(r.created_at) == day]

    def winning_mission(self, day: date) -> Optional[CleanupMission]:
        """Jornada ganadora: la del día más avanzada y con más participantes."""
        candidates = [
            m for m in self.mission_repo.list_all()
            if self._local_date(m.date) == day or self._local_date(m.created_at) == day
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda m: (STATUS_RANK.get(m.status, 0), m.participant_count, m.eco_reward),
        )

    # --- Mensaje --------------------------------------------------------------
    def build_message(self, day: Optional[date] = None) -> str:
        day = day or self.today()
        reports = self.reports_of(day)
        lines = [
            "📊 Reporte diario · Ciudad Inteligente Cajamarca",
            f"📅 {day.strftime('%d/%m/%Y')}",
            "",
            f"📝 Reportes del día: {len(reports)}",
        ]

        if reports:
            by_status = Counter(r.status for r in reports)
            by_group = Counter(r.group for r in reports)
            by_sev = Counter(r.severity for r in reports)
            by_zone = Counter(r.zone for r in reports)
            lines += [
                "• Estado: " + ", ".join(
                    f"{k.replace('_', ' ').title()} {by_status.get(k, 0)}"
                    for k in ("PENDIENTE", "EN_PROCESO", "RESUELTO")
                ),
                "• Tipo: " + ", ".join(f"{g.title()} {n}" for g, n in by_group.most_common()),
                "• Severidad: " + ", ".join(
                    f"{s.title()} {by_sev.get(s, 0)}" for s in ("critico", "intermedio", "bajo")
                ),
            ]
            zone, count = by_zone.most_common(1)[0]
            lines.append(f"📍 Zona con más reportes: {zone} ({count})")
            top = max(reports, key=lambda r: (r.upvotes or 0))
            if (top.upvotes or 0) > 0:
                lines.append(f"🔥 Más votado: \"{top.title}\" ({top.upvotes} votos, {top.zone})")
            criticos = [r for r in reports if r.severity == "critico" and r.status != "RESUELTO"]
            if criticos:
                lines.append(f"⚠️ Críticos sin resolver: {len(criticos)}")
        else:
            lines.append("Sin reportes nuevos hoy.")

        lines += ["", "🏆 Equipo ganador del día"]
        mission = self.winning_mission(day)
        if mission is None:
            lines.append("No hubo jornadas de limpieza hoy.")
        else:
            lines += [
                f"Jornada: {mission.title} (#{mission.id})",
                f"Zona: {mission.zone} · Estado: {mission.status.replace('_', ' ').title()}",
                f"Recompensa: {mission.eco_reward} eco-puntos",
                f"Integrantes ({mission.participant_count}):",
            ]
            members = []
            for username in mission.participants:
                user = self.user_repo.get_by_username(username)
                members.append((
                    username,
                    (user.name or username) if user else username,
                    (user.eco_points or 0) if user else 0,
                    len(user.active_badges or []) if user else 0,
                ))
            members.sort(key=lambda m: m[2], reverse=True)
            for i, (username, name, points, badges) in enumerate(members):
                icon = MEDALS[i] if i < len(MEDALS) else "•"
                label = name if name == username else f"{name} (@{username})"
                lines.append(f"{icon} {label} — {points} pts, {badges} insignias")
            if not members:
                lines.append("(sin participantes registrados)")

        return "\n".join(lines)

    def send(self, day: Optional[date] = None) -> str:
        day = day or self.today()
        text = self.build_message(day)
        self.notifier.send(f"Reporte diario Cajamarca · {day.strftime('%d/%m/%Y')}", text)
        return text


class DailyReportScheduler:
    """Hilo en segundo plano que envía el resumen una vez al día.
    Guarda la última fecha enviada en un JSON para no duplicar envíos
    (por ejemplo, si el servidor se reinicia)."""

    def __init__(self, service: DailyReportService, send_at: str, state_file: str):
        hh, mm = (int(x) for x in send_at.split(":"))
        self.service = service
        self.send_at = time(hh, mm)
        self.state_file = state_file
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _last_sent(self) -> Optional[str]:
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f).get("last_sent")
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _mark_sent(self, day: date) -> None:
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump({"last_sent": day.isoformat()}, f)

    def tick(self) -> bool:
        """Envía si ya pasó la hora de hoy y aún no se envió. Devuelve True si envió."""
        now = datetime.now(self.service.tz)
        if now.time() < self.send_at or self._last_sent() == now.date().isoformat():
            return False
        try:
            self.service.send(now.date())
            self._mark_sent(now.date())
            log.info("[correo] reporte diario %s enviado", now.date())
            return True
        except Exception as exc:  # no tumbar el servidor por un fallo de red
            log.error("[correo] error enviando reporte diario: %s", exc)
            return False

    def _run(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(60)   # revisa cada minuto

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="daily-report", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
