"""Repo: localiza/cria o repositorio e gerencia config, HEAD, refs e index."""

import json
import os

from .errors import LhubError
from .utils import atomic_write_text, read_text

LHUB_DIR = ".lhub"


def global_config_path():
    """Config por maquina/usuario: ~/.lhubconfig.json (identidade do analista)."""
    return os.path.join(os.path.expanduser("~"), ".lhubconfig.json")


def read_global_config():
    txt = read_text(global_config_path())
    return json.loads(txt) if txt else {}


def write_global_config(cfg):
    atomic_write_text(global_config_path(), json.dumps(cfg, ensure_ascii=False, indent=2))


class Repo:
    """Representa um repositorio LocalHub (normal ou bare)."""

    def __init__(self, root, bare=False):
        self.root = os.path.abspath(root)
        self.bare = bare
        self.lhub_dir = self.root if bare else os.path.join(self.root, LHUB_DIR)

    # ------------------------------------------------------------------ paths
    @property
    def objects_dir(self):
        return os.path.join(self.lhub_dir, "objects")

    @property
    def refs_dir(self):
        return os.path.join(self.lhub_dir, "refs")

    @property
    def config_path(self):
        return os.path.join(self.lhub_dir, "config.json")

    @property
    def index_path(self):
        return os.path.join(self.lhub_dir, "index.json")

    @property
    def head_path(self):
        return os.path.join(self.lhub_dir, "HEAD")

    @property
    def merge_head_path(self):
        return os.path.join(self.lhub_dir, "MERGE_HEAD")

    def workpath(self, relpath):
        """Converte um caminho rastreado ('a/b.txt') em caminho do SO."""
        return os.path.join(self.root, *relpath.split("/"))

    # --------------------------------------------------------------- ciclo de vida
    @classmethod
    def init(cls, path, bare=False):
        repo = cls(path, bare=bare)
        os.makedirs(repo.objects_dir, exist_ok=True)
        os.makedirs(os.path.join(repo.refs_dir, "heads"), exist_ok=True)
        os.makedirs(os.path.join(repo.refs_dir, "remotes"), exist_ok=True)
        if not os.path.exists(repo.head_path):
            repo.write_head("ref: refs/heads/main")
        if not os.path.exists(repo.config_path):
            repo.write_config(
                {
                    "core": {"bare": bare},
                    "user": {},
                    "remotes": {},
                    "default_branch": "main",
                }
            )
        if not bare and not os.path.exists(repo.index_path):
            repo.write_index({})
        return repo

    @classmethod
    def find(cls, start=None, required=True):
        """Sobe na arvore de diretorios procurando uma pasta .lhub."""
        cur = os.path.abspath(start or os.getcwd())
        while True:
            if os.path.isdir(os.path.join(cur, LHUB_DIR)):
                return cls(cur)
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        if required:
            raise LhubError(
                "nao e um repositorio LocalHub (pasta .lhub nao encontrada)"
            )
        return None

    @classmethod
    def open_any(cls, path):
        """Abre um repositorio normal ou bare a partir de um caminho."""
        path = os.path.abspath(path)
        if os.path.isdir(os.path.join(path, LHUB_DIR)):
            return cls(path, bare=False)
        if os.path.isdir(os.path.join(path, "objects")) and os.path.exists(
            os.path.join(path, "HEAD")
        ):
            return cls(path, bare=True)
        raise LhubError("repositorio LocalHub nao encontrado em: %s" % path)

    # ----------------------------------------------------------------- config
    def read_config(self):
        txt = read_text(self.config_path)
        return json.loads(txt) if txt else {}

    def write_config(self, cfg):
        atomic_write_text(self.config_path, json.dumps(cfg, ensure_ascii=False, indent=2))

    def get_author(self):
        # precedencia: config do repo -> config global (por maquina) -> env -> usuario do SO
        user = self.read_config().get("user", {})
        guser = read_global_config().get("user", {})
        name = (
            user.get("name")
            or guser.get("name")
            or os.environ.get("LHUB_AUTHOR_NAME")
            or os.environ.get("USERNAME")
            or os.environ.get("USER")
            or "Usuario LocalHub"
        )
        email = (
            user.get("email")
            or guser.get("email")
            or os.environ.get("LHUB_AUTHOR_EMAIL")
            or "usuario@localhub"
        )
        return name, email

    # ------------------------------------------------------------------- HEAD
    def write_head(self, content):
        if not content.endswith("\n"):
            content += "\n"
        atomic_write_text(self.head_path, content)

    def read_head_raw(self):
        return (read_text(self.head_path) or "").strip()

    def current_branch(self):
        head = self.read_head_raw()
        prefix = "ref: refs/heads/"
        if head.startswith(prefix):
            return head[len(prefix):]
        return None

    def resolve_head(self):
        """Retorna o oid do commit apontado por HEAD (ou None se nao houver)."""
        head = self.read_head_raw()
        if head.startswith("ref: "):
            return self.read_ref(head[5:])
        return head or None

    # ------------------------------------------------------------------- refs
    def _ref_file(self, name):
        return os.path.join(self.lhub_dir, *name.split("/"))

    def read_ref(self, name):
        return (read_text(self._ref_file(name)) or "").strip() or None

    def write_ref(self, name, oid):
        atomic_write_text(self._ref_file(name), oid + "\n")

    def delete_ref(self, name):
        try:
            os.remove(self._ref_file(name))
        except FileNotFoundError:
            pass

    def list_refs(self, prefix):
        base = self._ref_file(prefix)
        result = {}
        if not os.path.isdir(base):
            return result
        for dirpath, _dirs, files in os.walk(base):
            for fn in files:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, base).replace("\\", "/")
                result[rel] = (read_text(full) or "").strip()
        return result

    def list_branches(self):
        return self.list_refs("refs/heads")

    # ----------------------------------------------------------------- MERGE_HEAD
    def read_merge_head(self):
        return (read_text(self.merge_head_path) or "").strip() or None

    def write_merge_head(self, oid):
        atomic_write_text(self.merge_head_path, oid + "\n")

    def clear_merge_head(self):
        try:
            os.remove(self.merge_head_path)
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------------ index
    def read_index(self):
        txt = read_text(self.index_path)
        return json.loads(txt) if txt else {}

    def write_index(self, index):
        atomic_write_text(
            self.index_path,
            json.dumps(index, ensure_ascii=False, sort_keys=True, indent=0),
        )

    # --------------------------------------------------------------- resolucao
    def resolve(self, rev):
        """Resolve 'HEAD', nome de branch, 'origin/x' ou um oid para um commit."""
        from .objects import has_object  # import tardio evita ciclo

        if rev in (None, "HEAD"):
            return self.resolve_head()
        ref = self.read_ref("refs/heads/%s" % rev)
        if ref:
            return ref
        if "/" in rev:
            ref = self.read_ref("refs/remotes/%s" % rev)
            if ref:
                return ref
        low = rev.lower()
        if len(low) >= 4 and all(c in "0123456789abcdef" for c in low):
            if len(low) == 64 and has_object(self, low):
                return low
            match = self._match_short_oid(low)
            if match:
                return match
        return None

    def _match_short_oid(self, prefix):
        sub = os.path.join(self.objects_dir, prefix[:2])
        if not os.path.isdir(sub):
            return None
        rest = prefix[2:]
        hits = [fn for fn in os.listdir(sub) if fn.startswith(rest)]
        if len(hits) == 1:
            return prefix[:2] + hits[0]
        return None

    def __repr__(self):
        kind = "bare" if self.bare else "normal"
        return "<Repo %s (%s)>" % (self.root, kind)
