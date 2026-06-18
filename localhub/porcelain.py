"""Operacoes de alto nivel usadas pela CLI (init, add, commit, log, ...)."""

import os

from . import worktree
from .diffmerge import diff_trees, unified_from_bytes
from .errors import LhubError
from .history import walk_history
from .index import add_paths, remove_paths, write_tree_from_index
from .objects import hash_object, make_commit, parse_commit, read_blob
from .repository import Repo, read_global_config, write_global_config
from .utils import now_with_tz


# --------------------------------------------------------------------- init
def init(path, bare=False):
    return Repo.init(path, bare=bare)


# ------------------------------------------------------------------- config
def config_set(repo, key, value, glob=False):
    cfg = read_global_config() if glob else repo.read_config()
    parts = key.split(".")
    node = cfg
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    if glob:
        write_global_config(cfg)
    else:
        repo.write_config(cfg)


def config_list(repo, glob=False):
    flat = {}

    def walk(prefix, obj):
        for k, v in obj.items():
            key = "%s.%s" % (prefix, k) if prefix else k
            if isinstance(v, dict):
                walk(key, v)
            else:
                flat[key] = v

    walk("", read_global_config() if glob else repo.read_config())
    return flat


# ------------------------------------------------------------- add / rm
def add(repo, paths, force=False):
    return add_paths(repo, paths, force=force)


def rm(repo, paths, from_disk=False):
    return remove_paths(repo, paths, from_disk=from_disk)


# ------------------------------------------------------------------- status
def status(repo):
    return worktree.compute_status(repo)


# ------------------------------------------------------------------- commit
def commit(repo, message, author=None, allow_empty=False):
    index = repo.read_index()
    tree = write_tree_from_index(repo, index)
    head = repo.resolve_head()
    merge_head = repo.read_merge_head()

    parents = []
    if head:
        parents.append(head)
    if merge_head:
        parents.append(merge_head)

    if head and not merge_head and not allow_empty:
        if parse_commit(repo, head)["tree"] == tree:
            raise LhubError("nada para commitar (use 'lhub add' ou --allow-empty)")

    name, email = author or repo.get_author()
    ts, tz = now_with_tz()
    oid = make_commit(repo, tree, parents, (name, email), message, ts, tz)

    branch = repo.current_branch()
    if branch:
        repo.write_ref("refs/heads/%s" % branch, oid)
    else:
        repo.write_head(oid)
    repo.clear_merge_head()
    return oid


# ---------------------------------------------------------------------- log
def log(repo, max_count=None):
    head = repo.resolve_head()
    if not head:
        return []
    out = []
    for i, (oid, c) in enumerate(walk_history(repo, head)):
        if max_count is not None and i >= max_count:
            break
        out.append((oid, c))
    return out


def show(repo, rev="HEAD"):
    oid = repo.resolve(rev)
    if not oid:
        raise LhubError("revisao desconhecida: %s" % rev)
    commit = parse_commit(repo, oid)
    parent_tree = (
        parse_commit(repo, commit["parents"][0])["tree"] if commit["parents"] else None
    )
    chunks = []
    for path, _status, oa, ob in diff_trees(repo, parent_tree, commit["tree"]):
        a = read_blob(repo, oa) if oa else b""
        b = read_blob(repo, ob) if ob else b""
        chunks.append(unified_from_bytes(path, a, b))
    return oid, commit, "".join(chunks)


# --------------------------------------------------------------------- diff
def diff(repo, staged=False, rev_a=None, rev_b=None):
    chunks = []
    if rev_a or rev_b:
        ta = parse_commit(repo, repo.resolve(rev_a))["tree"] if rev_a else None
        tb = parse_commit(repo, repo.resolve(rev_b))["tree"] if rev_b else None
        for path, _s, oa, ob in diff_trees(repo, ta, tb):
            a = read_blob(repo, oa) if oa else b""
            b = read_blob(repo, ob) if ob else b""
            chunks.append(unified_from_bytes(path, a, b))
        return "".join(chunks)

    head = repo.resolve_head()
    head_tree = parse_commit(repo, head)["tree"] if head else None

    if staged:
        itree = write_tree_from_index(repo, repo.read_index())
        for path, _s, oa, ob in diff_trees(repo, head_tree, itree):
            a = read_blob(repo, oa) if oa else b""
            b = read_blob(repo, ob) if ob else b""
            chunks.append(unified_from_bytes(path, a, b))
        return "".join(chunks)

    # nao-staged: index vs arquivos do disco
    for path, meta in sorted(repo.read_index().items()):
        wp = repo.workpath(path)
        a = read_blob(repo, meta["oid"])
        if os.path.exists(wp):
            with open(wp, "rb") as f:
                b = f.read()
            if hash_object("blob", b) == meta["oid"]:
                continue
        else:
            b = b""
        chunks.append(unified_from_bytes(path, a, b))
    return "".join(chunks)


# ------------------------------------------------------------------ branches
def branch_list(repo):
    return repo.list_branches(), repo.current_branch()


def branch_create(repo, name):
    if repo.read_ref("refs/heads/%s" % name):
        raise LhubError("a branch ja existe: %s" % name)
    start = repo.resolve_head()
    if not start:
        raise LhubError("ainda nao ha commits para iniciar uma branch")
    repo.write_ref("refs/heads/%s" % name, start)


def branch_delete(repo, name):
    if name == repo.current_branch():
        raise LhubError("nao da para apagar a branch em uso: %s" % name)
    if not repo.read_ref("refs/heads/%s" % name):
        raise LhubError("a branch nao existe: %s" % name)
    repo.delete_ref("refs/heads/%s" % name)


def checkout(repo, target, create=False, force=False):
    if create:
        branch_create(repo, target)
        repo.write_head("ref: refs/heads/%s" % target)
        return {"branch": target, "created": True}

    is_branch = repo.read_ref("refs/heads/%s" % target) is not None
    oid = repo.resolve(target)
    if not oid:
        raise LhubError("alvo desconhecido: %s" % target)
    if not force and worktree.has_local_changes(repo):
        raise LhubError(
            "ha alteracoes nao commitadas; faca commit ou use --force para descartar"
        )
    worktree.checkout_tree(repo, parse_commit(repo, oid)["tree"])
    if is_branch:
        repo.write_head("ref: refs/heads/%s" % target)
    else:
        repo.write_head(oid)
    return {"branch": target if is_branch else None, "oid": oid, "detached": not is_branch}


# ------------------------------------------------------------------- remotes
def remote_add(repo, name, url):
    cfg = repo.read_config()
    cfg.setdefault("remotes", {})[name] = {"url": os.path.abspath(url)}
    repo.write_config(cfg)


def remote_list(repo):
    return repo.read_config().get("remotes", {})
