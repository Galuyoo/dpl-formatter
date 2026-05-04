from core.email_sender import EmailAttachment, SmtpConfig, send_email_with_attachment


class FakeSMTP:
    sent_messages = []
    started_tls = False
    login_args = None

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def starttls(self):
        FakeSMTP.started_tls = True

    def login(self, username, password):
        FakeSMTP.login_args = (username, password)

    def send_message(self, message):
        FakeSMTP.sent_messages.append(message)


def test_send_email_with_attachment(monkeypatch):
    import smtplib

    FakeSMTP.sent_messages = []
    FakeSMTP.started_tls = False
    FakeSMTP.login_args = None

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    smtp_config = SmtpConfig(
        host="smtp.example.com",
        port=587,
        username="user@example.com",
        password="secret",
        from_email="from@example.com",
        use_tls=True,
    )

    attachment = EmailAttachment(
        filename="tracking.csv",
        content=b"order,tracking\n1,ABC",
        mime_type="text/csv",
    )

    send_email_with_attachment(
        smtp_config=smtp_config,
        to_email="ops@example.com",
        subject="Tracking CSV",
        body="Attached.",
        attachment=attachment,
    )

    assert FakeSMTP.started_tls is True
    assert FakeSMTP.login_args == ("user@example.com", "secret")
    assert len(FakeSMTP.sent_messages) == 1

    message = FakeSMTP.sent_messages[0]
    assert message["From"] == "from@example.com"
    assert message["To"] == "ops@example.com"
    assert message["Subject"] == "Tracking CSV"
    assert message.is_multipart()
