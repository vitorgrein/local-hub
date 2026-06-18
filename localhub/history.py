"""Percurso do grafo de commits: ancestrais, merge-base e objetos faltantes."""

import heapq

from .objects import has_object, parse_commit, parse_tree


def walk_history(repo, oid):
    """Gera (oid, commit) do mais novo para o mais antigo (por timestamp)."""
    seen = set()
    heap = []

    def push(o):
        if o and o not in seen:
            seen.add(o)
            commit = parse_commit(repo, o)
            heapq.heappush(heap, (-commit["timestamp"], o, commit))

    push(oid)
    while heap:
        _, o, commit = heapq.heappop(heap)
        yield o, commit
        for parent in commit["parents"]:
            push(parent)


def ancestors(repo, oid):
    """Conjunto de todos os commits alcancaveis a partir de `oid` (inclui ele)."""
    result = set()
    stack = [oid] if oid else []
    while stack:
        o = stack.pop()
        if o in result:
            continue
        result.add(o)
        for parent in parse_commit(repo, o)["parents"]:
            if parent not in result:
                stack.append(parent)
    return result


def is_ancestor(repo, ancestor, descendant):
    """True se `ancestor` esta na historia de `descendant`."""
    if not ancestor:
        return True
    if not descendant:
        return False
    if ancestor == descendant:
        return True
    return ancestor in ancestors(repo, descendant)


def merge_base(repo, a, b):
    """Ancestral comum mais recente (LCA) entre dois commits."""
    if not a or not b:
        return None
    common = ancestors(repo, a) & ancestors(repo, b)
    if not common:
        return None
    lowest = set(common)
    for c in common:
        for parent in parse_commit(repo, c)["parents"]:
            # remove ancestrais proprios de c que tambem sao comuns
            lowest -= (ancestors(repo, parent) & common)
    if not lowest:
        lowest = common
    return max(lowest, key=lambda o: parse_commit(repo, o)["timestamp"])


# ---------------------------------------------------------------- objetos
def _collect_tree(repo, tree_oid, into):
    if not tree_oid or tree_oid in into:
        return
    into.add(tree_oid)
    for entry in parse_tree(repo, tree_oid):
        if entry["type"] == "tree":
            _collect_tree(repo, entry["oid"], into)
        else:
            into.add(entry["oid"])


def reachable_objects(repo, tips):
    """Todos os oids (commit/tree/blob) alcancaveis a partir dos commits `tips`."""
    seen = set()
    stack = [t for t in tips if t]
    while stack:
        o = stack.pop()
        if o in seen:
            continue
        seen.add(o)
        commit = parse_commit(repo, o)
        _collect_tree(repo, commit["tree"], seen)
        stack.extend(p for p in commit["parents"] if p not in seen)
    return seen


def _need_tree(src, dst, tree_oid, need):
    if not tree_oid or tree_oid in need:
        return
    if has_object(dst, tree_oid):
        return  # destino ja tem a tree (e, por invariante, o que ela referencia)
    need.add(tree_oid)
    for entry in parse_tree(src, tree_oid):
        if entry["type"] == "tree":
            _need_tree(src, dst, entry["oid"], need)
        elif not has_object(dst, entry["oid"]):
            need.add(entry["oid"])


def missing_objects(src, dst, tips):
    """Oids presentes em `src` e ausentes em `dst`, alcancaveis a partir de tips.

    Poda a busca em commits/trees ja presentes no destino (push/fetch incremental).
    """
    need = set()
    visited = set()
    stack = [t for t in tips if t]
    while stack:
        o = stack.pop()
        if o in visited:
            continue
        visited.add(o)
        if has_object(dst, o):
            continue
        need.add(o)
        commit = parse_commit(src, o)
        _need_tree(src, dst, commit["tree"], need)
        stack.extend(commit["parents"])
    return need
