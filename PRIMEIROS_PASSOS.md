# LocalHub — Primeiros Passos (`lhub`)

Guia rápido de instalação, configuração no PATH e uso do `lhub` no **seu
interpretador Python**, com foco no `lhub clone`. Para a referência completa veja o
[`README.md`](README.md).

---

## 1. O que é

O **LocalHub** (`lhub`) é um mini controle de versão **local, em Python puro,
sem git**. Ele:

- Guarda snapshots versionados numa pasta `.lhub/` (objetos endereçados por
  conteúdo, SHA-256 → blob / tree / commit; dá deduplicação e integridade).
- Sincroniza entre máquinas com **`clone` / `push` / `pull` / `fetch`** usando
  **uma pasta compartilhada como "remoto"** (drive de rede, OneDrive, pen-drive…).
- **Não precisa de servidor** nem de login: o controle de acesso é a própria
  permissão da pasta de rede (NTFS).

Cada pessoa usa o **seu próprio interpretador Python** (3.8+). Descubra o
caminho do seu com `py -0p` ou `(Get-Command python).Source`.

---

## 2. Instalação (no seu interpretador)

O jeito mais simples é o script **`install.ps1`** (na raiz do projeto). Ele valida
o interpretador, instala, opcionalmente põe `lhub` no PATH e confere a versão.

### Opção A — script (recomendado)

```powershell
# aponte para o SEU python e ja deixe `lhub` no PATH do usuario
.\install.ps1 -Python "C:\caminho\para\python.exe" -AddToPath

# ...ou deixe o script achar o Python automaticamente
.\install.ps1 -AddToPath

# modo editavel (desenvolver a partir do codigo)
.\install.ps1 -Python "C:\caminho\para\python.exe" -Editable
```

### Opção B — na mão (troque pelo SEU python)

```powershell
& "C:\caminho\para\python.exe" -m pip install -e .
```

### Opção C — via wheel (distribuir aos analistas)

```powershell
# gerar o pacote uma vez (cria dist\localhub-0.1.0-py3-none-any.whl)
& "C:\caminho\para\python.exe" -m pip wheel . --no-deps -w dist

# cada analista, no python dele:
.\install.ps1 -FromWheel "\\servidor\share\dist\localhub-0.1.0-py3-none-any.whl" -AddToPath
```

Conferir a instalação:

```powershell
lhub --version
# -> lhub 0.1.0
```

---

## 3. Deixar `lhub` na variável de ambiente (PATH)

Se você usou `install.ps1 -AddToPath`, **isso já foi feito** — pule para a seção 4.
Caso contrário, para digitar só **`lhub`** em qualquer pasta, adicione a pasta
`Scripts` do **seu** interpretador ao **PATH**.

> Descubra a pasta Scripts do seu python com:
> `& "C:\caminho\para\python.exe" -c "import sysconfig; print(sysconfig.get_path('scripts'))"`

### 3.1 Permanente (recomendado) — PATH do seu usuário

Rode **uma vez** no PowerShell (não precisa de admin, mexe só no seu usuário) —
troque `$dir` pela pasta Scripts do seu python:

```powershell
$dir = "C:\caminho\para\Scripts"
$atual = [Environment]::GetEnvironmentVariable("Path", "User")
if ($atual -notlike "*$dir*") {
    [Environment]::SetEnvironmentVariable("Path", "$atual;$dir", "User")
    "Adicionado ao PATH do usuario: $dir"
} else {
    "Ja estava no PATH."
}
```

> **Importante:** feche e reabra o terminal (ou faça logoff/login) para o novo
> PATH valer. Depois disso, `lhub` funciona em qualquer pasta:

```powershell
lhub --version
```

### 3.2 Só para a sessão atual (temporário, para testar)

```powershell
$env:Path += ";C:\caminho\para\Scripts"
lhub --version
```

### 3.3 Sem mexer no PATH (alternativas)

- Caminho completo: `& "C:\caminho\para\Scripts\lhub.exe" status`
- Como módulo, de dentro do projeto:
  `& "C:\caminho\para\python.exe" -m localhub status`

---

## 4. Configurar sua identidade (uma vez por máquina)

Fica gravado em `~\.lhubconfig.json` e vale para **todos** os repositórios:

