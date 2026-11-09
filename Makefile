# Copiado da skill python-on-rails. `make check` é o portão: rode antes de dizer "pronto".
.PHONY: check rapido fmt test e2e

check:
	scripts/portao.sh

rapido:
	scripts/portao.sh --rapido

fmt:
	uv run --locked ruff format .
	uv run --locked ruff check --fix .

test:
	uv run --locked pytest -m "not e2e"

# Testes funcionais: fora do portão e do hook Stop; no CI e antes do commit que fecha a história.
e2e:
	uv run --locked pytest -m e2e
