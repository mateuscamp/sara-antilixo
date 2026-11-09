# sara-antilixo

Detecta lixo acumulado no Mac (dados de apps desinstalados na `~/Library`, restos de build em
projetos parados, `.git` fora de `~/dev`, biblioteca do Fotos presa no iCloud, caches) e avisa
toda semana. Só apaga sozinho caches recriáveis de uma allowlist fechada (npm, uv, Homebrew,
Gradle), no máximo uma vez por mês. O resto é aviso. Decisão e motivos em
[`docs/adr/0001-detector-local-com-allowlist.md`](docs/adr/0001-detector-local-com-allowlist.md).

## Instalar

Precisa do [Homebrew](https://brew.sh); o `install.sh` instala o `uv` por ele se faltar.

```bash
git clone <url-do-repo> ~/dev/sara-antilixo
```

```bash
cd ~/dev/sara-antilixo && ./install.sh
```

O `install.sh` pode rodar de novo quantas vezes quiser (depois de um `git pull`, por exemplo):
ele sincroniza as dependências pelo `uv.lock`, reescreve o LaunchAgent
`~/Library/LaunchAgents/com.mateuscamp.sara-antilixo.plist` (domingo às 10h), recarrega o agente
e troca o bloco do sara-antilixo no `~/.zshrc`, sem duplicar.

O agente aponta para a pasta do clone: se movê-la, rode o `./install.sh` de novo.

## Onde fica o relatório

- Último relatório: `~/.local/state/sara-antilixo/relatorio.md`
- Saída do launchd: `~/.local/state/sara-antilixo/launchd.log`

Ao abrir o terminal, o bloco no `~/.zshrc` avisa se o relatório não existe ou tem mais de 8 dias
(o launchd não roda com o Mac desligado). Em dia, não diz nada.

## Desinstalar

```bash
launchctl bootout "gui/$(id -u)/com.mateuscamp.sara-antilixo"
```

```bash
rm ~/Library/LaunchAgents/com.mateuscamp.sara-antilixo.plist
```

```bash
rm -r ~/.local/state/sara-antilixo
```

Depois apague do `~/.zshrc` as linhas entre `# >>> sara-antilixo >>>` e
`# <<< sara-antilixo <<<` (inclusive) e, se quiser, a pasta do clone.

## Desenvolver

`make check` é o portão (lint, tipos, fronteiras, testes). Regras do projeto em `AGENTS.md`.
