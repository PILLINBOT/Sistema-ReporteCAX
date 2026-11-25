"""
================================================================================
MÓDULO: services/email_service.py
PRINCIPIO SOLID: Dependency Inversion (DIP) + OCP
================================================================================
Envío del reporte diario por correo electrónico usando SMTP (librería estándar,
sin dependencias). `Notifier` es la abstracción; `EmailNotifier` la
implementación concreta (Gmail, Outlook o cualquier servidor SMTP).
================================================================================
"""
import html
import smtplib
import ssl
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import List


class Notifier(ABC):
    @abstractmethod
    def send(self, subject: str, text: str) -> None: ...


class NotifierError(RuntimeError):
    pass


class EmailNotifier(Notifier):
    def __init__(self, host: str, port: int, user: str, password: str,
                 sender: str, recipients: List[str], timeout: int = 30):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender or user
        self.recipients = recipients
        self.timeout = timeout

    def send(self, subject: str, text: str) -> None:
        if not (self.user and self.password):
            raise NotifierError("Faltan SMTP_USER / SMTP_PASSWORD en el archivo .env.")
        if not self.recipients:
            raise NotifierError("Falta REPORT_EMAIL_TO (destinatario) en el archivo .env.")

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        msg.set_content(text)
        msg.add_alternative(_to_html(text), subtype="html")

        try:
            ctx = ssl.create_default_context()
            if self.port == 465:
                s = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=ctx)
            else:
                s = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
                s.starttls(context=ctx)
            with s:
                s.ehlo()
                # Gmail corta la conexión con AUTH PLAIN si la clave es incorrecta;
                # con AUTH LOGIN devuelve un error claro (535).
                if "login" in s.esmtp_features.get("auth", "").lower():
                    s.esmtp_features["auth"] = "LOGIN"
                s.login(self.user, self.password)
                s.send_message(msg)
        except smtplib.SMTPAuthenticationError as exc:
            raise NotifierError(
                "El servidor de correo rechazó el usuario/contraseña "
                "(en Gmail usa una contraseña de aplicación)."
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise NotifierError(f"No se pudo enviar el correo: {exc}") from exc


def _to_html(text: str) -> str:
    """Convierte el texto del reporte en un HTML simple y legible."""
    rows = []
    for line in text.splitlines():
        line = html.escape(line)
        if not line:
            rows.append("<br>")
        elif line.startswith(("📊", "📝", "🏆")):
            rows.append(f'<h3 style="margin:16px 0 6px">{line}</h3>')
        else:
            rows.append(f'<div style="margin:2px 0">{line}</div>')
    return (
        '<div style="font-family:Segoe UI,Arial,sans-serif;font-size:15px;'
        'color:#1f2937;max-width:600px">'
        + "".join(rows)
        + "</div>"
    )
