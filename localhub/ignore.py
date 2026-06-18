"""Suporte a .gitignore (e .lhubignore) com a semantica do git.

Regras suportadas: comentarios (#), linhas em branco, negacao (!),
padroes so-de-diretorio (barra no fim), ancoragem (barra no inicio/meio),
curingas * ? [...], globstar ** e arquivos .gitignore aninhados por pasta.
A ultima regra que casa decide; uma negacao nao reinclui algo dentro de uma
pasta ja excluida (mesma limitacao do git).
"""

import os
import re

from .utils import read_text

# Metadados que nunca sao rastreados.
ALWAYS_IGNORE = {".lhub", ".git"}
IGNORE_FILES = (".gitignore", ".lhubignore")


class Rule:
    __slots__ = ("base", "negation", "dir_only", "anchored", "regex")

    def __init__(self, base, negation, dir_only, anchored, regex):
        self.base = base          # pasta (relativa a raiz) do .gitignore que originou a regra
        self.negation = negation  # padrao com '!'
        self.dir_only = dir_only  # padrao terminado em '/'
        self.anchored = anchored  # padrao com '/' (casa caminho completo, nao so o nome)
        self.regex = regex


def _translate(pattern):
    """Traduz um glob estilo gitignore para um corpo de regex (sem ^ $)."""
    out = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                i += 2
                if i < n and pattern[i] == "/":
                    i += 1
                    out.append("(?:.*/)?")  # **/  -> zero ou mais diretorios
                else:
                    out.append(".*")        # ** ao final / antes de nao-barra
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            j = i + 1
            if j < n and pattern[j] in ("!", "^"):
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j >= n:
                out.append("\\[")
                i += 1
            else:
                cls = pattern[i + 1:j]
                if cls.startswith("!"):
                    cls = "^" + cls[1:]
                out.append("[" + cls + "]")
                i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def _compile_line(line, base):
    if not line.strip() or line.lstrip().startswith("#"):
        return None
    s = line
    negation = False
    if s.startswith("\\#") or s.startswith("\\!"):
        s = s[1:]
    elif s.startswith("!"):
        negation = True
        s = s[1:]
    s = re.sub(r"(?<!\\)\s+$", "", s)  # remove espacos finais nao escapados
    if not s:
        return None
    dir_only = s.endswith("/")
    if dir_only:
        s = s[:-1]
    anchored = "/" in s
    if s.startswith("/"):
        s = s[1:]
    if not s:
        return None
    regex = re.compile("^" + _translate(s) + "$")
    return Rule(base, negation, dir_only, anchored, regex)


def load_rules(root):
    """Coleta as regras de todos os .gitignore/.lhubignore (raiz e subpastas)."""
    rules = []
    for dirpath, dirnames, files in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        dirnames[:] = [d for d in dirnames if d not in ALWAYS_IGNORE]
        for ign in IGNORE_FILES:
            if ign in files:
                txt = read_text(os.path.join(dirpath, ign)) or ""
                if txt[:1] == chr(0xFEFF):  # ignora BOM UTF-8 (como o git faz)
                    txt = txt[1:]
                for line in txt.splitlines():
                    rule = _compile_line(line, rel_dir)
                    if rule:
                        rules.append(rule)
    return rules


def _decide(rule, subpath, is_dir):
    """True (ignora), False (reinclui) ou None (nao se aplica) para um caminho."""
    base = rule.base
    if base:
        if subpath == base:
            rel = ""
        elif subpath.startswith(base + "/"):
            rel = subpath[len(base) + 1:]
        else:
            return None
    else:
        rel = subpath
    if not rel:
        return None
    if rule.dir_only and not is_dir:
        return None
    target = rel if rule.anchored else rel.rsplit("/", 1)[-1]
    if rule.regex.match(target):
        return not rule.negation
    return None


def is_ignored(relpath, is_dir, rules):
    """Decide se um caminho (relativo, com '/') deve ser ignorado."""
    parts = relpath.split("/")
    if any(p in ALWAYS_IGNORE for p in parts):
        return True

    ignored = False
    for i in range(len(parts)):
        sub = "/".join(parts[: i + 1])
        sub_is_dir = True if i < len(parts) - 1 else is_dir
        decision = None
        for rule in rules:
            d = _decide(rule, sub, sub_is_dir)
            if d is not None:
                decision = d  # ultima regra que casa vence
        if decision is True:
            ignored = True
        elif decision is False and not ignored:
            # reinclui apenas se nenhum ancestral ja estava excluido
            ignored = False
    return ignored
