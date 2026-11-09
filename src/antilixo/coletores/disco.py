"""Medidas de disco compartilhadas pelos coletores. Só lê; nunca apaga (ADR-0001)."""

import logging
import os
import stat
from pathlib import Path

_log = logging.getLogger(__name__)


def somar_tamanho(raiz: Path) -> int:
    """Soma o espaço ocupado por arquivos comuns sob `raiz`, sem seguir symlinks.

    Achado A4 de 2026-11-09: arquivos esparsos como Docker.raw e hardlinks inflavam
    o tamanho; por isso soma blocos alocados e conta cada inode uma vez por chamada.
    """
    total = 0
    vistos: set[tuple[int, int]] = set()
    for pasta, _subpastas, arquivos in raiz.walk():
        for nome in arquivos:
            try:
                info = (pasta / nome).lstat()
            except OSError:
                # O dono do cache pode apagar o arquivo entre a listagem e o lstat (achado A2
                # de 2026-11-09); sem permissão de busca dá o mesmo. Fica fora da soma.
                _log.debug("lstat falhou, arquivo fora da soma: %s", pasta / nome)
                continue
            if stat.S_ISREG(info.st_mode):
                inode = (info.st_dev, info.st_ino)
                if inode not in vistos:
                    vistos.add(inode)
                    total += info.st_blocks * 512
    return total


def medir_uso_do_disco(raiz: Path) -> int:
    """Bytes usados no volume que contém `raiz`, para o orçamento de >20 GB em 30 dias.

    `os.statvfs`, e não `shutil.disk_usage`: `shutil` é proibido fora de `acoes/` (ADR-0001).
    Mesma conta do `disk_usage` no POSIX: blocos totais menos livres, no tamanho do fragmento.
    """
    info = os.statvfs(raiz)
    return (info.f_blocks - info.f_bfree) * info.f_frsize
