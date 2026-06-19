"""Saude dos agendamentos: ultimo run, proximo horario e deteccao de atraso.

Le o historico e os projetos registrados (via Store) e calcula, por projeto:
- a ultima execucao e seu status;
- o proximo horario previsto (a partir do cron);
- se esta **atrasado** (passou um horario previsto sem execucao correspondente).
"""

from datetime import datetime

from .cron import CronExpr


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def is_overdue(expected, last_started, now, grace_min):
    """True se passou o horario `expected` (+ folga) sem execucao a partir dele."""
    if expected is None:
        return False
    if (now - expected).total_seconds() <= grace_min * 60:
        return False
    return last_started is None or last_started < expected


def latest_by_project(store):
    """Ultimo registro de execucao por projeto (o historico esta em ordem)."""
    runs = {}
    for rec in store.read_history(limit=1000000):
        runs[rec["name"]] = rec
    return runs


def health(store, now=None, grace_min=None):
    """Lista de dicts com a saude de cada projeto registrado."""
    from .notify import alert_opts
    from .scheduler import load_workflow

    now = now or datetime.now()
    if grace_min is None:
        grace_min = alert_opts(store).get("missed_grace_min", 5)
    last = latest_by_project(store)

    rows = []
    for name, info in sorted(store.read_projects().items()):
        row = {
            "name": name,
            "path": info["path"],
            "enabled": info.get("enabled", True),
            "schedule": None,
            "error": None,
            "last": last.get(name),
            "next_run": None,
            "expected": None,
            "overdue": False,
        }
        try:
            wf, _ = load_workflow(info["path"])
            row["schedule"] = wf["schedule"]
        except Exception as e:
            row["error"] = str(e)

        sched = row["schedule"]
        if sched and row["enabled"]:
            try:
                cx = CronExpr(sched)
                nxt = cx.next_after(now)
                row["next_run"] = nxt.isoformat(timespec="minutes") if nxt else None
                prev = cx.prev_at_or_before(now)
                row["expected"] = prev.isoformat(timespec="minutes") if prev else None
                last_started = _parse_dt(row["last"]["started"]) if row["last"] else None
                row["overdue"] = is_overdue(prev, last_started, now, grace_min)
            except ValueError:
                pass
        rows.append(row)
    return rows


def daemon_status(store, timeout_min=None):
    """(vivo?, ultimo_heartbeat) do daemon, com base no arquivo de heartbeat."""
    from .notify import alert_opts

    if timeout_min is None:
        timeout_min = alert_opts(store).get("heartbeat_timeout_min", 3)
    hb = store.read_heartbeat()
    if not hb:
        return False, None
    alive = (datetime.now() - hb).total_seconds() < timeout_min * 60
    return alive, hb
