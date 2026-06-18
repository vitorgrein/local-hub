"""Armazenamento de objetos enderecados por conteudo (blob / tree / commit).

Cada objeto e serializado como `b"<tipo> <tamanho>\\0<payload>"`, com hash
SHA-256 sobre esse conteudo, e gravado comprimido (zlib) em
`objects/<2 primeiros>/<resto>`. Igual em espirito ao git, formato proprio.
"""

import hashlib
import json
import os
import shutil
import zlib


def _object_path(repo, oid):
    return os.path.join(repo.objects_dir, oid[:2], oid[2:])


def hash_object(otype, data):
    header = ("%s %d" % (otype, len(data))).encode("utf-8")
    return hashlib.sha256(header + b"\x00" + data).hexdigest()


def has_object(repo, oid):
    return bool(oid) and os.path.exists(_object_path(repo, oid))


def write_object(repo, otype, data):
    """Grava um objeto (se ainda nao existir) e devolve seu oid."""
    oid = hash_object(otype, data)
    path = _object_path(repo, oid)
    if not os.path.exists(path):
        header = ("%s %d" % (otype, len(data))).encode("utf-8")
        payload = zlib.compress(header + b"\x00" + data, 6)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = "%s.tmp.%d" % (path, os.getpid())
        with open(tmp, "wb") as f:
            f.write(payload)
        os.replace(tmp, path)
    return oid


def read_object(repo, oid):
    """Devolve (tipo, payload_bytes) de um objeto armazenado."""
    path = _object_path(repo, oid)
    try:
        with open(path, "rb") as f:
            full = zlib.decompress(f.read())
    except FileNotFoundError:
        raise KeyError("objeto nao encontrado: %s" % oid)
    nul = full.index(b"\x00")
    otype = full[:nul].decode("utf-8").split(" ", 1)[0]
    return otype, full[nul + 1:]


def copy_object(src_repo, dst_repo, oid):
    """Copia o arquivo bruto do objeto entre repositorios (preserva o hash)."""
    dst = _object_path(dst_repo, oid)
    if os.path.exists(dst):
        return
    src = _object_path(src_repo, oid)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = "%s.tmp.%d" % (dst, os.getpid())
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


# --------------------------------------------------------------------- blob
def write_blob(repo, data):
    return write_object(repo, "blob", data)


def read_blob(repo, oid):
    otype, data = read_object(repo, oid)
    if otype != "blob":
        raise ValueError("esperava blob, veio %s" % otype)
    return data


# --------------------------------------------------------------------- tree
def make_tree(repo, entries):
    """`entries`: lista de dicts {name, type, mode, oid}. Devolve o oid."""
    norm = sorted(entries, key=lambda e: e["name"])
    data = json.dumps(norm, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return write_object(repo, "tree", data)


def parse_tree(repo, oid):
    otype, data = read_object(repo, oid)
    if otype != "tree":
        raise ValueError("esperava tree, veio %s" % otype)
    return json.loads(data.decode("utf-8"))


# ------------------------------------------------------------------- commit
def make_commit(repo, tree, parents, author, message, timestamp, tz_offset):
    obj = {
        "tree": tree,
        "parents": list(parents),
        "author_name": author[0],
        "author_email": author[1],
        "timestamp": int(timestamp),
        "tz_offset": int(tz_offset),
        "message": message,
    }
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return write_object(repo, "commit", data)


def parse_commit(repo, oid):
    otype, data = read_object(repo, oid)
    if otype != "commit":
        raise ValueError("esperava commit, veio %s" % otype)
    return json.loads(data.decode("utf-8"))
