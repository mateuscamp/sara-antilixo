"""Pastas da ~/Library com forma de bundle id que nunca são órfãs (AGENTS.md, regras de 2026-11-09).

`com.apple.*` fica fora desta lista: a regra cobre o prefixo inteiro. Item novo leva o porquê.
Lista proposta à sessão-mãe em 2026-11-09.
"""

EXCECOES_LIBRARY: frozenset[str] = frozenset(
    {
        # SDK de relatório de falha embutido em vários apps; não é de um app só.
        "com.crashlytics.data",
        "com.plausiblelabs.crashreporter.data",
        # Toolchain de linha de comando (swift build), sem .app correspondente.
        "org.swift.swiftpm",
        # Atualizador compartilhado pelos apps do Google; fica enquanto houver um deles.
        "com.google.Keystone",
    }
)
