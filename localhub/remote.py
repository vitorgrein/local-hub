"""Sincronizacao entre repositorios: clone, fetch, push e pull.

O "remoto" e simplesmente outra pasta com um repositorio LocalHub (de
preferencia *bare*), que pode estar num drive de rede ou pasta compartilhada.
"""

import os

from . import worktree
from .diffmerge import merge_trees
from .errors import LhubError
from .history import is_ancestor, merge_base, missing_objects, reachable_objects
from .index import write_tree_from_index
from .objects import copy_object, has_object, make_commit, parse_commit
from .repository import Repo
from .utils import FileLock, now_with_tz


def _remote_url(repo, remote):
    cfg = repo.read_config()
    entry = cfg.get("remotes", {}).get(remote)
    if not entry:
        raise LhubError("remoto desconhecido: %s (use 'lhub remote add')" % remote)
    return entry["url"]


def _default_branch(repo):
    head = repo.read_head_raw()
    prefix = "ref: refs/heads/"
    if head.startswith(prefix):
        return head[len(prefix):]
    return repo.read_config().get("default_branch", "main")


# -------------------------------------------------------------------- clone
def clone(src_url, dst_path):
    src = Repo.open_any(src_url)
    dst_path = os.path.abspath(dst_path)
    if os.path.isdir(dst_path) and os.listdir(dst_path):
        raise LhubError("o diretorio destino nao esta vazio: %s" % dst_path)

    dst = Repo.init(dst_path, bare=False)
    heads = {n: o for n, o in src.list_branches().items() if o}
    for oid in reachable_objects(src, list(heads.values())):
        copy_object(src, dst, oid)

    for name, oid in heads.items():
        dst.write_ref("refs/remotes/origin/%s" % name, oid)

    default = _default_branch(src)
    cfg = dst.read_config()
    cfg.setdefault("remotes", {})["origin"] = {"url": os.path.abspath(src_url)}
    cfg["default_branch"] = default
    dst.write_config(cfg)

    if heads.get(default):
        dst.write_ref("refs/heads/%s" % default, heads[default])
        dst.write_head("ref: refs/heads/%s" % default)
        worktree.checkout_tree(dst, parse_commit(dst, heads[default])["tree"])
    else:
        dst.write_head("ref: refs/heads/%s" % default)
    return dst, default


# -------------------------------------------------------------------- fetch
def fetch(repo, remote="origin"):
    src = Repo.open_any(_remote_url(repo, remote))
    updated = {}
    for name, oid in src.list_branches().items():
        if not oid:
            continue
        for need in missing_objects(src, repo, [oid]):
            copy_object(src, repo, need)
        ref = "refs/remotes/%s/%s" % (remote, name)
        old = repo.read_ref(ref)
        repo.write_ref(ref, oid)
        if old != oid:
            updated[name] = (old, oid)
    return updated


def _check_fast_forward(repo, remote_tip, local_tip, force):
    if force or not remote_tip or remote_tip == local_tip:
        return
    if not has_object(repo, remote_tip):
        raise LhubError("o remoto tem commits que voce nao possui; rode 'lhub pull' antes")
    if not is_ancestor(repo, remote_tip, local_tip):
        raise LhubError(
            "push rejeitado (nao e fast-forward); rode 'lhub pull' antes ou use --force"
        )


# --------------------------------------------------------------------- push
def push(repo, remote="origin", branch=None, force=False):
    branch = branch or repo.current_branch()
    if not branch:
        raise LhubError("HEAD destacado: informe a branch a enviar")
    local_tip = repo.read_ref("refs/heads/%s" % branch)
    if not local_tip:
        raise LhubError("a branch local nao tem commits: %s" % branch)

    url = _remote_url(repo, remote)
    dst = Repo.open_any(url)
    ref = "refs/heads/%s" % branch

    # validacao previa (rapida) antes de transferir objetos
    _check_fast_forward(repo, dst.read_ref(ref), local_tip, force)

    for need in missing_objects(repo, dst, [local_tip]):
        copy_object(repo, dst, need)

    # revalida sob lock: evita que dois analistas enviando ao mesmo tempo
    # sobrescrevam o commit um do outro no repositorio de rede
    with FileLock(dst._ref_file(ref)):
        current = dst.read_ref(ref)
        _check_fast_forward(repo, current, local_tip, force)
        dst.write_ref(ref, local_tip)

    repo.write_ref("refs/remotes/%s/%s" % (remote, branch), local_tip)
    return {
        "branch": branch,
        "old": current,
        "new": local_tip,
        "remote": remote,
        "url": url,
        "up_to_date": current == local_tip,
    }


# --------------------------------------------------------------------- pull
def pull(repo, remote="origin", branch=None):
    fetch(repo, remote)
    branch = branch or repo.current_branch()
    if not branch:
        raise LhubError("HEAD destacado: informe a branch a atualizar")

    remote_tip = repo.read_ref("refs/remotes/%s/%s" % (remote, branch))
    if not remote_tip:
        return {"status": "sem-remoto", "branch": branch}

    local_tip = repo.read_ref("refs/heads/%s" % branch)

    if not local_tip:
        repo.write_ref("refs/heads/%s" % branch, remote_tip)
        worktree.checkout_tree(repo, parse_commit(repo, remote_tip)["tree"])
        return {"status": "criado", "branch": branch, "new": remote_tip}

    if local_tip == remote_tip:
        return {"status": "atualizado", "branch": branch}

    if is_ancestor(repo, remote_tip, local_tip):
        return {"status": "a-frente", "branch": branch}

    if worktree.has_local_changes(repo):
        raise LhubError("ha alteracoes locais nao commitadas; faca commit antes do pull")

    if is_ancestor(repo, local_tip, remote_tip):
        # fast-forward
        repo.write_ref("refs/heads/%s" % branch, remote_tip)
        worktree.checkout_tree(repo, parse_commit(repo, remote_tip)["tree"])
        return {
            "status": "fast-forward",
            "branch": branch,
            "old": local_tip,
            "new": remote_tip,
        }

    # historias divergentes -> merge 3-vias
    base = merge_base(repo, local_tip, remote_tip)
    base_tree = parse_commit(repo, base)["tree"] if base else None
    ours_tree = parse_commit(repo, local_tip)["tree"]
    theirs_tree = parse_commit(repo, remote_tip)["tree"]

    merged, conflicts = merge_trees(repo, base_tree, ours_tree, theirs_tree)
    merged_tree = write_tree_from_index(
        repo, {p: {"oid": m["oid"], "mode": m.get("mode", "100644")} for p, m in merged.items()}
    )
    worktree.checkout_tree(repo, merged_tree)

    if conflicts:
        repo.write_merge_head(remote_tip)
        return {
            "status": "conflito",
            "branch": branch,
            "conflicts": sorted(conflicts),
            "remote_tip": remote_tip,
        }

    name, email = repo.get_author()
    ts, tz = now_with_tz()
    message = "Merge de %s/%s" % (remote, branch)
    coid = make_commit(
        repo, merged_tree, [local_tip, remote_tip], (name, email), message, ts, tz
    )
    repo.write_ref("refs/heads/%s" % branch, coid)
    return {"status": "merge", "branch": branch, "old": local_tip, "new": coid}
