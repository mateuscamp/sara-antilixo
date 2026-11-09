"""Pastas da ~/Library que nunca são órfãs (AGENTS.md, regras de 2026-11-09).

`com.apple.*` fica fora daqui: a regra cobre o prefixo inteiro. Nome solto (Notion) vale só nas
pastas da ~/Library onde foi visto, para não isentar um app de terceiro com o mesmo nome em outra;
bundle id é único e vale em todas. Na dúvida, o nome fica de fora e o falso positivo vira só aviso.
Comparação sem diferenciar maiúsculas.
"""

from dataclasses import dataclass

# Onde apps desinstalados deixam dados com o nome do bundle id (medido em 2026-11-08).
PASTAS_DA_LIBRARY = (
    "Application Support",
    "Caches",
    "Containers",
    "Saved Application State",
    "HTTPStorages",
    "WebKit",
    "Logs",
)

_TODAS: frozenset[str] = frozenset()
_SUPORTE = frozenset({"Application Support"})
_CACHES = frozenset({"Caches"})
_LOGS = frozenset({"Logs"})


@dataclass(frozen=True, slots=True)
class Excecao:
    nome: str
    pastas: frozenset[str]  # pastas da ~/Library onde vale; vazio = todas
    motivo: str


EXCECOES_LIBRARY: tuple[Excecao, ...] = (
    # Com forma de bundle id (lista aprovada pela sessão-mãe em 2026-11-09).
    Excecao("com.crashlytics.data", _TODAS, "SDK de relatório de falha embutido em vários apps"),
    Excecao("com.plausiblelabs.crashreporter.data", _TODAS, "outro SDK de falha, compartilhado"),
    Excecao("org.swift.swiftpm", _TODAS, "toolchain de linha de comando (swift build), sem .app"),
    Excecao("com.google.Keystone", _TODAS, "atualizador compartilhado pelos apps do Google"),
    # Daemons e frameworks do macOS, sem .app, nas pastas onde foram vistos em 2026-11-09.
    Excecao("AddressBook", _SUPORTE, "Contatos"),
    Excecao("Animoji", _SUPORTE, "Memoji/Animoji do sistema"),
    Excecao("CallHistoryDB", _SUPORTE, "histórico de chamadas"),
    Excecao("CallHistoryTransactions", _SUPORTE, "transações do histórico de chamadas"),
    Excecao("CloudDocs", _SUPORTE, "iCloud Drive (bird)"),
    Excecao("CrashReporter", _SUPORTE | _LOGS, "relatórios de falha do sistema"),
    Excecao("DifferentialPrivacy", _SUPORTE, "telemetria com privacidade diferencial"),
    Excecao("DiskImages", _SUPORTE, "framework de imagens de disco"),
    Excecao("FileProvider", _SUPORTE, "framework File Provider (CloudStorage)"),
    Excecao("IntelligenceFlow", _SUPORTE, "Apple Intelligence"),
    Excecao("Knowledge", _SUPORTE, "knowledged, base de uso do sistema"),
    Excecao("SESStorage", _SUPORTE, "Secure Element (Apple Pay)"),
    Excecao("homeenergyd", _SUPORTE, "daemon do Casa"),
    Excecao("iCloud", _SUPORTE, "conta iCloud"),
    Excecao("icdd", _SUPORTE, "daemon de captura de imagem"),
    Excecao("locationaccessstored", _SUPORTE, "daemon de permissões de localização"),
    Excecao("networkserviceproxy", _SUPORTE, "proxy de rede do sistema (Private Relay)"),
    Excecao("AMSDataMigratorTool", _CACHES, "Apple Media Services"),
    Excecao("CloudKit", _CACHES, "framework CloudKit"),
    Excecao("FamilyCircle", _CACHES, "Compartilhamento Familiar"),
    Excecao("familycircled", _CACHES | {"HTTPStorages"}, "daemon do Compartilhamento Familiar"),
    Excecao("GameKit", _CACHES, "Game Center"),
    Excecao("GeoServices", _CACHES, "Mapas e localização do sistema"),
    Excecao("PassKit", _CACHES, "Wallet"),
    Excecao("softwareupdate", _CACHES | {"HTTPStorages"}, "atualização do macOS"),
    Excecao("Databases", frozenset({"WebKit"}), "armazenamento do próprio WebKit"),
    Excecao("Assistant", _LOGS, "Siri"),
    Excecao("Baseband", _LOGS, "modem"),
    Excecao("DiagnosticReports", _LOGS, "relatórios de diagnóstico do sistema"),
    Excecao("PrivacyPreservingMeasurement", _LOGS, "medição com privacidade"),
    Excecao("SiriTTSService", _LOGS, "voz da Siri"),
    # Ferramentas de linha de comando, sem .app.
    Excecao("Homebrew", _CACHES | _LOGS, "Caches/Homebrew é cache da allowlist; Logs, do brew"),
    Excecao("zoxide", _SUPORTE, "cd inteligente (CLI)"),
    Excecao("claude-cli-nodejs", _CACHES, "Claude Code (CLI)"),
)

_POR_NOME: dict[str, frozenset[str]] = {e.nome.casefold(): e.pastas for e in EXCECOES_LIBRARY}


def e_excecao(nome: str, pasta_da_library: str) -> bool:
    """Diz se a pasta `nome`, dentro de `~/Library/<pasta_da_library>`, nunca é órfã."""
    pastas = _POR_NOME.get(nome.casefold())
    if pastas is None:
        return False
    return not pastas or pasta_da_library in pastas
