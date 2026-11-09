#!/usr/bin/env bash
# Portão único do projeto Python: o mesmo comando para o agente, o hook Stop e o CI.
# Aprova só se tudo passar; a primeira etapa que reprova encerra com a saída dela.
#   scripts/portao.sh            completo (make check e CI)
#   scripts/portao.sh --rapido   sem a auditoria de dependências, que precisa de rede (hook Stop)
# Copiado da skill python-on-rails.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
rapido=false
[[ "${1:-}" == "--rapido" ]] && rapido=true

etapa() { printf '\n== %s\n' "$1"; }

etapa "lock em dia com o pyproject"
uv lock --check

etapa "trilhos"
# O juiz fica fora do projeto, na pasta da skill: não há cópia para editar nem etapa em bash para
# calar. Ele confere supressões, configuração paralela e todo afrouxamento do portão. Sem ele o
# portão não aprova. O CI baixa o mesmo script numa versão fixa (assets/ci.yml). O caminho vai
# inteiro na linha que executa: o juiz recusa a chamada por variável, que se troca sem ler.
if [[ ! -f "$HOME/.claude/skills/python-on-rails/scripts/conferir_trilho.py" ]]; then
  echo "Falta o conferir_trilho: instale a skill python-on-rails. O portão não aprova sem ele."
  exit 2
fi
uv run --locked python -I "$HOME/.claude/skills/python-on-rails/scripts/conferir_trilho.py"

etapa "formatação"
uv run --locked ruff format --check .

etapa "lint"
uv run --locked ruff check .

etapa "tipos"
uv run --locked basedpyright

if grep -q '^\[tool.importlinter\]' pyproject.toml; then
  etapa "fronteiras"
  uv run --locked lint-imports
fi

etapa "testes"
# Os funcionais (`e2e`) ficam no `make e2e`: navegador deixaria o hook Stop lento demais.
uv run --locked pytest -m "not e2e"

if ! $rapido; then
  etapa "dependências com vulnerabilidade conhecida"
  uv audit --locked --preview-features audit
fi

printf '\nPortão aprovado.\n'
