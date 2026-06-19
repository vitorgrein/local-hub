"""Testes do LocalHub: ciclo local + sincronizacao entre repositorios.

Roda com:  python -m unittest discover -s tests
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime

from localhub import porcelain, remote
from localhub.objects import parse_commit
from localhub.repository import Repo


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def make_repo(path, name="Tester"):
    repo = porcelain.init(path)
    porcelain.config_set(repo, "user.name", name)
    porcelain.config_set(repo, "user.email", "%s@test" % name.lower())
    return repo


class LocalCycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lhub_")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_commit_log_diff(self):
        work = os.path.join(self.tmp, "w")
        repo = make_repo(work)
        write(os.path.join(work, "a.txt"), "linha 1\n")
        porcelain.add(repo, [work])
        c1 = porcelain.commit(repo, "primeiro")
        self.assertTrue(parse_commit(repo, c1))

        # nada novo -> commit vazio rejeitado
        with self.assertRaises(Exception):
            porcelain.commit(repo, "vazio")

        # status limpo
        st = porcelain.status(repo)
        self.assertEqual(st["staged"], {})
        self.assertEqual(st["unstaged"], {})

        # modifica e versiona de novo
        write(os.path.join(work, "a.txt"), "linha 1\nlinha 2\n")
        st = porcelain.status(repo)
        self.assertEqual(st["unstaged"], {"a.txt": "modificado"})
        d = porcelain.diff(repo)
        self.assertIn("linha 2", d)
        porcelain.add(repo, [os.path.join(work, "a.txt")])
        c2 = porcelain.commit(repo, "segundo")

        hist = porcelain.log(repo)
        self.assertEqual([o for o, _ in hist], [c2, c1])

    def test_branch_checkout(self):
        work = os.path.join(self.tmp, "wb")
        repo = make_repo(work)
        write(os.path.join(work, "f.txt"), "main\n")
        porcelain.add(repo, [work])
        porcelain.commit(repo, "c1")

        porcelain.checkout(repo, "dev", create=True)
        write(os.path.join(work, "f.txt"), "dev\n")
        write(os.path.join(work, "novo.txt"), "so na dev\n")
        porcelain.add(repo, [work])
        porcelain.commit(repo, "na dev")

        porcelain.checkout(repo, "main")
        self.assertEqual(read(os.path.join(work, "f.txt")), "main\n")
        self.assertFalse(os.path.exists(os.path.join(work, "novo.txt")))

        porcelain.checkout(repo, "dev")
        self.assertEqual(read(os.path.join(work, "f.txt")), "dev\n")
        self.assertTrue(os.path.exists(os.path.join(work, "novo.txt")))

    def test_gitignore(self):
        work = os.path.join(self.tmp, "wi")
        repo = make_repo(work)
        write(os.path.join(work, ".gitignore"), "*.log\nbuild/\n!manter.log\n")
        write(os.path.join(work, "app.py"), "x")
        write(os.path.join(work, "debug.log"), "x")
        write(os.path.join(work, "manter.log"), "x")
        write(os.path.join(work, "build", "out.txt"), "x")
        write(os.path.join(work, "src", "main.py"), "x")

        untracked = set(porcelain.status(repo)["untracked"])
        self.assertIn("app.py", untracked)
        self.assertIn("src/main.py", untracked)
        self.assertIn(".gitignore", untracked)
        self.assertIn("manter.log", untracked)        # reincluido por !manter.log
        self.assertNotIn("debug.log", untracked)       # ignorado por *.log
        self.assertNotIn("build/out.txt", untracked)   # pasta build/ ignorada

        # add . respeita o ignore
        staged, ignored = porcelain.add(repo, [work])
        self.assertIn("app.py", staged)
        self.assertNotIn("debug.log", staged)
        self.assertNotIn("build/out.txt", staged)

        # arquivo ignorado nomeado explicitamente: pulado, salvo com force
        staged2, ignored2 = porcelain.add(repo, [os.path.join(work, "debug.log")])
        self.assertEqual(ignored2, ["debug.log"])
        staged3, _ = porcelain.add(repo, [os.path.join(work, "debug.log")], force=True)
        self.assertIn("debug.log", staged3)

    def test_gitignore_with_bom(self):
        work = os.path.join(self.tmp, "wbom")
        repo = make_repo(work)
        # .gitignore gravado com BOM UTF-8 (como PowerShell/alguns editores fazem)
        with open(os.path.join(work, ".gitignore"), "w", encoding="utf-8-sig") as f:
            f.write("*.tmp\n")
        write(os.path.join(work, "keep.txt"), "x")
        write(os.path.join(work, "lixo.tmp"), "x")
        untracked = set(porcelain.status(repo)["untracked"])
        self.assertIn("keep.txt", untracked)
        self.assertNotIn("lixo.tmp", untracked)


class Sync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lhub_")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _bare(self):
        bare = os.path.join(self.tmp, "central.lhub")
        Repo.init(bare, bare=True)
        return bare

    def test_push_clone_pull_fastforward(self):
        bare = self._bare()
        a = os.path.join(self.tmp, "A")
        repoA = make_repo(a, "Ana")
        write(os.path.join(a, "doc.txt"), "v1\n")
        porcelain.add(repoA, [a])
        porcelain.commit(repoA, "inicial")
        porcelain.remote_add(repoA, "origin", bare)
        remote.push(repoA, "origin")

        # clona em B
        b = os.path.join(self.tmp, "B")
        repoB, branch = remote.clone(bare, b)
        self.assertEqual(branch, "main")
        self.assertEqual(read(os.path.join(b, "doc.txt")), "v1\n")

        # B commita e envia
        write(os.path.join(b, "doc.txt"), "v1\nv2 de B\n")
        porcelain.add(repoB, [b])
        porcelain.commit(repoB, "B edita")
        remote.push(repoB, "origin")

        # A puxa -> fast-forward
        res = remote.pull(repoA, "origin")
        self.assertEqual(res["status"], "fast-forward")
        self.assertEqual(read(os.path.join(a, "doc.txt")), "v1\nv2 de B\n")

    def test_pull_three_way_merge(self):
        bare = self._bare()
        a = os.path.join(self.tmp, "A")
        repoA = make_repo(a, "Ana")
        write(os.path.join(a, "base.txt"), "comum\n")
        porcelain.add(repoA, [a])
        porcelain.commit(repoA, "base")
        porcelain.remote_add(repoA, "origin", bare)
        remote.push(repoA, "origin")

        b = os.path.join(self.tmp, "B")
        repoB, _ = remote.clone(bare, b)

        # A mexe num arquivo, B noutro (sem conflito)
        write(os.path.join(a, "do_a.txt"), "feito por A\n")
        porcelain.add(repoA, [a])
        porcelain.commit(repoA, "A adiciona arquivo")

        write(os.path.join(b, "do_b.txt"), "feito por B\n")
        porcelain.add(repoB, [b])
        porcelain.commit(repoB, "B adiciona arquivo")
        remote.push(repoB, "origin")

        res = remote.pull(repoA, "origin")
        self.assertEqual(res["status"], "merge")
        # merge commit tem dois pais
        self.assertEqual(len(parse_commit(repoA, res["new"])["parents"]), 2)
        # ambos os arquivos existem em A
        self.assertTrue(os.path.exists(os.path.join(a, "do_a.txt")))
        self.assertTrue(os.path.exists(os.path.join(a, "do_b.txt")))

    def test_pull_conflict_then_resolve(self):
        bare = self._bare()
        a = os.path.join(self.tmp, "A")
        repoA = make_repo(a, "Ana")
        write(os.path.join(a, "shared.txt"), "linha original\n")
        porcelain.add(repoA, [a])
        porcelain.commit(repoA, "base")
        porcelain.remote_add(repoA, "origin", bare)
        remote.push(repoA, "origin")

        b = os.path.join(self.tmp, "B")
        repoB, _ = remote.clone(bare, b)

        # mesma linha, mudancas diferentes
        write(os.path.join(a, "shared.txt"), "mudanca de A\n")
        porcelain.add(repoA, [a])
        porcelain.commit(repoA, "A edita")

        write(os.path.join(b, "shared.txt"), "mudanca de B\n")
        porcelain.add(repoB, [b])
        porcelain.commit(repoB, "B edita")
        remote.push(repoB, "origin")

        res = remote.pull(repoA, "origin")
        self.assertEqual(res["status"], "conflito")
        self.assertIn("shared.txt", res["conflicts"])
        conteudo = read(os.path.join(a, "shared.txt"))
        self.assertIn("<<<<<<<", conteudo)
        self.assertIn("mudanca de A", conteudo)
        self.assertIn("mudanca de B", conteudo)
        self.assertIsNotNone(repoA.read_merge_head())

        # resolve, adiciona, commita
        write(os.path.join(a, "shared.txt"), "resolvido juntando A e B\n")
        porcelain.add(repoA, [os.path.join(a, "shared.txt")])
        merge_commit = porcelain.commit(repoA, "resolve conflito")
        self.assertEqual(len(parse_commit(repoA, merge_commit)["parents"]), 2)
        self.assertIsNone(repoA.read_merge_head())

    def test_push_rejects_non_fastforward(self):
        bare = self._bare()
        a = os.path.join(self.tmp, "A")
        repoA = make_repo(a, "Ana")
        write(os.path.join(a, "x.txt"), "1\n")
        porcelain.add(repoA, [a])
        porcelain.commit(repoA, "c1")
        porcelain.remote_add(repoA, "origin", bare)
        remote.push(repoA, "origin")

        b = os.path.join(self.tmp, "B")
        repoB, _ = remote.clone(bare, b)
        write(os.path.join(b, "x.txt"), "1\n2\n")
        porcelain.add(repoB, [b])
        porcelain.commit(repoB, "b avanca")
        remote.push(repoB, "origin")

        # A avanca a partir de um estado antigo e tenta empurrar -> rejeitado
        write(os.path.join(a, "x.txt"), "1\nA\n")
        porcelain.add(repoA, [a])
        porcelain.commit(repoA, "a avanca")
        with self.assertRaises(Exception):
            remote.push(repoA, "origin")


class Locking(unittest.TestCase):
    def test_stale_lock_is_broken(self):
        from localhub.utils import FileLock

        tmp = tempfile.mkdtemp(prefix="lhub_lock_")
        try:
            target = os.path.join(tmp, "ref")
            orphan = target + ".lock"
            # simula um .lock orfao deixado por um processo que morreu
            with open(orphan, "w"):
                pass
            old = time.time() - 600
            os.utime(orphan, (old, old))
            # com stale curto, o lock orfao e quebrado e a aquisicao funciona
            with FileLock(target, timeout=2.0, stale=1.0):
                pass
            self.assertFalse(os.path.exists(orphan))
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


class Cron(unittest.TestCase):
    def test_matches_next_prev(self):
        from localhub.cron import CronExpr

        mon = datetime(2024, 1, 1, 7, 0)       # 2024-01-01 = segunda-feira
        self.assertEqual(mon.weekday(), 0)
        cx = CronExpr("0 7 * * 1-5")           # 07:00, seg-sex
        self.assertTrue(cx.matches(mon))
        self.assertFalse(cx.matches(datetime(2024, 1, 1, 7, 1)))
        sat = datetime(2024, 1, 6, 7, 0)       # sabado
        self.assertEqual(sat.weekday(), 5)
        self.assertFalse(cx.matches(sat))
        self.assertEqual(cx.next_after(mon), datetime(2024, 1, 2, 7, 0))
        self.assertEqual(cx.prev_at_or_before(datetime(2024, 1, 1, 7, 30)), mon)

    def test_step_field(self):
        from localhub.cron import CronExpr

        cx = CronExpr("*/15 * * * *")
        self.assertTrue(cx.matches(datetime(2026, 1, 1, 0, 0)))
        self.assertTrue(cx.matches(datetime(2026, 1, 1, 0, 15)))
        self.assertFalse(cx.matches(datetime(2026, 1, 1, 0, 16)))


class Monitoring(unittest.TestCase):
    def test_is_overdue(self):
        from localhub.monitor import is_overdue

        now = datetime(2026, 6, 18, 8, 0)
        expected = datetime(2026, 6, 18, 7, 0)
        self.assertTrue(is_overdue(expected, None, now, 5))                      # nunca rodou
        self.assertFalse(is_overdue(expected, datetime(2026, 6, 18, 7, 1), now, 5))  # rodou depois
        self.assertTrue(is_overdue(expected, datetime(2026, 6, 17, 7, 0), now, 5))   # so rodou antes
        self.assertFalse(is_overdue(expected, None, datetime(2026, 6, 18, 7, 3), 5))  # dentro da folga
        self.assertFalse(is_overdue(None, None, now, 5))                        # sem horario previsto

    def test_webhook_payload(self):
        from localhub.notify import _webhook_payload

        self.assertEqual(_webhook_payload("discord", "x"), {"content": "x"})
        self.assertEqual(_webhook_payload("slack", "x"), {"text": "x"})
        self.assertEqual(_webhook_payload("teams", "x"), {"text": "x"})
        self.assertEqual(_webhook_payload("json", "x"), {"message": "x"})


class SchedulerRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lhub_sched_")
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def _store(self):
        from localhub import scheduler

        return scheduler.Store(home=os.path.join(self.tmp, "home"))

    def test_run_executes_and_records(self):
        from localhub import scheduler

        proj = os.path.join(self.tmp, "proj")
        os.makedirs(proj)
        wf = scheduler.normalize_workflow(
            {"name": "demo", "python": sys.executable,
             "steps": [{"run": "{python} -c \"open('out.txt','w').write('ok')\""}]},
            proj,
        )
        store = self._store()
        rec = scheduler.Scheduler(store)._execute(wf, proj, "manual")
        self.assertEqual(rec["status"], "ok")
        self.assertTrue(os.path.exists(os.path.join(proj, "out.txt")))
        self.assertEqual(len(store.read_history()), 1)
        self.assertTrue(os.path.exists(rec["log"]))

    def test_failed_step_marks_failed(self):
        from localhub import scheduler

        proj = os.path.join(self.tmp, "proj")
        os.makedirs(proj)
        wf = scheduler.normalize_workflow(
            {"name": "demo", "python": sys.executable,
             "steps": [{"run": "{python} -c \"import sys; sys.exit(3)\""}]},
            proj,
        )
        rec = scheduler.Scheduler(self._store())._execute(wf, proj, "manual")
        self.assertEqual(rec["status"], "failed")
        self.assertEqual(rec["steps"][0]["exit"], 3)


class CliSmoke(unittest.TestCase):
    def test_cli_end_to_end(self):
        tmp = tempfile.mkdtemp(prefix="lhub_cli_")
        try:
            env = dict(os.environ)
            env["LHUB_AUTHOR_NAME"] = "CLI"
            env["LHUB_AUTHOR_EMAIL"] = "cli@test"
            # garante que o subprocesso ache o pacote mesmo sem 'pip install'
            proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            prev = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = proj_root + (os.pathsep + prev if prev else "")

            def run(*args):
                return subprocess.run(
                    [sys.executable, "-m", "localhub", *args],
                    cwd=tmp,
                    env=env,
                    capture_output=True,
                    text=True,
                )

            self.assertEqual(run("init").returncode, 0)
            write(os.path.join(tmp, "hello.txt"), "oi\n")
            self.assertEqual(run("add", "hello.txt").returncode, 0)
            r = run("commit", "-m", "via cli")
            self.assertEqual(r.returncode, 0, r.stderr)
            r = run("log", "--oneline")
            self.assertEqual(r.returncode, 0)
            self.assertIn("via cli", r.stdout)
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
