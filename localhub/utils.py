"""Utilitarios: escrita atomica, lock de arquivo e funcoes de tempo."""

import os
import time


def read_text(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return default


def atomic_write_bytes(path, data):
    """Escreve em arquivo temporario e renomeia (troca atomica)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_text(path, text):
    atomic_write_bytes(path, text.encode("utf-8"))


def now_with_tz():
    """Retorna (epoch_segundos, offset_minutos) do horario local."""
    ts = int(time.time())
    lt = time.localtime(ts)
    if lt.tm_isdst and time.daylight:
        offset_sec = -time.altzone
    else:
        offset_sec = -time.timezone
    return ts, offset_sec // 60


def format_time(ts, tz_minutes):
    """Formata um instante para exibicao, ex: 2026-06-17 14:30:00 -0300."""
    sign = "+" if tz_minutes >= 0 else "-"
    hh = abs(tz_minutes) // 60
    mm = abs(tz_minutes) % 60
    shown = time.gmtime(ts + tz_minutes * 60)
    return "%s %s%02d%02d" % (
        time.strftime("%Y-%m-%d %H:%M:%S", shown),
        sign,
        hh,
        mm,
    )


class FileLock:
    """Lock cooperativo simples baseado em arquivo .lock (best-effort).

    Se um processo morrer segurando o lock, o arquivo .lock fica orfao. Como o
    lock so e mantido por um instante (a atualizacao de uma ref), qualquer .lock
    mais antigo que `stale` segundos e tratado como abandonado e removido.
    """

    def __init__(self, target_path, timeout=15.0, stale=120.0):
        self.lock_path = target_path + ".lock"
        self.timeout = timeout
        self.stale = stale
        self._fd = None

    def _break_if_stale(self):
        """Remove o lock se ele estiver claramente abandonado (orfao)."""
        try:
            age = time.time() - os.path.getmtime(self.lock_path)
        except OSError:
            return  # sumiu sozinho; o proximo O_EXCL decide o vencedor
        if age > self.stale:
            try:
                os.remove(self.lock_path)
            except OSError:
                pass

    def __enter__(self):
        parent = os.path.dirname(self.lock_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        start = time.time()
        while True:
            try:
                self._fd = os.open(
                    self.lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR
                )
                return self
            except FileExistsError:
                self._break_if_stale()
                if time.time() - start > self.timeout:
                    raise TimeoutError(
                        "nao foi possivel obter o lock: %s" % self.lock_path
                    )
                time.sleep(0.05)

    def __exit__(self, *exc):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            os.remove(self.lock_path)
        except OSError:
            pass
