"""
Logger centralizado do APEX Manager.
Uso: from app.logger import logger
Saída: console (WARNING+) + arquivo logs/apex.log (INFO+) com rotação de 5MB.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

# Diretório de logs na raiz do projeto (fora de backend/)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOG_DIR = os.path.join(_ROOT, "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

logger = logging.getLogger("apex")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    _fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(module)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Arquivo: INFO+ com rotação 5MB, mantém 3 backups
    _fh = RotatingFileHandler(
        os.path.join(_LOG_DIR, "apex.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    _fh.setLevel(logging.INFO)
    _fh.setFormatter(_fmt)

    # Console: WARNING+ (não polui o terminal durante dev)
    _ch = logging.StreamHandler()
    _ch.setLevel(logging.WARNING)
    _ch.setFormatter(_fmt)

    logger.addHandler(_fh)
    logger.addHandler(_ch)