```powershell
lhub config --global user.name  "Vitor"
lhub config --global user.email "vitorgrein04@gmail.com"
lhub config --list
```

(Sem `--global`, a config vale só para o repositório atual.)

---

## 5. `lhub clone` — o fluxo principal

`clone` copia um repositório de uma pasta remota para uma pasta local,
configura esse remoto como **`origin`** e já deixa a árvore de trabalho pronta
na branch padrão.

```
lhub clone <origem> [destino]
```

- `<origem>`: a pasta-repositório remota (de preferência um repositório **bare**).
- `[destino]`: pasta local a criar; **precisa estar vazia ou não existir**.
  Se omitido, usa o nome da pasta de origem.

> **Use sempre caminhos UNC** (`\\servidor\share\...`), **não** letras de unidade
> mapeada (`Z:\...`). A letra mapeada muda entre máquinas e o caminho do remoto
> fica gravado na config; UNC funciona para todos.

### Exemplo completo (do zero ao primeiro clone)

```powershell
# (A) UMA vez: criar o repositório central (bare) na pasta de rede
lhub init --bare "\\servidor\share\repos\projeto.lhub"

# (B) Em cada máquina: clonar para uma pasta local chamada "projeto"
lhub clone "\\servidor\share\repos\projeto.lhub" projeto
cd projeto

# (C) Identidade (se ainda não fez --global)
lhub config --global user.name  "Vitor"
lhub config --global user.email "vitorgrein04@gmail.com"

# (D) Trabalhar normalmente
#    ...edita arquivos...
lhub add .
lhub status
lhub commit -m "minha mudança"
lhub push                # envia ao origin (a pasta de rede)

# (E) Trazer o que os colegas enviaram
lhub pull
```

Depois do `clone`, estes comandos já assumem `origin` automaticamente:
`lhub push`, `lhub pull`, `lhub fetch`.

---

## 6. Fluxo de uso diário (resumo)

```powershell
lhub init                      # cria repositório na pasta atual (se for novo projeto)
lhub status                    # o que mudou
lhub add .                     # adiciona ao staging
lhub commit -m "primeiro commit"
lhub log --oneline             # histórico
lhub diff                      # mudanças não commitadas
lhub show HEAD                 # detalhe de um commit

lhub branch nova               # cria branch
lhub checkout nova             # troca de branch
lhub checkout -b feature       # cria e já troca

lhub pull                      # baixa e integra do origin
lhub push                      # envia ao origin
```

### Adicionar o repositório de um colega como outro remoto

Qualquer pasta-repositório serve de remoto:

```powershell
lhub remote add colega "\\servidor\share\repos\maria.lhub"
lhub push colega main
lhub fetch colega
```

---

## 7. Conflitos e regras de sincronização

- `pull` faz **fast-forward** quando possível; quando as histórias divergem,
  faz um **merge 3-vias** automático.
- Em conflito, os arquivos recebem marcadores `<<<<<<<` / `=======` / `>>>>>>>`.
  Resolva, depois `lhub add <arquivo>` e `lhub commit`.
- `push` exige **fast-forward**: dois `push` simultâneos são serializados com
  trava; quem ficar para trás recebe "não é fast-forward" e deve dar `lhub pull`
  antes (ou `lhub push --force`, com cuidado).

---

## 8. Ignorar arquivos

O LocalHub lê **`.gitignore`** (mesmo formato do GitHub) e também `.lhubignore`,
na raiz e em subpastas. Suporta `#` comentário, `!negação`, `pasta/` só-diretório,
`/raiz` ancorado, curingas `* ? [...]` e globstar `**`. Arquivos ignorados não
aparecem em `status` nem entram no `lhub add .` (use `lhub add -f` para forçar).

```gitignore
*.log
build/
__pycache__/
!importante.log     # exceção: este volta a ser rastreado
```

---

## 9. Referência rápida de comandos

| Comando | O que faz |
|---|---|
| `lhub init [--bare] [pasta]` | cria repositório (bare = remoto sem árvore) |
| `lhub config [--global] <chave> <valor>` / `--list` | lê/grava config |
| `lhub add [-f] <caminhos...>` | adiciona ao staging |
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
