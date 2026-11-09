"""Pastas da ~/Library que nunca são órfãs (AGENTS.md, regras de 2026-11-09).

Vale para nome com forma de bundle id e para nome solto (Notion). `com.apple.*` fica fora daqui:
a regra cobre o prefixo inteiro. Cada item leva o porquê; na dúvida, o nome fica de fora e o
falso positivo vira só aviso. Comparação sem diferenciar maiúsculas.
"""

EXCECOES_LIBRARY: frozenset[str] = frozenset(
    {
        # --- Com forma de bundle id (lista aprovada pela sessão-mãe em 2026-11-09) ---
        "com.crashlytics.data",  # SDK de relatório de falha embutido em vários apps
        "com.plausiblelabs.crashreporter.data",  # idem, outro SDK de falha
        "org.swift.swiftpm",  # toolchain de linha de comando (swift build), sem .app
        "com.google.Keystone",  # atualizador compartilhado pelos apps do Google
        # --- Daemons e frameworks do macOS, sem .app (vistos na ~/Library em 2026-11-09) ---
        "AddressBook",  # Contatos
        "Animoji",  # Memoji/Animoji do sistema
        "CallHistoryDB",  # histórico de chamadas
        "CallHistoryTransactions",  # idem, transações do histórico
        "CloudDocs",  # iCloud Drive (bird)
        "CrashReporter",  # relatórios de falha do sistema
        "DifferentialPrivacy",  # telemetria com privacidade diferencial
        "DiskImages",  # framework de imagens de disco
        "FileProvider",  # framework File Provider (CloudStorage)
        "IntelligenceFlow",  # Apple Intelligence
        "Knowledge",  # knowledged, base de uso do sistema
        "SESStorage",  # Secure Element (Apple Pay)
        "homeenergyd",  # daemon do Casa
        "iCloud",  # conta iCloud
        "icdd",  # daemon de captura de imagem
        "locationaccessstored",  # daemon de permissões de localização
        "networkserviceproxy",  # proxy de rede do sistema (iCloud Private Relay)
        "AMSDataMigratorTool",  # Apple Media Services
        "CloudKit",  # framework CloudKit
        "FamilyCircle",  # Compartilhamento Familiar
        "familycircled",  # idem, o daemon
        "GameKit",  # Game Center
        "GeoServices",  # Mapas/localização do sistema
        "PassKit",  # Wallet
        "softwareupdate",  # atualização do macOS
        "Databases",  # WebKit/Databases, armazenamento do próprio WebKit
        "Assistant",  # Siri
        "Baseband",  # modem (Logs)
        "DiagnosticReports",  # relatórios de diagnóstico do sistema (Logs)
        "PrivacyPreservingMeasurement",  # medição com privacidade (Logs)
        "SiriTTSService",  # voz da Siri (Logs)
        "FaceTime",  # app de /System/Applications, fora das pastas_de_apps
        # --- Ferramentas de linha de comando, sem .app ---
        "Homebrew",  # Caches/Homebrew é cache da allowlist; Logs/Homebrew, logs do brew
        "zoxide",  # cd inteligente (CLI)
        "claude-cli-nodejs",  # Claude Code (CLI)
    }
)
