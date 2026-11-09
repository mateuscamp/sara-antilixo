# sara-antilixo

Detecta lixo acumulado no Mac, avisa toda semana e só apaga caches recriáveis da allowlist.
Arquitetura: script local, LaunchAgent semanal · Quantum: 1. ADRs em `docs/adr/`.

## Comandos

- Portão: `make check` (lock, juiz, ruff, basedpyright, import-linter, pytest, uv audit). Rode
  antes de dizer "pronto" e mostre a saída. O hook Stop roda o mesmo.
- Só os testes: `make test`. Formatar: `make fmt`.
- A suíte inteira roda em <10 s e nunca toca o HOME real: todo caminho entra como parâmetro
  (`home: Path`), e o teste usa `tmp_path`.
- Commit só quando o humano pedir.

## Segurança da limpeza (ADR-0001)

- Só `src/antilixo/acoes/` apaga. Fora dele, importar `shutil` reprova (import-linter).
  `Path.unlink`/`rmdir`/`os.remove` fora dele são proibidos, mas ainda sem checagem automática
  (`test_so_acoes_apaga_arquivos`, pendente): confira no diff.
- `acoes/` só apaga caminho que, resolvido (`..` e symlinks seguidos), fica dentro de um item da
  allowlist em `dominio/`. Fora disso: `ForaDaAllowlistError`, e nada é apagado.
- Allowlist fechada: caches do npm, uv, Homebrew e Gradle. Item novo exige ADR.
- Limpeza automática no máximo uma vez por mês. O resto é aviso.
- Repo com commit sem push, stash ou arquivo modificado nunca é alvo, nem de aviso de "apagar".
- O Claude lê o relatório; nunca executa limpeza nem chama `acoes/` fora de teste.

## Regras do domínio (decididas em 2026-11-09)

- Aviso: quando a soma de uma categoria passa de 2 GB. O relatório lista os itens dela.
- Notificação: achado já avisado só volta a notificar se crescer ≥20% desde o último aviso.
  Continua no relatório toda semana. O estado guarda o tamanho no momento do aviso.
- Órfão da `~/Library`: bundle id da pasta sem app correspondente em `/Applications` ou
  `~/Applications` (lido de `Contents/Info.plist` com `plistlib`). Pastas do sistema
  (`com.apple.*` e a lista de exceções em `dominio/`) nunca são órfãs.
- Regra que não está aqui nem no ADR: perguntar, não inferir.

## Contextos e fronteiras

| Pasta | Papel | Padrão | Testes |
|---|---|---|---|
| `dominio/` | núcleo: allowlist, classificação apagar/avisar/ignorar | funções puras, dataclasses | unidade, sem disco |
| `coletores/` | varrem o disco, devolvem `Achado` | funções que recebem `home: Path` | `tmp_path` |
| `acoes/` | único lugar que apaga | transaction script | `tmp_path` |
| `relatorio/` | Markdown e notificação via `osascript` | transaction script | `tmp_path`, `osascript` fake |

- `dominio/` não importa `coletores/`, `acoes/`, `relatorio/`, `os`, `shutil`, `subprocess`.
- `coletores/`, `dominio/`, `relatorio/` não importam `acoes/` nem `shutil`.
- Estado em `~/.local/state/sara-antilixo/`. Nada em outro lugar.
- Pasta nova ou dependência de produção (fora da stdlib) exige ADR antes do código.

## Ciclo de mudança (TDD)

1. Vermelho: um teste, um comportamento, nomeado pelo comportamento. Rodar e ver falhar NA
   ASSERÇÃO. `ImportError`/`NameError`/fixture quebrada não conta.
2. Verde: o mínimo que passa, sem editar o teste. Rodar a suíte inteira.
3. Refatorar com a suíte verde. Depois `make check`.

- Antes de pedir commit, erro deliberado: troque a implementação por uma versão errada plausível.
  Se nenhum teste falha, falta teste.
- Bug: primeiro o teste que reproduz, visto falhando; depois o fix.
- O relatório mostra a linha de falha do vermelho e o resumo do verde.
- Proibido para ficar verde: mudar asserção, `skip`/`xfail`, apagar ou renomear teste, asserção
  mais fraca, mockar o sujeito sob teste, `try/except` no teste, `sleep`.
  Teste estava errado? Diga no relatório e volte ao vermelho.

## Revisão antes do commit

- Todo diff: code-audit em modo auditoria (confere o vermelho numa cópia descartável).
- Diff que toca `acoes/`, `dominio/` ou a allowlist: antes, `/code-review high` (nível explícito).
- Achado não se corrige sem o sim do humano.

## Python

- Ambiente: `uv`. Dependência de dev com `uv add --dev`, nunca `pip install`. Produção: só stdlib.
- Proibido mexer em `[tool.ruff]`, `[tool.basedpyright]`, `[tool.pytest]`, `[tool.importlinter]`,
  `[tool.trilhos]`, `scripts/portao.sh`, `Makefile`, hooks e CI, criar `ruff.toml`,
  `pyrightconfig.json` ou `pytest.ini`, ou acrescentar ignore/exclude/linha de base. Regra parece
  errada? Diga no relatório e pare.
- `trilhos: pare` ou achado `[humano]`: não conserte, não crie ADR, não edite o registro de
  desvios. Relate e pare.
- Supressão só com regra e motivo na mesma linha:
  `# pyright: ignore[reportX]  # motivo: <por quê>` · `# noqa: S603  # motivo: <por quê>`.
- Toda função anotada. Sem `Any`. Miolo em `@dataclass(frozen=True, slots=True)`; nada de `dict`
  solto atravessando funções.
- Exceção própria com sufixo `Error`, com o valor recebido e o esperado na mensagem. Sem
  `except Exception`, sem `except: pass`. Relançar com `raise ... from erro`.
- `logging.getLogger(__name__)`; `print` só na CLI.
- Fake de borda (relógio, disco, `osascript`) é classe tipada injetada. `Mock` reprova no portão.

## Comentários

- Não apagar comentários de proveniência (ADR, bug, limitação upstream) em refactor.
- Escrever o porquê, não o quê.

## Estrutura

```
src/antilixo/
  dominio/      allowlist, classificação (núcleo, puro)
  coletores/    varredura → Achado
  acoes/        único lugar que apaga
  relatorio/    Markdown + osascript
tests/<pasta>/test_<modulo>.py
docs/adr/       decisões
scripts/        portão e hook
```
