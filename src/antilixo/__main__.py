"""`python -m antilixo`: o que o LaunchAgent roda todo domingo às 10h (ADR-0001).

Só monta o ambiente real (HOME, relógio local, apps instalados, osascript) e chama `executar`.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

from antilixo.execucao import Ambiente, executar
from antilixo.relatorio.notificacao import ExecutorDeSubprocesso


def main() -> int:
    # A saída vai para ~/.local/state/sara-antilixo/launchd.log (StandardErrorPath do plist).
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    home = Path.home()
    executar(
        Ambiente(
            home=home,
            agora=datetime.now().astimezone(),
            # /System/Applications: sem ela, apps do sistema viram órfãos falsos (revisão de
            # 2026-11-09 dos coletores de disco).
            pastas_de_apps=(
                Path("/Applications"),
                home / "Applications",
                Path("/System/Applications"),
            ),
            executor=ExecutorDeSubprocesso(),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
