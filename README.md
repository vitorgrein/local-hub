# LocalHub (`lhub`)

Um mini controle de versão **local, em Python puro, sem usar o git**. Guarda
snapshots versionados numa pasta `.lhub/` usando objetos endereçados por
conteúdo (SHA‑256: blob / tree / commit), e sincroniza entre máquinas com
`push` / `pull` / `clone` usando **uma pasta compartilhada como "remoto"**
(drive de rede, OneDrive, pen‑drive etc.). Nenhum servidor é necessário.

## Instalação

Cada pessoa instala no **seu próprio interpretador Python** (3.8+). A forma mais
simples é o script [`install.ps1`](install.ps1) — aponte para o python que você
quer usar e ele instala, opcionalmente põe `lhub` no PATH e confere a versão:

```powershell
# instala no interpretador informado e deixa `lhub` disponível em qualquer pasta
.\install.ps1 -Python "C:\caminho\para\python.exe" -AddToPath

# ...ou deixe o script detectar o Python do PATH automaticamente:
.\install.ps1 -AddToPath

# modo editável (para desenvolver a partir do código):
.\install.ps1 -Python "C:\caminho\para\python.exe" -Editable
```

> Não sabe o caminho do seu Python? Veja com `py -0p` ou `(Get-Command python).Source`.

Sem o script, dá para instalar na mão (troque pelo **seu** python):

```powershell
& "C:\caminho\para\python.exe" -m pip install -e .
```

### Distribuir aos analistas via wheel

```powershell
# gerar o pacote (uma vez) -> cria dist\localhub-0.1.0-py3-none-any.whl
& "C:\caminho\para\python.exe" -m pip wheel . --no-deps -w dist

# cada analista, no python dele (pelo script ou na mão):
.\install.ps1 -FromWheel "\\servidor\share\dist\localhub-0.1.0-py3-none-any.whl" -AddToPath
```

Depois disso o comando `lhub` fica disponível. Sem instalar, também dá para
rodar `python -m localhub ...` de dentro da pasta do projeto.

## Testar

Não há dependências externas (só a biblioteca padrão do Python). Dois scripts
ajudam a validar na sua máquina, sem precisar instalar nada:

```powershell
.\run-tests.ps1     # roda toda a suite de testes (unittest)
.\demo.ps1          # simula 2 pessoas: init/commit/push/clone/pull de ponta a ponta
.\demo.ps1 -Keep    # idem, mas mantem a pasta temporaria para inspecionar
```

Ambos aceitam `-Python "C:\caminho\para\python.exe"`; se omitido, detectam o
Python automaticamente. Pela linha de comando direto também dá:
`python -m unittest discover -s tests`.

## Uso rápido

```powershell
lhub init                      # cria um repositório na pasta atual
lhub config user.name  "Vitor"            # identidade só neste repositório
lhub config user.email "vitorgrein04@gmail.com"
# ...ou uma vez por máquina, valendo para todos os repositórios:
lhub config --global user.name  "Vitor"
lhub config --global user.email "vitorgrein04@gmail.com"

lhub add .                     # adiciona arquivos ao staging
lhub status                    # mostra o que mudou
lhub commit -m "primeiro commit"
lhub log --oneline             # histórico
lhub diff                      # mudanças não commitadas
lhub show HEAD                 # detalhe de um commit

lhub branch nova               # cria branch
lhub checkout nova             # troca de branch
lhub checkout -b feature       # cria e já troca
```

## Trabalho em rede com vários analistas (replicável)

O "remoto" é só **outra pasta numa rede do Windows** — de preferência um
repositório **bare** (sem árvore de trabalho). Quem tiver acesso à pasta pode
`clone`/`push`/`pull`. **O controle de acesso é a própria permissão da pasta de
rede (NTFS)** — não há login separado.

```powershell
# 1) UMA vez, na pasta compartilhada, crie o repositório central (bare):
lhub init --bare "\\servidor\share\repos\projeto.lhub"

# 2) cada analista, na máquina dele:
lhub clone "\\servidor\share\repos\projeto.lhub" projeto
cd projeto
lhub config --global user.name "Fulano"      # identidade da máquina (uma vez)
# ...edita arquivos...
lhub add .
lhub commit -m "minha mudança"
lhub push                                     # envia ao repositório de rede

# 3) para trazer o que os outros enviaram:
lhub pull
```

Cada analista também pode criar **seu próprio** repositório na rede e adicionar
o do colega como remoto — qualquer pasta-repositório serve como remoto:

```powershell
lhub remote add colega "\\servidor\share\repos\maria.lhub"
lhub push colega main
```

`pull` faz **fast-forward** quando possível e, quando as histórias divergem,
faz um **merge 3‑vias** automático. Em conflito, os arquivos recebem marcadores
`<<<<<<<` / `=======` / `>>>>>>>`; resolva, depois `lhub add <arquivo>` e
`lhub commit`. Dois `push` simultâneos no mesmo repositório são serializados com
trava; quem ficar para trás recebe "não é fast-forward" e deve dar `pull` antes.

> **Importante:** use **caminhos UNC** (`\\servidor\share\...`), não letras de
> unidade mapeada (`Z:\...`). A letra mapeada pode ser diferente em cada máquina
> e o caminho do remoto fica gravado na config — UNC funciona para todos.

## Comandos

