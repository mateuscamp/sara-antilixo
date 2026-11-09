"""Medidas de disco compartilhadas pelos coletores. Só lê; nunca apaga (ADR-0001)."""

import os
import stat
from pathlib import Path


def somar_tamanho(raiz: Path) -> int:
    """Soma o tamanho dos arquivos comuns sob `raiz`, sem seguir symlinks."""
    total = 0
    for pasta, _subpastas, arquivos in raiz.walk():
        for nome in arquivos:
            info = (pasta / nome).lstat()
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
    return total


def medir_uso_do_disco(raiz: Path) -> int:
    """Bytes usados no volume que contém `raiz`, para o orçamento de >20 GB em 30 dias.

    `os.statvfs`, e não `shutil.disk_usage`: `shutil` é proibido fora de `acoes/` (ADR-0001).
    Mesma conta do `disk_usage` no POSIX: blocos totais menos livres, no tamanho do fragmento.
    """
    info = os.statvfs(raiz)
    return (info.f_blocks - info.f_bfree) * info.f_frsize
