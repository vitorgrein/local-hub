"""Interface de linha de comando do LocalHub (comando `lhub`)."""

import argparse
import sys

from . import porcelain, remote
from .errors import LhubError
from .repository import Repo
from .utils import format_time

SHORT = 10  # tamanho do hash curto exibido


def _repo():
    return Repo.find()


def _short(oid):
    return oid[:SHORT] if oid else "-"


# --------------------------------------------------------------- handlers
def cmd_init(args):
    repo = porcelain.init(args.path, bare=args.bare)
    tipo = "bare " if args.bare else ""
    print("Repositorio LocalHub %sinicializado em %s" % (tipo, repo.lhub_dir))
    return 0


def cmd_config(args):
    glob = args.glob
    repo = None if glob else _repo()
    if args.list:
        for k, v in sorted(porcelain.config_list(repo, glob=glob).items()):
            print("%s=%s" % (k, v))
        return 0
    if args.key and args.value is not None:
        porcelain.config_set(repo, args.key, args.value, glob=glob)
        print("[%s] %s=%s" % ("global" if glob else "local", args.key, args.value))
        return 0
    if args.key:
        print(porcelain.config_list(repo, glob=glob).get(args.key, ""))
        return 0
    print("uso: lhub config [--global] <chave> <valor> | --list", file=sys.stderr)
    return 2


def cmd_add(args):
    repo = _repo()
    staged, ignored = porcelain.add(repo, args.paths, force=args.force)
    print("%d arquivo(s) adicionado(s) ao staging." % len(staged))
    if ignored:
        print("ignorado(s) por .gitignore/.lhubignore (use -f para forcar):")
        for p in ignored:
            print("    %s" % p)
    return 0


def cmd_rm(args):
    repo = _repo()
    removed = porcelain.rm(repo, args.paths, from_disk=not args.cached)
    print("%d arquivo(s) removido(s) do rastreamento." % len(removed))
    return 0


def cmd_status(args):
    st = porcelain.status(_repo())
    if st["detached"]:
        print("HEAD destacado")
    else:
        print("Na branch %s" % st["branch"])
    if st["merging"]:
        print("** merge em andamento - resolva os conflitos e faca commit **")

    if st["staged"]:
        print("\nMudancas prontas para commit (staged):")
        for p, s in sorted(st["staged"].items()):
            print("    %-12s %s" % (s + ":", p))
    if st["unstaged"]:
        print("\nMudancas nao adicionadas (use 'lhub add'):")
        for p, s in sorted(st["unstaged"].items()):
            print("    %-12s %s" % (s + ":", p))
    if st["untracked"]:
        print("\nArquivos nao rastreados (use 'lhub add'):")
        for p in st["untracked"]:
            print("    %s" % p)
    if not (st["staged"] or st["unstaged"] or st["untracked"]):
        print("nada a commitar, arvore de trabalho limpa")
    return 0


def cmd_commit(args):
    repo = _repo()
    oid = porcelain.commit(repo, args.message, allow_empty=args.allow_empty)
    branch = repo.current_branch() or "HEAD"
    print("[%s %s] %s" % (branch, _short(oid), args.message.splitlines()[0]))
    return 0


def cmd_log(args):
    repo = _repo()
    entries = porcelain.log(repo, max_count=args.max_count)
    if not entries:
        print("ainda nao ha commits")
        return 0
    for oid, c in entries:
        if args.oneline:
            print("%s %s" % (_short(oid), c["message"].splitlines()[0] if c["message"] else ""))
        else:
            print("commit %s" % oid)
            if len(c["parents"]) > 1:
                print("Merge: %s" % " ".join(_short(p) for p in c["parents"]))
            print("Autor: %s <%s>" % (c["author_name"], c["author_email"]))
            print("Data:  %s" % format_time(c["timestamp"], c["tz_offset"]))
            print("")
            for line in c["message"].splitlines() or [""]:
                print("    %s" % line)
            print("")
    return 0


def cmd_show(args):
    repo = _repo()
    oid, c, diff = porcelain.show(repo, args.rev)
    print("commit %s" % oid)
    print("Autor: %s <%s>" % (c["author_name"], c["author_email"]))
    print("Data:  %s" % format_time(c["timestamp"], c["tz_offset"]))
    print("")
    for line in c["message"].splitlines() or [""]:
        print("    %s" % line)
    print("")
    sys.stdout.write(diff)
    return 0


