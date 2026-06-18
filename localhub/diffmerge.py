"""Diffs entre trees/blobs e merge 3-vias (estilo diff3) em nivel de linha."""

import difflib

from .index import flatten_tree
from .objects import read_blob, write_blob


# ----------------------------------------------------------------- diffs
def diff_trees(repo, tree_a, tree_b):
    """Lista (caminho, status, oid_a, oid_b); status: added/deleted/modified."""
    fa = flatten_tree(repo, tree_a) if tree_a else {}
    fb = flatten_tree(repo, tree_b) if tree_b else {}
    changes = []
    for path in sorted(set(fa) | set(fb)):
        oa = fa.get(path, {}).get("oid")
        ob = fb.get(path, {}).get("oid")
        if oa == ob:
            continue
        if oa is None:
            changes.append((path, "added", None, ob))
        elif ob is None:
            changes.append((path, "deleted", oa, None))
        else:
            changes.append((path, "modified", oa, ob))
    return changes


def unified_from_bytes(path, a, b, a_label="a", b_label="b"):
    """Diff unificado entre dois conteudos (bytes). Avisa se for binario."""
    try:
        at = a.decode("utf-8")
        bt = b.decode("utf-8")
    except UnicodeDecodeError:
        return "diff binario diferente: %s\n" % path
    la = at.splitlines(keepends=True)
    lb = bt.splitlines(keepends=True)
    diff = difflib.unified_diff(
        la, lb, fromfile="%s/%s" % (a_label, path), tofile="%s/%s" % (b_label, path)
    )
    out = "".join(diff)
    if out and not out.endswith("\n"):
        out += "\n"
    return out


# -------------------------------------------------------------- merge 3-vias
def _matched_map(base, other):
    """Mapa indice_base -> indice_other das linhas iguais (blocos casados)."""
    sm = difflib.SequenceMatcher(a=base, b=other, autojunk=False)
    mapping = {}
    for ai, bi, size in sm.get_matching_blocks():
        for k in range(size):
            mapping[ai + k] = bi + k
    return mapping


def merge3(base, ours, theirs, label_ours="NOSSO", label_theirs="REMOTO"):
    """Merge 3-vias de listas de linhas. Devolve (linhas, houve_conflito)."""
    mo = _matched_map(base, ours)
    mt = _matched_map(base, theirs)
    sync_points = sorted(i for i in mo if i in mt)

    result = []
    conflict = False
    base_i = ours_i = theirs_i = 0

    for s in sync_points + [len(base)]:
        o_end = mo.get(s, len(ours))
        t_end = mt.get(s, len(theirs))
        base_chunk = base[base_i:s]
        ours_chunk = ours[ours_i:o_end]
        theirs_chunk = theirs[theirs_i:t_end]

        if ours_chunk == theirs_chunk:
            result.extend(ours_chunk)
        elif ours_chunk == base_chunk:
            result.extend(theirs_chunk)
        elif theirs_chunk == base_chunk:
            result.extend(ours_chunk)
        else:
            conflict = True
            result.append("<<<<<<< %s\n" % label_ours)
            result.extend(ours_chunk)
            if result and not result[-1].endswith("\n"):
                result[-1] += "\n"
            result.append("=======\n")
            result.extend(theirs_chunk)
            if result and not result[-1].endswith("\n"):
                result[-1] += "\n"
            result.append(">>>>>>> %s\n" % label_theirs)

        if s < len(base):
            result.append(ours[mo[s]])  # linha de sincronizacao (igual nos 3)
            base_i = s + 1
            ours_i = mo[s] + 1
            theirs_i = mt[s] + 1

    return result, conflict


def try_merge_blob(repo, base_oid, ours_oid, theirs_oid):
    """Tenta mesclar tres blobs por linha. Devolve (bytes, houve_conflito)."""
    def load(oid):
        return read_blob(repo, oid) if oid else b""

    base_b, ours_b, theirs_b = load(base_oid), load(ours_oid), load(theirs_oid)
    try:
        bt = base_b.decode("utf-8")
        ot = ours_b.decode("utf-8")
        tt = theirs_b.decode("utf-8")
    except UnicodeDecodeError:
        # binario: nao da pra mesclar -> conflito, mantem o nosso
        return ours_b, True

    merged, conflict = merge3(
        bt.splitlines(keepends=True),
        ot.splitlines(keepends=True),
        tt.splitlines(keepends=True),
    )
    return "".join(merged).encode("utf-8"), conflict


def merge_trees(repo, base_tree, ours_tree, theirs_tree):
    """Merge 3-vias de trees. Devolve ({caminho: {oid, mode}}, lista_conflitos)."""
    base = flatten_tree(repo, base_tree) if base_tree else {}
    ours = flatten_tree(repo, ours_tree) if ours_tree else {}
    theirs = flatten_tree(repo, theirs_tree) if theirs_tree else {}

    result = {}
    conflicts = []
    for path in sorted(set(base) | set(ours) | set(theirs)):
        bo = base.get(path, {}).get("oid")
        oo = ours.get(path, {}).get("oid")
        to = theirs.get(path, {}).get("oid")
        mode = (
            ours.get(path) or theirs.get(path) or base.get(path) or {}
        ).get("mode", "100644")

        if oo == to:
            if oo:
                result[path] = {"oid": oo, "mode": mode}
        elif oo == bo:
            if to:
                result[path] = {"oid": to, "mode": mode}
        elif to == bo:
            if oo:
                result[path] = {"oid": oo, "mode": mode}
        elif oo is None or to is None:
            # um lado apagou, o outro modificou -> conflito
            conflicts.append(path)
            result[path] = {"oid": oo or to, "mode": mode}
        else:
            merged_bytes, had_conflict = try_merge_blob(repo, bo, oo, to)
            result[path] = {"oid": write_blob(repo, merged_bytes), "mode": mode}
            if had_conflict:
                conflicts.append(path)

    return result, conflicts