| Comando | O que faz |
|---|---|
| `lhub init [--bare] [pasta]` | cria um repositório (bare = remoto sem working tree) |
| `lhub config [--global] <chave> <valor>` / `--list` | lê/grava config; `--global` = por máquina |
| `lhub add [-f] <caminhos...>` | adiciona ao staging (respeita ignore; `-f` força) |
| `lhub rm [--cached] <caminhos...>` | remove do rastreamento |
| `lhub status` | estado da árvore de trabalho |
| `lhub commit -m "msg"` | grava um commit |
| `lhub log [-n N] [--oneline]` | histórico |
| `lhub show [rev]` | commit + diff |
| `lhub diff [--staged] [revA] [revB]` | diferenças |
| `lhub branch [nome] [-d nome]` | lista/cria/apaga branches |
| `lhub checkout [-b] <alvo>` | troca de branch/commit |
| `lhub remote add <nome> <pasta>` / `remote` | gerencia remotos |
| `lhub clone <pasta> [destino]` | clona de um remoto |
| `lhub fetch [remoto]` | baixa objetos/refs sem integrar |
| `lhub push [remoto] [branch] [--force]` | envia commits |
| `lhub pull [remoto] [branch]` | baixa e integra |

## Agendador (`lhub sched`) + painel

Roda suas automações versionadas em horários (cron), na própria máquina, sem
depender do Agendador de Tarefas do Windows. Cada projeto traz um
**`workflow.yml`** (estilo GitHub Actions); o agendador roda a **versão
commitada**, captura log/histórico, mostra um **painel** e envia **avisos** de
falha e de execução que **não rodou**.

`workflow.yml` na raiz do projeto (veja [`workflow.example.yml`](workflow.example.yml)):

```yaml
name: cobranca-bradesco
schedule: "0 7 * * 1-5"        # 07:00, seg-sex (min hora dia mes dia-semana)
python: "C:/.../python.exe"    # use {python} nos comandos
on_dirty: warn                 # warn | skip | run (mudancas nao commitadas)
steps:
  - run: "{python} run.py"
  - run: "{python} daily.py"
on_failure:
  - run: "{python} notifica_erro.py"
```

Uso:

```powershell
lhub sched add C:\caminho\do\projeto   # registra (precisa ter workflow.yml)
lhub run cobranca-bradesco             # roda agora (teste), amarrado ao commit
lhub sched list                        # projetos + schedule
lhub sched daemon --web                # agendador residente + painel web
lhub sched dashboard                   # painel no terminal (atualiza sozinho)
lhub sched status                      # historico das execucoes
lhub sched logs cobranca-bradesco      # ultimo log
lhub sched check                       # 1 checagem: avisa se daemon caiu ou ha atraso
```

| Comando | O que faz |
|---|---|
| `lhub sched add <pasta>` | registra um projeto (lê o `workflow.yml`) |
| `lhub sched rm <nome>` | remove do agendador |
| `lhub sched list` | lista projetos e seus schedules |
| `lhub run <nome\|pasta>` | roda o workflow **agora** (gatilho manual) |
| `lhub sched daemon [--web] [--host H] [--port P]` | loop residente; dispara os jobs vencidos a cada minuto |
| `lhub sched web [--port P]` | só o painel web (somente leitura) |
| `lhub sched dashboard [-n/--interval]` | painel no terminal |
| `lhub sched status [-n]` | histórico recente |
| `lhub sched logs <nome>` | último log de um projeto |
| `lhub sched check` | watchdog pontual (sai ≠ 0 e avisa se houver problema) |
| `lhub sched config` | mostra onde fica o `config.json` dos avisos |

**Avisos (e-mail/webhook):** crie `~/.lhub-scheduler/config.json` a partir de
[`config.example.json`](config.example.json). O agendador avisa quando um job
**falha** e quando um horário previsto passou **sem rodar** (atraso). O `daemon`
grava um *heartbeat*; o painel mostra se o próprio agendador caiu.

> O agendador depende de **PyYAML** (instalado junto pelo `pip`). Se você instala
> por wheel numa máquina sem internet, garanta que o `pyyaml` esteja disponível lá.

**Watchdog de última instância:** se a VM reiniciar e o `daemon` não subir, nada
detecta a falha. Para cobrir isso, agende **uma** entrada no Agendador do Windows
chamando `lhub sched check` a cada 15 min — ele te avisa se o agendador morreu.

## Como funciona (resumo)

- `.lhub/objects/`: objetos comprimidos (zlib), nomeados pelo hash SHA‑256 do
  conteúdo — isso dá deduplicação e verificação de integridade.
- `.lhub/refs/heads/<branch>`: aponta para o commit mais recente da branch.
- `.lhub/refs/remotes/<remoto>/<branch>`: o que sabemos do remoto.
- `.lhub/HEAD`: branch atual; `.lhub/index.json`: staging; `.lhub/config.json`.
- `push`/`fetch` copiam apenas os objetos que faltam no destino (incremental) e
  atualizam as refs. `push` exige fast-forward (a menos de `--force`).

## Ignorar arquivos (`.gitignore`)

O LocalHub lê arquivos **`.gitignore`** (mesmo formato do GitHub) e também
`.lhubignore`, na raiz e em subpastas. Suporta comentários (`#`), negação
(`!padrao`), só-de-diretório (`pasta/`), ancoragem (`/raiz`), curingas
`* ? [...]` e globstar `**`. Arquivos ignorados não aparecem em `status` nem
entram no `lhub add .` (use `lhub add -f` para forçar um arquivo específico).

Exemplo de `.gitignore`:

```gitignore
*.log
build/
__pycache__/
!importante.log     # exceção: este volta a ser rastreado
```
