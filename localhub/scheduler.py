"""Agendador de tarefas do LocalHub.

Roda projetos versionados com o lhub a partir de um workflow YAML (estilo
GitHub Actions), na propria maquina. Cada execucao roda na pasta de trabalho,
**fixada ao commit atual** (registra o commit e sinaliza se houver mudancas
nao commitadas), captura log e guarda historico.

Workflow (ex.: `workflow.yml` na raiz do projeto):

    name: cobranca-bradesco        # opcional (padrao = nome da pasta)
    schedule: "0 7 * * 1-5"        # cron: 07:00, seg-sex
    python: "C:/.../python.exe"    # opcional; use {python} nos comandos
    workdir: "."                   # relativo a raiz do projeto
    timeout: 3600                  # segundos por passo (opcional)
    on_dirty: warn                 # warn | skip | run  (mudancas nao commitadas)
    steps:
      - run: "{python} run.py"
      - run: "{python} daily.py"
    on_failure:
      - run: "{python} notifica_erro.py"

O estado (projetos registrados, historico e logs) fica em
`~/.lhub-scheduler/` (ou em $LHUB_SCHEDULER_HOME).
"""

import json
import os
import subprocess
import time
from datetime import datetime

from .cron import CronExpr
from .errors import LhubError
from .utils import atomic_write_text, read_text

WORKFLOW_NAMES = ("workflow.yml", "workflow.yaml", ".lhub/workflow.yml")


# --------------------------------------------------------------- workflow
def _load_yaml(path):
    try:
        import yaml
    except ImportError:
        raise LhubError(
            "PyYAML nao instalado neste interpretador; rode: pip install pyyaml"
        )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def find_workflow(project_path):
    for rel in WORKFLOW_NAMES:
        cand = os.path.join(project_path, *rel.split("/"))
        if os.path.isfile(cand):
            return cand
    raise LhubError("nenhum workflow (workflow.yml) encontrado em: %s" % project_path)


def _norm_step(step):
    if isinstance(step, str):
        return {"name": step, "run": step}
    if isinstance(step, dict) and step.get("run"):
        return {"name": step.get("name") or step["run"], "run": step["run"]}
    raise LhubError("passo invalido no workflow: %r" % (step,))


def normalize_workflow(data, project_path):
    """Aplica padroes e valida um dict de workflow."""
    if not isinstance(data, dict):
        raise LhubError("workflow deve ser um mapeamento YAML")
    name = data.get("name") or os.path.basename(os.path.abspath(project_path))
    steps = [_norm_step(s) for s in (data.get("steps") or [])]
    if not steps:
        raise LhubError("workflow '%s' nao tem 'steps'" % name)
    on_dirty = (data.get("on_dirty") or "warn").lower()
    if on_dirty not in ("warn", "skip", "run"):
        raise LhubError("on_dirty deve ser warn|skip|run (veio %r)" % on_dirty)
    return {
        "name": name,
        "schedule": data.get("schedule"),
        "python": data.get("python") or "",
        "workdir": data.get("workdir") or ".",
        "timeout": data.get("timeout"),
        "on_dirty": on_dirty,
        "steps": steps,
        "on_failure": [_norm_step(s) for s in (data.get("on_failure") or [])],
    }


def load_workflow(project_path):
    wf_path = find_workflow(project_path)
    return normalize_workflow(_load_yaml(wf_path), project_path), wf_path


# --------------------------------------------------------------- repo state
def _repo_state(project_path):
    """(commit, sujo?) do projeto, ou (None, False) se nao for repo lhub."""
    try:
        from . import worktree
        from .repository import Repo

        repo = Repo.find(project_path, required=False)
        if not repo:
            return None, False
        return repo.resolve_head(), worktree.has_local_changes(repo)
    except Exception:
        return None, False


# --------------------------------------------------------------- execucao
def _run_steps(steps, workdir, python, timeout, log):
    """Roda passos sequenciais; devolve (status, registros_dos_passos)."""
    records = []
    status = "ok"
    for step in steps:
        cmd = step["run"].replace("{python}", python or "python")
        log.write(("\n$ %s\n" % cmd).encode("utf-8", "replace"))
        log.flush()
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                shell=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            code = proc.returncode
        except subprocess.TimeoutExpired:
            log.write(("\n[timeout apos %ss]\n" % timeout).encode("utf-8"))
            code = -1
        log.flush()
        records.append({"name": step["name"], "exit": code})
        if code != 0:
            status = "failed"
            break
    return status, records


