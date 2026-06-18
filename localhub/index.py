"""Area de staging (index) e conversao entre index <-> arvore (tree)."""

import os

from .errors import LhubError
from .ignore import is_ignored, load_rules
from .objects import make_tree, parse_tree, write_blob


def _rel(repo, path):
    """Caminho relativo a raiz do repo, normalizado com '/'."""
    abspath = os.path.abspath(path)
    try:
        rel = os.path.relpath(abspath, repo.root)
    except ValueError:
        # Windows: caminho em outra unidade (ex.: D:\ com repo em C:\)
        raise LhubError("caminho fora do repositorio: %s" % path)
    if rel.startswith(".."):
        raise LhubError("caminho fora do repositorio: %s" % path)
    return rel.replace("\\", "/")


def _stage_file(repo, index, rel):
    with open(repo.workpath(rel), "rb") as f:
        data = f.read()
    oid = write_blob(repo, data)
    st = os.stat(repo.workpath(rel))
    index[rel] = {
        "oid": oid,
        "size": st.st_size,
        "mtime": st.st_mtime,
        "mode": "100644",
    }


def _iter_dir(repo, abspath, rules):
    """Gera caminhos relativos nao ignorados sob uma pasta."""
    for dirpath, dirnames, files in os.walk(abspath):
        dirnames[:] = [
            d
            for d in dirnames
            if not is_ignored(_rel(repo, os.path.join(dirpath, d)), True, rules)
        ]
        for fn in files:
            rel = _rel(repo, os.path.join(dirpath, fn))
            if not is_ignored(rel, False, rules):
                yield rel


def add_paths(repo, paths, force=False):
    """Adiciona arquivos/pastas ao index, respeitando .gitignore/.lhubignore.

    Devolve (staged, ignorados). Arquivos ignorados so entram com force=True.
    """
    rules = load_rules(repo.root)
    index = repo.read_index()
    staged = []
    ignored = []
    for p in paths:
        abspath = os.path.abspath(p)
        if not os.path.exists(abspath):
            # permite "remover" do index um arquivo que sumiu do disco
            rel = _rel(repo, abspath)
            if rel in index:
                del index[rel]
                staged.append(rel)
                continue
            raise LhubError("caminho nao encontrado: %s" % p)
        if os.path.isfile(abspath):
            rel = _rel(repo, abspath)
            if not force and is_ignored(rel, False, rules):
                ignored.append(rel)
                continue
            _stage_file(repo, index, rel)
            staged.append(rel)
        else:
            for rel in _iter_dir(repo, abspath, rules):
                _stage_file(repo, index, rel)
                staged.append(rel)
    repo.write_index(index)
    return staged, ignored


def remove_paths(repo, paths, from_disk=False):
    index = repo.read_index()
    removed = []
    for p in paths:
        rel = _rel(repo, p)
        matched = [k for k in index if k == rel or k.startswith(rel + "/")]
        if not matched:
            raise LhubError("nao esta rastreado: %s" % p)
        for k in matched:
            del index[k]
            removed.append(k)
            if from_disk:
                try:
                    os.remove(repo.workpath(k))
                except OSError:
                    pass
    repo.write_index(index)
    return removed


def write_tree_from_index(repo, index):
    """Constroi as trees aninhadas a partir do index plano e devolve a raiz."""
    root = {}
    for path, meta in index.items():
        parts = path.split("/")
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = {"__blob__": meta["oid"], "__mode__": meta.get("mode", "100644")}

    def write_node(node):
        entries = []
        for name, val in node.items():
            if "__blob__" in val:
                entries.append(
                    {
                        "name": name,
                        "type": "blob",
                        "mode": val["__mode__"],
                        "oid": val["__blob__"],
                    }
                )
            else:
                entries.append(
                    {
                        "name": name,
                        "type": "tree",
                        "mode": "040000",
                        "oid": write_node(val),
                    }
                )
        return make_tree(repo, entries)

    return write_node(root)


def flatten_tree(repo, tree_oid, prefix=""):
    """Achata uma tree em {caminho: {'oid':..., 'mode':...}}."""
    result = {}
    if not tree_oid:
        return result
    for entry in parse_tree(repo, tree_oid):
        path = prefix + entry["name"]
        if entry["type"] == "blob":
            result[path] = {"oid": entry["oid"], "mode": entry["mode"]}
        else:
            result.update(flatten_tree(repo, entry["oid"], path + "/"))
    return result
