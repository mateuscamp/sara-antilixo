#!/usr/bin/env bash
# Instala o sara-antilixo: `git clone` + `./install.sh` (ADR-0001, driver "sobreviver à formatação").
# Idempotente: rodar de novo deixa o plist e o ~/.zshrc iguais. Compatível com o bash 3.2 do macOS.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
rotulo="com.mateuscamp.sara-antilixo"
estado="$HOME/.local/state/sara-antilixo"
plist="$HOME/Library/LaunchAgents/$rotulo.plist"
zshrc="$HOME/.zshrc"
inicio_bloco="# >>> sara-antilixo >>>"
fim_bloco="# <<< sara-antilixo <<<"
# Casam a linha do marcador mesmo com espaço, tab ou \r no fim (editor, CRLF): sem isso, um
# marcador assim não seria visto e o install.sh acrescentaria um segundo bloco. Os marcadores não
# têm caractere especial de ERE.
padrao_inicio="^$inicio_bloco[[:space:]]*\$"
padrao_fim="^$fim_bloco[[:space:]]*\$"

# Cópia de trabalho do ~/.zshrc. Global para o trap: se o script abortar no meio (disco cheio,
# ~/.zshrc só leitura), ela não fica esquecida no TMPDIR.
temporario=""
limpar_temporario() {
  [[ -z "$temporario" ]] || rm -f -- "$temporario"
}
trap limpar_temporario EXIT

# Troca toda ocorrência de $2 por $3 em $1. Sem ${x//a/b}: no bash 5.2 o `&` da troca vira o trecho
# casado, e um caminho com `&` sairia corrompido.
substituir() {
  local texto="$1" marca="$2" valor="$3" saida=""
  while [[ "$texto" == *"$marca"* ]]; do
    saida+="${texto%%"$marca"*}$valor"
    texto="${texto#*"$marca"}"
  done
  printf '%s' "$saida$texto"
}

escapar_xml() {
  local texto
  texto="$(substituir "$1" '&' '&amp;')"
  texto="$(substituir "$texto" '<' '&lt;')"
  substituir "$texto" '>' '&gt;'
}

garantir_uv() {
  command -v uv > /dev/null && return 0
  if ! command -v brew > /dev/null; then
    # Não baixa instalador por conta própria: rodar script da internet é decisão do usuário.
    cat >&2 << 'FIM'
install.sh: falta o uv, e o Homebrew para instalá-lo.
Instale o Homebrew seguindo https://brew.sh, abra um terminal novo (para o brew entrar no PATH)
e rode ./install.sh de novo.
FIM
    exit 1
  fi
  brew install uv
}

escrever_plist() {
  local conteudo
  conteudo="$(< "$repo/instalacao/$rotulo.plist")"
  conteudo="$(substituir "$conteudo" '@UV@' "$(escapar_xml "$uv")")"
  conteudo="$(substituir "$conteudo" '@REPO@' "$(escapar_xml "$repo")")"
  conteudo="$(substituir "$conteudo" '@LOG@' "$(escapar_xml "$estado/launchd.log")")"
  mkdir -p "$(dirname "$plist")" "$estado"
  printf '%s\n' "$conteudo" > "$plist"
}

recarregar_agente() {
  local dominio
  dominio="gui/$(id -u)"
  # Falha quando o agente não estava carregado (primeira instalação): não é erro.
  launchctl bootout "$dominio/$rotulo" 2> /dev/null || true
  # O bootout termina de forma assíncrona; o bootstrap logo depois às vezes falha com
  # "Bootstrap failed: 5: Input/output error". Tenta de novo antes de desistir.
  local tentativa
  for tentativa in 1 2 3; do
    launchctl bootstrap "$dominio" "$plist" && return 0
    [[ "$tentativa" == 3 ]] || sleep 1
  done
  # Para antes do ~/.zshrc: o heartbeat só entra quando o agente que ele vigia está carregado.
  echo "install.sh: o launchctl bootstrap falhou 3 vezes para $plist." \
    "Veja 'launchctl print $dominio/$rotulo' e rode ./install.sh de novo." >&2
  exit 1
}

# Confere os marcadores antes de mexer em qualquer coisa: com um marcador sem par, fora de ordem ou
# repetido, trocar o bloco apagaria linhas do usuário. Nesse caso para e deixa o conserto para ele.
conferir_marcadores() {
  [[ -f "$zshrc" ]] || return 0
  local inicios fins
  inicios="$(grep -nE "$padrao_inicio" "$zshrc" | cut -d: -f1 | tr '\n' ' ' || true)"
  fins="$(grep -nE "$padrao_fim" "$zshrc" | cut -d: -f1 | tr '\n' ' ' || true)"
  [[ -z "$inicios" && -z "$fins" ]] && return 0
  # Um número de linha só em cada (o espaço final vem do tr) e o início antes do fim.
  if [[ "$inicios" =~ ^[0-9]+\ $ && "$fins" =~ ^[0-9]+\ $ ]] && ((${inicios% } < ${fins% })); then
    return 0
  fi
  echo "install.sh: marcadores do sara-antilixo quebrados em $zshrc" \
    "(início nas linhas: ${inicios:-nenhuma}; fim nas linhas: ${fins:-nenhuma})." \
    "Esperado: um '$inicio_bloco' antes de um '$fim_bloco'. Conserte à mão e rode de novo." >&2
  exit 1
}

# Põe o heartbeat no ~/.zshrc entre os marcadores, trocando o bloco anterior no mesmo lugar.
# Escreve por cima com `cat >`, e não com `mv`: um ~/.zshrc que é symlink (dotfiles) continua symlink.
escrever_bloco_zshrc() {
  local bloco
  bloco="$inicio_bloco"$'\n'"$(< "$repo/instalacao/heartbeat.zsh")"$'\n'"$fim_bloco"
  touch "$zshrc"
  # Com modelo explícito: o mktemp do macOS sem argumento ignora o TMPDIR.
  temporario="$(mktemp "${TMPDIR:-/tmp}/sara-antilixo-zshrc.XXXXXX")"
  if grep -qE "$padrao_inicio" "$zshrc"; then
    INICIO="$inicio_bloco" FIM="$fim_bloco" BLOCO="$bloco" awk '
      # A mesma classe do grep acima: com classes diferentes, um marcador visto por um e não pelo
      # outro deixaria o bloco velho no lugar sem aviso.
      { linha = $0; sub(/[[:space:]]+$/, "", linha) }
      linha == ENVIRON["INICIO"] { print ENVIRON["BLOCO"]; pulando = 1; next }
      linha == ENVIRON["FIM"] { pulando = 0; next }
      !pulando { print }
    ' "$zshrc" > "$temporario"
  else
    cat "$zshrc" > "$temporario"
    # Arquivo sem quebra de linha no fim: o marcador grudaria na última linha do usuário.
    [[ -s "$zshrc" && -n "$(tail -c 1 "$zshrc")" ]] && printf '\n' >> "$temporario"
    printf '%s\n' "$bloco" >> "$temporario"
  fi
  cat "$temporario" > "$zshrc"
}

conferir_marcadores
garantir_uv
# Não resolve o symlink do Homebrew: /opt/homebrew/bin/uv sobrevive ao `brew upgrade`, o caminho
# dentro do Cellar não.
uv="$(command -v uv)"
# Antes do agente: o primeiro domingo não pode encontrar o ambiente por montar.
uv sync --locked --project "$repo"
escrever_plist
recarregar_agente
escrever_bloco_zshrc
