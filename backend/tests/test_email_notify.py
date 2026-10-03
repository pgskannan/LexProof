from app.lexproof.services import email_notify as en

RECORD = {
    "id": "r1", "request_type": "demo", "full_name": "Asha\r\nBcc: evil@x.com Rao", "work_email": "asha@example.com",
    "company": "Acme", "role": "procurement", "team_size": "51-200", "use_case": "Supplier MSAs", "created_at": "2026-10-02T00:00:00Z",
}


class FakeSMTP:
    instances = []

    def __init__(self, host, port, context=None, timeout=None):
        self.host, self.port, self.sent, self.logged_in = host, port, [], None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, message):
        self.sent.append(message)


def test_skipped_when_not_configured(monkeypatch):
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert en.send_request_notification(RECORD, smtp_factory=FakeSMTP) is False


def test_sends_to_team_with_reply_to_requester(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setenv("SMTP_USERNAME", "team@lexproofsolutions.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.delenv("TRIAL_NOTIFY_TO", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert en.send_request_notification(RECORD, smtp_factory=FakeSMTP) is True
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("mailserver.businessidentity.llc", 465)
    assert smtp.logged_in == ("team@lexproofsolutions.com", "pw")
    (message,) = smtp.sent
    assert message["To"] == "team@lexproofsolutions.com"
    assert message["Reply-To"] == "asha@example.com"
    assert message["Subject"].startswith("New demo request: Acme")
    assert "\n" not in message["Subject"] and message["Bcc"] is None
    assert "Procurement / source-to-pay" in message.get_content()


def test_smtp_failure_never_raises(monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "team@lexproofsolutions.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")

    def boom(*args, **kwargs):
        raise OSError("connection refused")

    assert en.send_request_notification(RECORD, smtp_factory=boom) is False