def cmd_diff(args):
    repo = _repo()
    text = porcelain.diff(repo, staged=args.staged, rev_a=args.rev_a, rev_b=args.rev_b)
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def cmd_branch(args):
    repo = _repo()
    if args.delete:
        porcelain.branch_delete(repo, args.delete)
        print("branch '%s' apagada" % args.delete)
        return 0
    if args.name:
        porcelain.branch_create(repo, args.name)
        print("branch '%s' criada" % args.name)
        return 0
    branches, current = porcelain.branch_list(repo)
    if not branches:
        print("(nenhuma branch ainda - faca o primeiro commit)")
        return 0
    for name in sorted(branches):
        marca = "*" if name == current else " "
        print("%s %s" % (marca, name))
    return 0


def cmd_checkout(args):
    repo = _repo()
    res = porcelain.checkout(repo, args.target, create=args.create, force=args.force)
    if res.get("created"):
        print("criada e selecionada a branch '%s'" % res["branch"])
    elif res.get("detached"):
        print("HEAD agora em %s (modo destacado)" % _short(res["oid"]))
    else:
        print("selecionada a branch '%s'" % res["branch"])
    return 0


def cmd_remote(args):
    repo = _repo()
    if args.action == "add":
        if not (args.name and args.url):
            print("uso: lhub remote add <nome> <caminho>", file=sys.stderr)
            return 2
        porcelain.remote_add(repo, args.name, args.url)
        print("remoto '%s' -> %s" % (args.name, args.url))
        return 0
    remotes = porcelain.remote_list(repo)
    if not remotes:
        print("(nenhum remoto configurado)")
    for name, info in sorted(remotes.items()):
        print("%s\t%s" % (name, info.get("url")))
    return 0


def cmd_clone(args):
    dst = args.dst
    if not dst:
        base = args.src.rstrip("/\\").replace("\\", "/").split("/")[-1]
        dst = base or "clone"
    repo, branch = remote.clone(args.src, dst)
    print("clonado em '%s' (branch %s)" % (repo.root, branch))
    return 0


def cmd_fetch(args):
    repo = _repo()
    updated = remote.fetch(repo, args.remote)
    if not updated:
        print("ja esta atualizado")
    for name, (old, new) in sorted(updated.items()):
        print("  %s -> %s  (%s)" % (_short(old), _short(new), name))
    return 0


def cmd_push(args):
    repo = _repo()
    res = remote.push(repo, args.remote, args.branch, force=args.force)
    if res["up_to_date"]:
        print("ja esta atualizado")
    else:
        print(
            "%s %s -> %s  (%s/%s)"
            % (
                _short(res["old"]) if res["old"] else "novo",
                _short(res["new"]),
                res["remote"],
                res["remote"],
                res["branch"],
            )
        )
    return 0


def cmd_pull(args):
    repo = _repo()
    res = remote.pull(repo, args.remote, args.branch)
    s = res["status"]
    if s == "atualizado":
        print("ja esta atualizado")
    elif s == "fast-forward":
        print("fast-forward %s -> %s" % (_short(res["old"]), _short(res["new"])))
    elif s == "merge":
        print("merge concluido, novo commit %s" % _short(res["new"]))
    elif s in ("criado", "sem-remoto", "a-frente"):
        print(s.replace("-", " "))
    elif s == "conflito":
        print("CONFLITO ao mesclar. Resolva os arquivos abaixo, depois 'lhub add' + 'lhub commit':")
        for p in res["conflicts"]:
            print("    %s" % p)
        return 1
    return 0


def cmd_run(args):
    from . import scheduler

    rec = scheduler.run_now(args.target)
    commit = _short(rec["commit"]) if rec["commit"] else "-"
    dirt = " *mudancas nao commitadas*" if rec["dirty"] else ""
    print("[%s] %s  %ss  (commit %s)%s" % (rec["status"], rec["name"], rec["duration_s"], commit, dirt))
    if rec.get("log"):
        print("log: %s" % rec["log"])
    return 0 if rec["status"] in ("ok", "skipped") else 1


