"""Painel web (somente leitura) do agendador, usando apenas a stdlib.

Sobe um servidor HTTP que mostra a saude de cada job (ultimo run, status,
proximo horario, atraso) e o estado do daemon (heartbeat). A pagina se
atualiza sozinha. Tambem expoe /api/health em JSON.
"""

import html
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import monitor


def _badge(text, color):
    return '<span style="background:%s;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px">%s</span>' % (color, html.escape(text))


def _row_html(row):
    last = row.get("last") or {}
    status = last.get("status") or "-"
    color = {"ok": "#2e7d32", "failed": "#c62828", "skipped": "#f9a825"}.get(status, "#757575")
    if row.get("error"):
        situacao = _badge("workflow invalido", "#c62828")
    elif not row.get("enabled"):
        situacao = _badge("desativado", "#757575")
    elif row.get("overdue"):
        situacao = _badge("ATRASADO", "#c62828")
    else:
        situacao = _badge("ok", "#2e7d32")
    return (
        "<tr>"
        "<td><b>%s</b></td>"
        "<td>%s</td>"
        "<td><code>%s</code></td>"
        "<td>%s</td>"
        "<td>%s</td>"
        "<td>%s</td>"
        "<td>%s</td>"
        "</tr>"
    ) % (
        html.escape(row["name"]),
        situacao,
        html.escape(str(row.get("schedule") or row.get("error") or "-")),
        _badge(status, color),
        html.escape(str(last.get("started") or "-")),
        html.escape(str(row.get("next_run") or "-")),
        html.escape(str(last.get("commit") or "-")[:10]),
    )


def render_html(store):
    rows = monitor.health(store)
    alive, last_seen = monitor.daemon_status(store)
    daemon_badge = (
        _badge("daemon ON", "#2e7d32") if alive else _badge("daemon OFF", "#c62828")
    )
    seen = last_seen.isoformat(timespec="seconds") if last_seen else "nunca"
    table = "".join(_row_html(r) for r in rows) or '<tr><td colspan="7">(nenhum projeto registrado)</td></tr>'
    return """<!doctype html>
<html lang="pt-br"><head>
<meta charset="utf-8"><meta http-equiv="refresh" content="10">
<title>LocalHub - Agendador</title>
<style>
 body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222}}
 h1{{font-size:20px}} .sub{{color:#666;font-size:13px;margin-bottom:16px}}
 table{{border-collapse:collapse;width:100%%}}
 th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #eee;font-size:14px}}
 th{{color:#666;font-weight:600;border-bottom:2px solid #ddd}}
 code{{background:#f4f4f4;padding:1px 5px;border-radius:4px}}
</style></head><body>
<h1>LocalHub &middot; Agendador {daemon}</h1>
<div class="sub">heartbeat: {seen} &middot; atualizado: {now} &middot; atualiza a cada 10s</div>
<table>
<tr><th>Projeto</th><th>Situacao</th><th>Schedule</th><th>Ultimo status</th><th>Ultimo run</th><th>Proximo</th><th>Commit</th></tr>
{table}
</table>
</body></html>""".format(
        daemon=daemon_badge,
        seen=html.escape(seen),
        now=datetime.now().isoformat(timespec="seconds"),
        table=table,
    )


class _Handler(BaseHTTPRequestHandler):
    store = None

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/health"):
            body = json.dumps(monitor.health(self.store), default=str, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        else:
            self._send(200, "text/html; charset=utf-8", render_html(self.store).encode("utf-8"))

    def log_message(self, *args):  # silencia o log de acesso
        pass


def _make_server(store, host, port):
    handler = type("BoundHandler", (_Handler,), {"store": store})
    return ThreadingHTTPServer((host, port), handler)


def serve(scheduler_or_store, host="127.0.0.1", port=8787):
    """Bloqueante: serve o painel ate Ctrl+C."""
    store = getattr(scheduler_or_store, "store", scheduler_or_store)
    _make_server(store, host, port).serve_forever()


def start_in_thread(scheduler, host="127.0.0.1", port=8787):
    """Sobe o painel numa thread daemon e devolve o servidor."""
    httpd = _make_server(scheduler.store, host, port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
