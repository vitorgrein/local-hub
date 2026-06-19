"""LocalHub - um mini controle de versao local, em Python puro (sem git).

Armazena snapshots versionados numa pasta `.lhub/` usando objetos
enderecados por conteudo (SHA-256). Suporta commit/log/diff/branch e
sincronizacao entre maquinas via push/pull/clone usando uma pasta
compartilhada como "remoto".
"""

from .errors import LhubError
from .repository import Repo

__version__ = "0.2.0"
__all__ = ["Repo", "LhubError", "__version__"]