def cmd_sched(args):
    from . import scheduler
    from .cron import CronExpr

    sch = scheduler.Scheduler()
    action = args.action

    if action == "add":
        if not args.target:
            print("uso: lhub sched add <pasta-do-projeto>", file=sys.stderr)
            return 2
        info = sch.register(args.target)
        print("registrado: %s -> %s" % (info["name"], info["path"]))
        return 0

    if action in ("rm", "remove"):
        if not args.target:
            print("uso: lhub sched rm <nome>", file=sys.stderr)
            return 2
        sch.unregister(args.target)
        print("removido: %s" % args.target)
        return 0

    if action == "list":
        projects = sch.store.read_projects()
        if not projects:
            print("(nenhum projeto registrado - use 'lhub sched add <pasta>')")
            return 0
        for name in sorted(projects):
            info = projects[name]
            try:
                wf, _ = scheduler.load_workflow(info["path"])
                sched_str = wf["schedule"] or "(sem schedule)"
            except Exception as e:
                sched_str = "ERRO: %s" % e
            estado = "" if info.get("enabled", True) else "  [desativado]"
            print("%-24s %-16s %s%s" % (name, sched_str, info["path"], estado))
        return 0

    if action == "status":
        hist = sch.store.read_history(limit=args.max_count or 20)
        if not hist:
            print("(sem execucoes ainda)")
            return 0
        for rec in hist:
            print("%s  %-10s %-20s %ss  commit=%s%s"
                  % (rec["started"], rec["status"], rec["name"], rec["duration_s"],
                     (rec["commit"] or "-")[:SHORT], " (sujo)" if rec.get("dirty") else ""))
        return 0

    if action == "logs":
        if not args.target:
            print("uso: lhub sched logs <nome>", file=sys.stderr)
            return 2
        hist = sch.store.read_history(limit=1, name=args.target)
        if not hist or not hist[-1].get("log"):
            print("(sem log para: %s)" % args.target)
            return 0
        sys.stdout.write(open(hist[-1]["log"], "r", encoding="utf-8", errors="replace").read())
        return 0

    if action == "daemon":
        extra = "  + painel web em http://%s:%d" % (args.host, args.port) if args.web else ""
        print("agendador rodando (Ctrl+C para parar). Estado em: %s%s" % (sch.store.home, extra))
        try:
            sch.daemon(on_event=lambda m: print(m), web=args.web, host=args.host, port=args.port)
        except KeyboardInterrupt:
            print("\nagendador parado.")
        return 0

    if action == "web":
        from . import web

        print("painel web em http://%s:%d  (Ctrl+C para parar)" % (args.host, args.port))
        try:
            web.serve(sch, host=args.host, port=args.port)
        except KeyboardInterrupt:
            print("\npainel parado.")
        return 0

    if action == "dashboard":
        import os
        import time
        from . import monitor

        try:
            while True:
                os.system("cls" if os.name == "nt" else "clear")
                alive, seen = monitor.daemon_status(sch.store)
                print("LocalHub - Agendador   daemon: %s   heartbeat: %s"
                      % ("ON" if alive else "OFF",
                         seen.isoformat(timespec="seconds") if seen else "nunca"))
                print("-" * 92)
                print("%-22s %-9s %-15s %-9s %-19s %-16s" %
                      ("PROJETO", "SITUACAO", "SCHEDULE", "ULT.STATUS", "ULTIMO RUN", "PROXIMO"))
                for r in monitor.health(sch.store):
                    last = r.get("last") or {}
                    sit = ("ATRASADO" if r.get("overdue")
                           else "off" if not r.get("enabled")
                           else "erro" if r.get("error") else "ok")
                    print("%-22s %-9s %-15s %-9s %-19s %-16s" % (
                        r["name"][:22], sit, str(r.get("schedule") or "-")[:15],
                        str(last.get("status") or "-")[:9],
                        str(last.get("started") or "-")[:19],
                        str(r.get("next_run") or "-")[:16]))
                print("-" * 92)
                print("(atualiza a cada %ss - Ctrl+C para sair)" % args.interval)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0

    if action == "check":
        from . import monitor, notify

        alive, _ = monitor.daemon_status(sch.store)
        overdue = [r["name"] for r in monitor.health(sch.store) if r.get("overdue")]
        problems = []
        if not alive:
            problems.append("daemon offline")
        if overdue:
            problems.append("atrasados: " + ", ".join(overdue))
        if problems:
            msg = "; ".join(problems)
            notify.notify(sch.store, "[lhub] watchdog", msg, on_error=lambda m: print(m, file=sys.stderr))
            print("PROBLEMA: %s" % msg)
            return 1
        print("ok: daemon vivo e nenhum job atrasado")
        return 0

    if action == "config":
        from . import notify

        cfg = notify.load_config(sch.store)
        print("config: %s" % notify.config_path(sch.store))
        print("  e-mail:  %s" % ("habilitado" if cfg.get("email", {}).get("enabled") else "desabilitado"))
        print("  webhook: %s" % ("habilitado" if cfg.get("webhook", {}).get("enabled") else "desabilitado"))
        if not cfg:
            print("  (crie esse arquivo para configurar avisos - veja o README)")
        return 0

    if action == "tick":
        fired = sch.tick()
        print("%d job(s) disparado(s)" % fired)
        return 0

    print("uso: lhub sched {add|rm|list|status|logs|daemon|dashboard|web|check|config|tick} [alvo]", file=sys.stderr)
    return 2


