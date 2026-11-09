# Heartbeat do sara-antilixo, posto pelo install.sh entre os marcadores. Edite no repositório.
# O launchd não roda com o Mac desligado (ADR-0001): avisa ao abrir o terminal quando o último
# relatório sumiu ou tem mais de 8 dias. Zsh puro, sem processo novo: abrir o terminal segue rápido.
() {
  # Opções do zsh padrão só aqui dentro: setopt do usuário não muda o glob abaixo.
  emulate -L zsh
  # N: vazio, sem erro, se o arquivo não existir. `.`: arquivo comum. mh-192: modificado há menos
  # de 192 horas (8 dias).
  local -a recente=("${HOME}"/.local/state/sara-antilixo/relatorio.md(N.mh-192))
  (( ${#recente} )) && return 0
  print -u2 "sara-antilixo: nenhum relatório nos últimos 8 dias" \
    "(~/.local/state/sara-antilixo/relatorio.md). Veja ~/.local/state/sara-antilixo/launchd.log" \
    "e 'launchctl print gui/$(id -u)/com.mateuscamp.sara-antilixo'."
  return 0
}
