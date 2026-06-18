"""Leitura da arvore de trabalho: status e checkout (materializar uma tree)."""

import os

from .ignore import is_ignored, load_rules
from .index import flatten_tree
from .objects import hash_object, parse_commit, read_blob


def iter_files(repo):
    """Gera os caminhos relativos ('/') de todos os arquivos nao ignorados."""
    rules = load_rules(repo.root)
    for dirpath, dirnames, files in os.walk(repo.root):
        rel_dir = os.path.relpath(dirpath, repo.root).replace("\\", "/")
        prefix = "" if rel_dir == "." else rel_dir + "/"
        dirnames[:] = [d for d in dirnames if not is_ignored(prefix + d, True, rules)]
        for fn in files:
            rel = prefix + fn
            if not is_ignored(rel, False, rules):
                yield rel


def _head_tree_flat(repo):
    head = repo.resolve_head()
    if not head:
        return {}
    return flatten_tree(repo, parse_commit(repo, head)["tree"])


def _working_oid(repo, relpath):
    with open(repo.workpath(relpath), "rb") as f:
        return hash_object("blob", f.read())


def compute_status(repo):
    """Devolve um dicionario com mudancas staged, unstaged e nao rastreadas."""
    head = _head_tree_flat(repo)
    index = repo.read_index()
    work = set(iter_files(repo))

    staged = {}
    for path in set(index) | set(head):
        in_index = path in index
        in_head = path in head
        if in_index and not in_head:
            staged[path] = "novo"
        elif in_index and in_head and index[path]["oid"] != head[path]["oid"]:
            staged[path] = "modificado"
        elif in_head and not in_index:
            staged[path] = "removido"

    unstaged = {}
    for path, meta in index.items():
        wp = repo.workpath(path)
        if not os.path.exists(wp):
            unstaged[path] = "removido"
            continue
        st = os.stat(wp)
        if st.st_size == meta.get("size") and st.st_mtime == meta.get("mtime"):
            continue
        if _working_oid(repo, path) != meta["oid"]:
            unstaged[path] = "modificado"

    untracked = sorted(work - set(index))
    return {
        "branch": repo.current_branch(),
        "detached": repo.current_branch() is None,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "merging": repo.read_merge_head() is not None,
    }


def has_local_changes(repo):
    """True se ha mudancas staged ou unstaged (ignora arquivos nao rastreados)."""
    st = compute_status(repo)
    return bool(st["staged"] or st["unstaged"])


def _prune_empty_dirs(repo):
    for dirpath, dirnames, files in os.walk(repo.root, topdown=False):
        if os.path.abspath(dirpath) == repo.root:
            continue
        rel = os.path.relpath(dirpath, repo.root).replace("\\", "/")
        if rel.split("/")[0] in (".lhub", ".git"):
            continue
        if not os.listdir(dirpath):
            try:
                os.rmdir(dirpath)
            except OSError:
                pass


def checkout_tree(repo, tree_oid):
    """Materializa uma tree no diretorio de trabalho e reescreve o index.

    Remove arquivos rastreados que nao existem na tree alvo, grava/atualiza os
    arquivos da tree e reconstroi o index com base no resultado.
    """
    target = flatten_tree(repo, tree_oid) if tree_oid else {}
    current = repo.read_index()

    for path in current:
        if path not in target:
            try:
                os.remove(repo.workpath(path))
            except OSError:
                pass

    new_index = {}
    for path, meta in target.items():
        wp = repo.workpath(path)
        os.makedirs(os.path.dirname(wp), exist_ok=True) if os.path.dirname(wp) else None
        with open(wp, "wb") as f:
            f.write(read_blob(repo, meta["oid"]))
        st = os.stat(wp)
        new_index[path] = {
            "oid": meta["oid"],
            "size": st.st_size,
            "mtime": st.st_mtime,
            "mode": meta.get("mode", "100644"),
        }
    repo.write_index(new_index)
    _prune_empty_dirs(repo)
