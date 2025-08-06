from app import email


def _capture_email(monkeypatch):
    sent = {}

    class FakeSendGridClient:
        def __init__(self, *args, **kwargs):
            pass

        def send(self, message):
            sent['message'] = message
            class Response:
                status_code = 202
                body = ''
                headers = {}
            return Response()

    monkeypatch.setattr(email, "SendGridAPIClient", FakeSendGridClient)
    return sent


def test_confirmation_email_cc(monkeypatch):
    sent = _capture_email(monkeypatch)
    email.send_confirmation_email(
        "user@example.com", [{"name": "Alice", "jersey_number": 5}]
    )
    cc_list = sent['message'].get()['personalizations'][0]['cc']
    assert any(addr['email'] == 'tim@posasports.org' for addr in cc_list)


def test_pines_confirmation_email_cc(monkeypatch):
    sent = _capture_email(monkeypatch)
    email.send_pines_confirmation_email(
        "user@example.com", [{"name": "Bob", "jersey_number": 7}]
    )
    cc_list = sent['message'].get()['personalizations'][0]['cc']
    assert any(addr['email'] == 'tim@posasports.org' for addr in cc_list)
