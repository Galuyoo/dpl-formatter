from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    mime_type: str


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    use_tls: bool = True


def send_email_with_attachment(
    *,
    smtp_config: SmtpConfig,
    to_email: str,
    subject: str,
    body: str,
    attachment: EmailAttachment,
) -> None:
    if not to_email:
        raise ValueError("Recipient email is required.")

    if not smtp_config.host:
        raise ValueError("SMTP host is required.")

    if not smtp_config.from_email:
        raise ValueError("From email is required.")

    message = EmailMessage()
    message["From"] = smtp_config.from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    maintype, subtype = _split_mime_type(attachment.mime_type)

    message.add_attachment(
        attachment.content,
        maintype=maintype,
        subtype=subtype,
        filename=attachment.filename,
    )

    with smtplib.SMTP(smtp_config.host, smtp_config.port, timeout=30) as smtp:
        if smtp_config.use_tls:
            smtp.starttls()

        if smtp_config.username or smtp_config.password:
            smtp.login(smtp_config.username, smtp_config.password)

        smtp.send_message(message)


def _split_mime_type(mime_type: str) -> tuple[str, str]:
    if not mime_type or "/" not in mime_type:
        return "application", "octet-stream"

    maintype, subtype = mime_type.split("/", 1)
    return maintype.strip() or "application", subtype.strip() or "octet-stream"