class Store:
    """Persistencia do agendador em ~/.lhub-scheduler/."""

    def __init__(self, home=None):
        self.home = (
            home
            or os.environ.get("LHUB_SCHEDULER_HOME")
            or os.path.join(os.path.expanduser("~"), ".lhub-scheduler")
        )
        self.projects_path = os.path.join(self.home, "projects.json")
        self.state_path = os.path.join(self.home, "state.json")
        self.history_path = os.path.join(self.home, "history.jsonl")
        self.logs_dir = os.path.join(self.home, "logs")
        self.heartbeat_path = os.path.join(self.home, "heartbeat.txt")

    def _read_json(self, path):
        txt = read_text(path)
        return json.loads(txt) if txt else {}

    def read_projects(self):
        return self._read_json(self.projects_path)

    def write_projects(self, data):
        atomic_write_text(self.projects_path, json.dumps(data, ensure_ascii=False, indent=2))

    def read_state(self):
        return self._read_json(self.state_path)

    def write_state(self, data):
        atomic_write_text(self.state_path, json.dumps(data, ensure_ascii=False, indent=2))

    def new_log_path(self, name, when):
        d = os.path.join(self.logs_dir, name)
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, when.strftime("%Y%m%d_%H%M%S") + ".log")

    def append_history(self, record):
        os.makedirs(self.home, exist_ok=True)
        with open(self.history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_history(self, limit=20, name=None):
        txt = read_text(self.history_path)
        if not txt:
            return []
        out = []
        for line in txt.splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if name and rec.get("name") != name:
                continue
            out.append(rec)
        return out[-limit:]

    def write_heartbeat(self):
        atomic_write_text(self.heartbeat_path, datetime.now().isoformat())

    def read_heartbeat(self):
        txt = read_text(self.heartbeat_path)
        if not txt:
            return None
        try:
            return datetime.fromisoformat(txt.strip())
        except ValueError:
            return None


# --------------------------------------------------------------- agendador
class Scheduler:
    def __init__(self, store=None):
        self.store = store or Store()

    # --- registro de projetos ---
    def register(self, project_path):
        project_path = os.path.abspath(project_path)
        wf, _ = load_workflow(project_path)  # valida que existe e é valido
        projects = self.store.read_projects()
        projects[wf["name"]] = {"path": project_path, "enabled": True}
        self.store.write_projects(projects)
        return {"name": wf["name"], "path": project_path}

    def unregister(self, name):
        projects = self.store.read_projects()
        if name not in projects:
            raise LhubError("projeto nao registrado: %s" % name)
        del projects[name]
        self.store.write_projects(projects)

    def resolve_path(self, target):
        """Aceita um nome registrado ou um caminho de pasta."""
        projects = self.store.read_projects()
        if target in projects:
            return projects[target]["path"]
        if os.path.isdir(target):
            return os.path.abspath(target)
        raise LhubError("projeto nao registrado e nao e uma pasta: %s" % target)

    # --- execucao de um projeto ---
    def run_project(self, target, trigger="manual"):
        project_path = self.resolve_path(target)
        wf, wf_path = load_workflow(project_path)
        return self._execute(wf, project_path, trigger)

    def _execute(self, wf, project_path, trigger):
        name = wf["name"]
        started = datetime.now()
        commit, dirty = _repo_state(project_path)

        if dirty and wf["on_dirty"] == "skip":
            record = {
                "name": name,
                "trigger": trigger,
                "started": started.isoformat(timespec="seconds"),
                "finished": started.isoformat(timespec="seconds"),
                "duration_s": 0,
                "status": "skipped",
                "commit": commit,
                "dirty": True,
                "steps": [],
                "log": None,
            }
            self.store.append_history(record)
            return record

        workdir = os.path.normpath(os.path.join(project_path, wf["workdir"]))
        log_path = self.store.new_log_path(name, started)
        with open(log_path, "wb") as log:
            header = (
                "# %s | %s | trigger=%s\n# commit=%s dirty=%s workdir=%s\n"
                % (name, started.isoformat(timespec="seconds"), trigger,
                   commit, dirty, workdir)
            )
            log.write(header.encode("utf-8", "replace"))
            if dirty:
                log.write(b"# AVISO: ha mudancas nao commitadas; rodando o estado atual da pasta\n")
            log.flush()

            status, steps = _run_steps(
                wf["steps"], workdir, wf["python"], wf["timeout"], log
            )
            if status == "failed" and wf["on_failure"]:
                log.write(b"\n# on_failure\n")
                log.flush()
                _run_steps(wf["on_failure"], workdir, wf["python"], wf["timeout"], log)

        finished = datetime.now()
        record = {
            "name": name,
            "trigger": trigger,
            "started": started.isoformat(timespec="seconds"),
            "finished": finished.isoformat(timespec="seconds"),
            "duration_s": round((finished - started).total_seconds(), 1),
            "status": status,
            "commit": commit,
            "dirty": dirty,
            "steps": steps,
            "log": log_path,
        }
        self.store.append_history(record)
        return record

    # --- agendamento ---
    def due(self, now):
        """Projetos cujo cron casa com `now` e que ainda nao rodaram neste minuto."""
        state = self.store.read_state()
        minute_key = now.strftime("%Y-%m-%dT%H:%M")
        out = []
        for name, info in self.store.read_projects().items():
            if not info.get("enabled", True):
                continue
            try:
                wf, _ = load_workflow(info["path"])
            except LhubError:
                continue
            if not wf["schedule"]:
                continue
            try:
                if not CronExpr(wf["schedule"]).matches(now):
                    continue
            except ValueError:
                continue
            if state.get(name) == minute_key:
                continue
            out.append((name, info["path"], wf))
        return out

    def tick(self, now=None, on_event=None):
        """Roda os jobs vencidos no minuto atual; devolve quantos dispararam."""
        from . import notify

        now = now or datetime.now()
        state = self.store.read_state()
        minute_key = now.strftime("%Y-%m-%dT%H:%M")
        results = []
        for name, path, wf in self.due(now):
            rec = self._execute(wf, path, trigger="schedule")
            results.append(rec)
            state[name] = minute_key
            self.store.write_state(state)

        if notify.alert_opts(self.store).get("on_failure", True):
            for rec in results:
                if rec["status"] == "failed":
                    notify.notify(
                        self.store,
                        "[lhub] '%s' FALHOU" % rec["name"],
                        "Status: %s\nInicio: %s\nCommit: %s\nLog: %s"
                        % (rec["status"], rec["started"], rec.get("commit"), rec.get("log")),
                        on_error=on_event,
                    )
        return len(results)

    def watchdog(self, now=None, on_event=None):
        """Detecta jobs atrasados (horario previsto sem execucao) e avisa 1x por slot."""
        from . import monitor, notify

        if not notify.alert_opts(self.store).get("on_missed", True):
            return
        now = now or datetime.now()
        state = self.store.read_state()
        alerted = state.setdefault("_alerted_missed", {})
        changed = False
        for row in monitor.health(self.store, now):
            if row.get("overdue") and row.get("expected"):
                if alerted.get(row["name"]) != row["expected"]:
                    notify.notify(
                        self.store,
                        "[lhub] '%s' NAO rodou" % row["name"],
                        "Estava previsto para %s e nao ha execucao correspondente.\nProximo: %s"
                        % (row["expected"], row.get("next_run")),
                        on_error=on_event,
                    )
                    alerted[row["name"]] = row["expected"]
                    changed = True
        if changed:
            self.store.write_state(state)

    def daemon(self, on_event=None, web=False, host="127.0.0.1", port=8787):
        """Loop residente: a cada minuto, dispara os jobs vencidos e checa atrasos.

        `on_event(msg)` recebe mensagens do proprio agendador. Se `web=True`,
        sobe tambem o painel web em http://host:port.
        """
        def emit(msg):
            (on_event or (lambda m: None))(msg)

        if web:
            from . import web as webmod

            webmod.start_in_thread(self, host, port)
            emit("painel web em http://%s:%d" % (host, port))

        emit("agendador iniciado: %s" % self.store.home)
        self.store.write_heartbeat()
        while True:
            now = datetime.now()
            # dorme ate o inicio do proximo minuto
            time.sleep(max(1, 60 - now.second))
            now = datetime.now()
            self.store.write_heartbeat()
            try:
                fired = self.tick(now, on_event=emit)
                self.watchdog(now, on_event=emit)
                if fired:
                    emit("%s: %d job(s) disparado(s)" % (now.strftime("%H:%M"), fired))
            except Exception as e:  # nunca derruba o daemon por causa de um job
                emit("erro no tick: %s" % e)


# --------------------------------------------------------------- atalho
def run_now(target, store=None):
    return Scheduler(store).run_project(target, trigger="manual")
