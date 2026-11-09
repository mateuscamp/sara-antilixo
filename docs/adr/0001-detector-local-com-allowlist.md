# 0001 — Um script local em Python detecta o lixo e avisa; só apaga caches recriáveis da allowlist

**Status:** Aceito
**Data:** 2026-11-08
**Driver ★:** detectar cedo

## Contexto

Em 08/11/2026 o Mac foi formatado com ~75 GB de lixo acumulado sem aviso. Origens medidas:
4,4 GB de dados de apps desinstalados arrastando para o Lixo (Comet, Tibia, Atlas, Unity, Notion)
que ficaram na `~/Library`; ~10 GB de restos de dev (`.build` do Swift, `node_modules`, `.venv`,
`target` do Rust, runtime do Codex) em projetos espalhados pelo HOME, vários com commits sem push;
5,8 GB de biblioteca do Fotos guardada dentro do iCloud Drive, onde não sincroniza e fica presa.
O detector anterior (disk-watch) não existe mais. Uma pessoa, um Mac, sem servidor.

Quantum atual: 1. Um processo local rodado pelo launchd; o único dado próprio é o estado em
`~/.local/state/sara-antilixo/` (último relatório, data da última limpeza).

## Drivers

| ★ | Característica | Origem | Como se mede |
|---|---|---|---|
| ★ | Detectar cedo | 75 GB acumulados sem aviso até a formatação | Qualquer categoria >2 GB avisada em ≤7 dias |
| | Limpeza segura | Repos com commit sem push no meio do lixo | Zero deleção fora da allowlist; repo com commit sem push, stash ou arquivo modificado nunca é alvo |
| | Sobreviver à formatação | O disk-watch se perdeu na formatação | `git clone` + `./install.sh` em <10 min, idempotente |
| | Silêncio | Aviso que se ignora vira ruído | 0 notificações em semana sem achado novo |
| | Testável | Código que apaga arquivo do usuário | Suíte em <15 s sem tocar o HOME real (era <10 s até 2026-11-09; ver Notas) |

## Alternativas consideradas

| Opção | Ganha | Perde | Por que não |
|---|---|---|---|
| Tarefa agendada do Claude | Zero código para manter | Não determinística; pode apagar errado | Viola "limpeza segura" |
| Só apps prontos (PureMac e similares) | Interface pronta | Não veem git, projetos fora de `~/dev` nem a biblioteca do Fotos no iCloud | Não cobrem ~16 GB das origens medidas |
| Shell script | Nada a instalar | Difícil de testar a parte que apaga | Viola "testável" |
| **Python local, stdlib, LaunchAgent semanal** | Determinístico, testável, sem dependência em produção | Código próprio para manter | — |

## Decisão

Um script local em Python, só com a biblioteca padrão no que roda em produção, executado
semanalmente por um LaunchAgent. Ele **detecta e avisa**. Só apaga sozinho caches recriáveis de
uma allowlist fechada (npm, uv, Homebrew, Gradle), no máximo uma vez por mês. O Claude só lê o
relatório; nunca executa limpeza.

Estrutura (`src/antilixo/`):

- `coletores/`: funções puras que varrem e devolvem `Achado`. Órfãos na `~/Library`; projetos
  parados >60 dias com build pesado ou sem push; `.git` fora de `~/dev`; `.photoslibrary` dentro
  de iCloud/Proton Drive; caches.
- `dominio/`: o núcleo. Allowlist e classificação apagar/avisar/ignorar. Sem E/S. (O desenho
  original chamava a pasta de `politica/`; renomeada para `dominio/` em 2026-11-08 para casar com
  o contrato que o juiz do python-on-rails exige, sem registrar desvio.)
- `acoes/`: o único lugar que apaga.
- `relatorio/`: Markdown e notificação via `osascript`.

## Consequências

**Ganha:** aviso semanal determinístico de todas as origens medidas, inclusive as que nenhum app
pronto vê (git, Fotos no iCloud), e uma parte que apaga coberta por teste sem tocar o HOME real.

**Perde:**
- Código próprio para manter, inclusive a lista de órfãos conhecidos da `~/Library`.
- Só stdlib em produção: nada de biblioteca pronta para varrer o disco ou montar o relatório.
- O launchd não roda com o Mac desligado; a semana em que ele ficou desligado atrasa o aviso.
  O heartbeat no `.zshrc` cobre isso.
- A notificação via `osascript` depende da permissão de notificações do macOS; sem ela, o aviso
  fica só no relatório.
- Ferramentas de desenvolvimento (ruff, basedpyright, pytest, import-linter) entram pelo `uv.lock`
  do python-on-rails. Por isso o comando de teste é `make check`, e não mais
  `python3 -m unittest -q`, e o `install.sh` precisa instalar o uv numa máquina formatada.

**Aceito conscientemente:** caches da allowlist podem ser apagados enquanto uma ferramenta os usa;
o custo é baixar de novo. Revisitar se um aviso de categoria >2 GB chegar depois de 7 dias, ou se
alguma deleção acontecer fora da allowlist.

## Governança

| O que verifica | Mecanismo | Onde roda | Falha quando |
|---|---|---|---|
| Limpeza só dentro da allowlist | `test_limpar_recusa_fora_da_allowlist` | `make check` | `limpar()` aceita caminho fora da allowlist, inclusive por `..`, symlink ou prefixo parecido |
| Repo com trabalho não salvo nunca é alvo | `test_so_achados_de_cache_sao_apagados` (só CACHE vira "apagar"; projeto parado e git fora de dev nunca) | `make check` | Repo com commit sem push, stash ou arquivo modificado aparece como alvo |
| Só `acoes/` apaga | import-linter "só acoes apaga arquivos" + `test_so_acoes_apaga_arquivos` (por nome: `rmtree`, `unlink`, `rmdir`, `remove`, `removedirs`, `TemporaryDirectory`, `NamedTemporaryFile`) | `make check` | `shutil`, `rmtree`, `unlink` ou `rmdir` fora de `acoes/` |
| Instalação reproduzível | `test_install_idempotente` com HOME temporário | `make check` | Rodar `install.sh` duas vezes muda algo na segunda |
| O detector está rodando | Heartbeat no `.zshrc` (`test_heartbeat_avisa_so_com_relatorio_de_mais_de_8_dias`) | Cada shell aberto | Último relatório com >8 dias |
| Orçamento de disco | Aviso no relatório e na notificação (testes de crescimento em `test_classificacao.py`) | Execução semanal | Disco cresce >20 GB em 30 dias |
| Detectar cedo sem ruído | `test_classificacao.py` e `test_library.py` | `make check` | Categoria somada >2 GB não vira aviso; achado já avisado notifica de novo sem crescer ≥20%; pasta `com.apple.*` ou da lista de exceções vira órfã |

Regra derivada no `AGENTS.md`: seção "Segurança da limpeza".

## Notas

Regras do domínio decididas em 2026-11-09 (aviso por categoria somada >2 GB, nova notificação
só com crescimento ≥20%, órfão por bundle id com lista de exceções do sistema): ver `AGENTS.md`.

Orçamento da suíte revisto em 2026-11-09, de <10 s para <15 s, decidido pelo usuário: com os
coletores integrados, 301 testes mediram 10,3 a 12,2 s, e o tempo vem dos testes com git e bash
de verdade (coletor de projetos, install.sh), que são a parte que dá segurança. Alternativas
recusadas: pytest-xdist (dependência nova, risco de teste não isolado) e mover esses testes para o
`make e2e` (sairiam do hook Stop).

Autor: Mateus Campelo · Criado em: 2026-11-08 · Aprovado em: 2026-11-08
