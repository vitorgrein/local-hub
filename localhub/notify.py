"""Envio de avisos do agendador: e-mail (SMTP) e webhook (Teams/Slack/Discord).

A configuracao fica em `<home-do-agendador>/config.json`, por exemplo:

    {
      "email": {
        "enabled": true,
        "smtp_host": "smtp.empresa.com",
        "smtp_port": 587,
        "use_tls": true,
        "use_ssl": false,
        "username": "automacoes@empresa.com",
        "password": "***",
        "from": "automacoes@empresa.com",
        "to": ["vitor@empresa.com"]
      },
      "webhook": {
        "enabled": true,
        "url": "https://outlook.office.com/webhook/...",
        "format": "teams"
      },
      "alerts": {
        "on_failure": true,
        "on_missed": true,
        "missed_grace_min": 5,
        "heartbeat_timeout_min": 3
      }
    }
"""

import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage

from .utils import read_text


def config_path(store):
    return os.path.join(store.home, "config.json")


def load_config(store):
    txt = read_text(config_path(store))
    return json.loads(txt) if txt else {}


def alert_opts(store):
    return load_config(store).get("alerts", {})


# ----------------------------------------------------------------- e-mail
def send_email(cfg, subject, body):
    msg = EmailMessage()
    msg["From"] = cfg["from"]
    to = cfg["to"]
    msg["To"] = ", ".join(to) if isinstance(to, (list, tuple)) else to
    msg["Subject"] = subject
    msg.set_content(body)

    port = int(cfg.get("smtp_port", 587))
    if cfg.get("use_ssl"):
        server = smtplib.SMTP_SSL(cfg["smtp_host"], port, timeout=20)
    else:
        server = smtplib.SMTP(cfg["smtp_host"], port, timeout=20)
        if cfg.get("use_tls", True):
            server.starttls()
    try:
        if cfg.get("username"):
            server.login(cfg["username"], cfg.get("password", ""))
        server.send_message(msg)
    finally:
        server.quit()


# ----------------------------------------------------------------- webhook
def _webhook_payload(fmt, text):
    fmt = (fmt or "json").lower()
    if fmt == "discord":
        return {"content": text}
    if fmt == "slack":
        return {"text": text}
    if fmt == "teams":
        return {"text": text}
    return {"message": text}


def send_webhook(cfg, text):
    payload = _webhook_payload(cfg.get("format", "json"), text)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        cfg["url"], data=data, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req, timeout=20).read()


# ----------------------------------------------------------------- dispatch
def notify(store, subject, body, on_error=None):
    """Envia o aviso por todos os canais habilitados. Nunca levanta excecao."""
    log = on_error or (lambda m: None)
    cfg = load_config(store)
    email_cfg = cfg.get("email", {})
    webhook_cfg = cfg.get("webhook", {})

    if email_cfg.get("enabled"):
        try:
            send_email(email_cfg, subject, body)
        except Exception as e:
            log("aviso por e-mail falhou: %s" % e)

    if webhook_cfg.get("enabled"):
        try:
            send_webhook(webhook_cfg, subject + "\n" + body)
        except Exception as e:
            log("aviso por webhook falhou: %s" % e)
