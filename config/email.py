"""SMTP locally; HTTPS on hosts that block outbound mail ports."""

from __future__ import annotations

import json
import logging
import os
import smtplib
import socket
import threading
import urllib.request
from contextlib import contextmanager

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend
from django.core.mail.utils import DNS_NAME

logger = logging.getLogger(__name__)
_ipv4_lock = threading.Lock()


@contextmanager
def ipv4_only():
    original = socket.getaddrinfo

    def _ipv4(host, port, family=0, type=0, proto=0, flags=0):
        return original(host, port, socket.AF_INET, type, proto, flags)

    with _ipv4_lock:
        socket.getaddrinfo = _ipv4
        try:
            yield
        finally:
            socket.getaddrinfo = original


class ResilientSMTPBackend(EmailBackend):
    """Force IPv4 and fall back between Gmail 465 (SSL) and 587 (STARTTLS)."""

    def _attempts(self):
        configured = (int(self.port), bool(self.use_ssl), bool(self.use_tls))
        gmail_ports = [
            (465, True, False),
            (587, False, True),
        ]
        if os.getenv("RENDER"):
            ordered = list(gmail_ports)
        else:
            ordered = [configured] + [item for item in gmail_ports if item[0] != configured[0]]
        seen = []
        for item in ordered:
            if item not in seen:
                seen.append(item)
        return seen

    def _open_once(self):
        if self._partial_connection is not None:
            self._close_connection(self._partial_connection)
            self._partial_connection = None

        connection_params = {"local_hostname": DNS_NAME.get_fqdn()}
        if self.timeout is not None:
            connection_params["timeout"] = self.timeout
        if self.use_ssl:
            connection_params["context"] = self.ssl_context

        with ipv4_only():
            self._partial_connection = self.connection_class(
                self.host, self.port, **connection_params
            )
            if not self.use_ssl and self.use_tls:
                self._partial_connection.starttls(context=self.ssl_context)
            if self.username and self.password:
                self._partial_connection.login(self.username, self.password)
            self.connection = self._partial_connection
            self._partial_connection = None
        return True

    def open(self):
        if self.connection:
            return False
        last_error = None
        for port, use_ssl, use_tls in self._attempts():
            self.port = port
            self.use_ssl = use_ssl
            self.use_tls = use_tls
            self.connection = None
            try:
                opened = self._open_once()
                logger.info(
                    "SMTP connected via %s:%s ssl=%s tls=%s",
                    self.host,
                    port,
                    use_ssl,
                    use_tls,
                )
                return opened
            except smtplib.SMTPAuthenticationError:
                raise
            except (OSError, TimeoutError, smtplib.SMTPException) as exc:
                last_error = exc
                logger.warning(
                    "SMTP %s:%s failed (%s); trying next route.",
                    self.host,
                    port,
                    exc,
                )
                self.connection = None
                if self._partial_connection is not None:
                    try:
                        self._close_connection(self._partial_connection)
                    except Exception:
                        pass
                    self._partial_connection = None
        if last_error and not self.fail_silently:
            raise last_error
        return None


class HttpsEmailBackend(BaseEmailBackend):
    """Send mail over HTTPS. Render blocks Gmail SMTP (465/587)."""

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        url = (getattr(settings, "EMAIL_HTTP_URL", "") or "").strip()
        secret = (getattr(settings, "EMAIL_HTTP_SECRET", "") or "").strip()
        if not url or not secret:
            logger.error(
                "Gmail SMTP is blocked on Render. Set EMAIL_HTTP_URL and EMAIL_HTTP_SECRET "
                "(scripts/gmail_bridge.gs) so password reset can send."
            )
            if not self.fail_silently:
                raise OSError("EMAIL_HTTP_URL is not configured")
            return 0
        sent = 0
        for message in email_messages:
            html = message.body
            for content, mimetype in getattr(message, "alternatives", []) or []:
                if mimetype == "text/html":
                    html = content
                    break
            to_addr = message.to[0] if message.to else ""
            payload = json.dumps(
                {
                    "secret": secret,
                    "to": to_addr,
                    "subject": message.subject,
                    "text": message.body,
                    "html": html,
                    "from": message.from_email,
                    "from_name": getattr(settings, "STORE_NAME", "UMII"),
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            opener = urllib.request.build_opener()
            try:
                with opener.open(request, timeout=15) as response:
                    body = response.read().decode("utf-8", "replace")
                try:
                    result = json.loads(body)
                except json.JSONDecodeError:
                    legacy_response = body.strip().lower()
                    if legacy_response in {"ok", "ok fine"}:
                        sent += 1
                        continue
                    if legacy_response == "unauthorized":
                        raise OSError("Gmail bridge rejected the secret")
                    if legacy_response.startswith("error:"):
                        raise OSError(f"Gmail bridge could not send the email: {body.strip()}")
                    raise OSError("Gmail bridge returned an invalid response")
                if not isinstance(result, dict):
                    raise OSError("Gmail bridge returned an invalid response")
                if result.get("status") == "unauthorized":
                    raise OSError("Gmail bridge rejected the secret")
                if result.get("status") != "sent":
                    detail = result.get("message")
                    raise OSError(
                        f"Gmail bridge could not send the email: {detail or 'unknown error'}"
                    )
                sent += 1
            except (OSError, TimeoutError) as exc:
                logger.exception("HTTPS email send failed for %s", to_addr)
                if not self.fail_silently:
                    raise
        return sent