# ----------------------------------------------------------------- parser
def build_parser():
    p = argparse.ArgumentParser(
        prog="lhub",
        description="LocalHub - controle de versao local em Python (sem git).",
    )
    p.add_argument("--version", action="store_true", help="mostra a versao")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("init", help="cria um repositorio")
    sp.add_argument("path", nargs="?", default=".")
    sp.add_argument("--bare", action="store_true", help="repositorio sem arvore (para servir de remoto)")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("config", help="le/grava configuracao (ex: user.name)")
    sp.add_argument("key", nargs="?")
    sp.add_argument("value", nargs="?")
    sp.add_argument("--list", action="store_true")
    sp.add_argument("--global", dest="glob", action="store_true", help="config por maquina (~/.lhubconfig.json)")
    sp.set_defaults(func=cmd_config)

    sp = sub.add_parser("add", help="adiciona arquivos ao staging")
    sp.add_argument("paths", nargs="+")
    sp.add_argument("-f", "--force", action="store_true", help="adiciona mesmo se ignorado")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("rm", help="remove arquivos do rastreamento")
    sp.add_argument("paths", nargs="+")
    sp.add_argument("--cached", action="store_true", help="remove so do index, mantem no disco")
    sp.set_defaults(func=cmd_rm)

    sp = sub.add_parser("status", help="mostra o estado da arvore")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("commit", help="grava um commit com o que esta no staging")
    sp.add_argument("-m", "--message", required=True)
    sp.add_argument("--allow-empty", action="store_true")
    sp.set_defaults(func=cmd_commit)

    sp = sub.add_parser("log", help="lista o historico de commits")
    sp.add_argument("-n", "--max-count", type=int, default=None)
    sp.add_argument("--oneline", action="store_true")
    sp.set_defaults(func=cmd_log)

    sp = sub.add_parser("show", help="mostra um commit e seu diff")
    sp.add_argument("rev", nargs="?", default="HEAD")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("diff", help="mostra diferencas")
    sp.add_argument("--staged", "--cached", action="store_true", dest="staged")
    sp.add_argument("rev_a", nargs="?")
    sp.add_argument("rev_b", nargs="?")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("branch", help="lista, cria ou apaga branches")
    sp.add_argument("name", nargs="?")
    sp.add_argument("-d", "--delete", metavar="NOME")
    sp.set_defaults(func=cmd_branch)

    sp = sub.add_parser("checkout", help="troca de branch/commit")
    sp.add_argument("target")
    sp.add_argument("-b", dest="create", action="store_true", help="cria a branch")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_checkout)

    sp = sub.add_parser("remote", help="gerencia remotos (pastas)")
    sp.add_argument("action", nargs="?")
    sp.add_argument("name", nargs="?")
    sp.add_argument("url", nargs="?")
    sp.add_argument("-v", action="store_true")
    sp.set_defaults(func=cmd_remote)

    sp = sub.add_parser("clone", help="clona de uma pasta remota")
    sp.add_argument("src")
    sp.add_argument("dst", nargs="?")
    sp.set_defaults(func=cmd_clone)

    sp = sub.add_parser("fetch", help="baixa objetos/refs do remoto")
    sp.add_argument("remote", nargs="?", default="origin")
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("push", help="envia commits ao remoto")
    sp.add_argument("remote", nargs="?", default="origin")
    sp.add_argument("branch", nargs="?")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_push)

    sp = sub.add_parser("pull", help="baixa e integra do remoto")
    sp.add_argument("remote", nargs="?", default="origin")
    sp.add_argument("branch", nargs="?")
    sp.set_defaults(func=cmd_pull)

    sp = sub.add_parser("run", help="roda agora o workflow de um projeto")
    sp.add_argument("target", help="nome registrado ou pasta do projeto")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("sched", help="agendador + painel (add/rm/list/status/logs/daemon/dashboard/web/check/config)")
    sp.add_argument("action", nargs="?", default="list",
                    help="add|rm|list|status|logs|daemon|dashboard|web|check|config|tick")
    sp.add_argument("target", nargs="?", help="pasta do projeto (add) ou nome (rm/logs)")
    sp.add_argument("-n", "--max-count", type=int, default=None, help="quantas linhas no status")
    sp.add_argument("--web", action="store_true", help="no daemon, sobe tambem o painel web")
    sp.add_argument("--host", default="127.0.0.1", help="host do painel web")
    sp.add_argument("--port", type=int, default=8787, help="porta do painel web")
    sp.add_argument("--interval", type=int, default=5, help="dashboard: segundos entre atualizacoes")
    sp.set_defaults(func=cmd_sched)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "version", False):
        from . import __version__
        print("lhub %s" % __version__)
        return 0
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except LhubError as e:
        print("lhub: erro: %s" % e, file=sys.stderr)
        return 1
    except KeyError as e:
        print("lhub: erro: objeto/ref nao encontrado: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
