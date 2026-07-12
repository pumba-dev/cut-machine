---
name: adicionar-canal
description: Onboarding completo de uma nova conta/canal do YouTube no pipeline multi-conta - checklist do canal, GCP/OAuth, config/accounts.json, assets de marca e decisao de cron. Uso - /adicionar-canal
---

# /adicionar-canal — onboarding de um novo canal do YouTube

O pipeline **já é multi-conta por design**: `clip-scout` grava `publish.account` em
cada clip a partir do `--conta` que você repassa no prompt (`.claude/agents/clip-scout.md`),
`render_clip.py` lê esse campo pra escolher o brand da conta, e os crons de
`publish_next.py` já fazem round-robin entre contas pela `publish.account` de cada
clip. **Adicionar um canal novo é config + assets + secrets + docs (perfil de copy do nicho
e a lista de canais do `CLAUDE.md`) — nenhuma mudança de código.**

Peça ao usuário, se ainda não tiver: nome do canal, nicho/público-alvo, paleta de
cores (2-3 cores de marca), e se já existe algum `credentials.json`/asset órfão em
disco de uma tentativa anterior (ver Passo 1).

## Passo 0 — Canal no YouTube (ação do usuário, fora do repo)

Isso é config do **Studio do YouTube em si** — sem acesso de browser/API pra isso,
apenas oriente o usuário:

- Criar o canal (conta Google/Brand Account) com o nome definido.
- Avatar + banner: se o usuário tiver prompts de geração de imagem prontos, sugira
  gerar numa ferramenta à parte e subir no Studio (não é parte deste pipeline).
- About/descrição + keywords, mensagem de boas-vindas e regras de comunidade.

Não bloqueia os passos técnicos abaixo — pode rodar em paralelo.

## Passo 1 — Escolher `account id` e checar órfãos

Escolha um slug curto pro `id` interno (ex. `negocios`, `cortes2` — como
`principal` já é o id do 1º canal, não precisa ser descritivo; o nome de verdade
vai em `label`/`channel_name`). **Antes de criar do zero**, cheque se já existe
algo em disco com esse id (retomada de tentativa anterior):

```
secrets/youtube/<id>/credentials.json     # projeto GCP ja criado?
assets/short-frame/<id>.png               # arte ja rascunhada?
assets/corte-frame/<id>.png
```

Se `credentials.json` já existir (sem `token.json`, sem entrada em
`accounts.json`) é sinal de um onboarding anterior não finalizado — confirme com
o usuário se reaproveita (pula a criação do projeto GCP no Passo 2) ou descarta.

Se os PNGs de moldura já existirem, **compare o SHA256 com os de outra conta**
(`sha256sum assets/short-frame/<id>.png assets/short-frame/principal.png`, etc.) —
se forem idênticos, é uma cópia-placeholder que ainda carrega a marca/cor de outro
canal, não arte final. Ver Passo 4 (recolorir em vez de descartar).

## Passo 2 — GCP + OAuth

**Se reaproveitando um projeto órfão do Passo 1**, pule pra criação da entrada em
`accounts.json` (Passo 3) e depois rode `auth.py` direto (fim deste passo) —
só confira que a conta Google do canal está em **Test users** do consent screen
desse projeto (Console GCP → APIs & Services → OAuth consent screen).

**Se for projeto novo:**

1. https://console.cloud.google.com → criar projeto novo.
2. APIs & Services → Library → **YouTube Data API v3** → Enable.
3. OAuth consent screen: User Type `External`, modo **Testing**, adicionar a
   conta Google dona do canal em **Test users** (sem isso o login falha com
   `access_denied`).
4. Credentials → Create Credentials → OAuth client ID → Application type
   **Desktop app** → baixar o JSON.
5. Salvar como `secrets/youtube/<id>/credentials.json` (a pasta é criada
   automaticamente por `core.accounts.credentials_dir` na 1ª chamada, mas o
   arquivo em si tem que ser colocado à mão — **nunca leia nem imprima esse
   arquivo**, apenas confirme que existe).

Depois de criar a entrada em `accounts.json` (Passo 3):

```
python scripts/auth.py --platform youtube --account <id>
```

Abre o browser, pede consentimento, grava `secrets/youtube/<id>/token.json`.
Idempotente: token válido existente vira `{"ok": true, "skipped": true}`.

Nota de quota: reaproveitar o MESMO projeto GCP de outra conta já configurada
economiza setup mas **divide** os 10k queries/dia e 100 uploads/dia entre as
contas do mesmo projeto — projeto próprio dá quota isolada (ver
`references/youtube-api.md`).

## Passo 3 — `config/accounts.json`

Adicionar uma entrada no array `accounts` (nunca remova/edite as existentes).
Template completo — todo bloco além de `platform`/`id`/`credentials_dir` é
**opt-in e merge-safe** (campo ausente cai no default neutro do respectivo
`*_config.py`/`branding.py`; conta sem os blocos = comportamento clássico):

```json
{
  "platform": "youtube",
  "id": "<id>",
  "label": "<Nome do canal>",
  "channel_name": "<Nome do canal>",
  "niche": "<descrição do nicho/público-alvo, usada pelo copywriter p/ coerência>",
  "copy_profile": "<perfil de nicho: politica | financas | ... (ver Passo 3.5)>",
  "credentials_dir": "secrets/youtube/<id>",
  "default": false,
  "daily_upload_limit": 100,
  "brand": {
    "short_frame": "assets/short-frame/<id>.png",
    "corte_frame": "assets/corte-frame/<id>.png",
    "short_outro": "assets/short-end/<id>.mp4",
    "corte_outro": "assets/corte-end/<id>.mp4",
    "accent_color": "#RRGGBB"
  },
  "transform": {
    "speed": 1.02,
    "pitch_semitones": 0.3,
    "eq": true,
    "music_dir": "assets/music/<id>",
    "music_volume": 0.02,
    "music_lufs": -16,
    "color": { "contrast": 1.05, "saturation": 1.1, "gamma": 0.98 },
    "zoom": 1.2,
    "jitter": 0.35
  },
  "thumbnail": {
    "face_aware": true,
    "intro_short": true,
    "intro_duration_s": 0.1,
    "rembg_model": "u2net"
  },
  "reframe": {
    "enabled": true,
    "min_segment_s": 1.2,
    "margin": 0.35,
    "fps": 5.0,
    "max_frames": 4000,
    "min_confidence": 0.15,
    "cutaway": false,
    "hook_punch": true,
    "sfx_dir": "",
    "sfx_volume": 0.5
  },
  "jumpcut": { "enabled": false, "min_gap_s": 1.2, "buffer_s": 0.15 },
  "default_hashtags": ["#...", "#...", "#...", "#...", "#..."]
}
```

Comece só com os campos mínimos (`platform`/`id`/`label`/`channel_name`/`niche`/
`copy_profile`/`credentials_dir`/`default`/`daily_upload_limit`/`default_hashtags`) se o
usuário quiser ir ao ar rápido sem moldura customizada — `brand`/`transform`/`reframe`/
`thumbnail`/`jumpcut` ausentes = fallback liso (cor chapada / tudo-off), zero erro.
`transform`/`reframe` acima são os valores já validados em `principal` (mesmo
risco de Content ID de repostar conteúdo de terceiros) — copie como ponto de
partida, não precisa reinventar por canal.

`default: false` é obrigatório em qualquer conta que não seja a principal —
sem isso, scripts chamados sem `--conta`/`--account` continuariam resolvendo pra
essa conta nova em vez da existente.

## Passo 3.5 — Perfil de copy do nicho (`copy_profile`)

O `copy_profile` liga a conta ao padrão editorial do nicho em `references/copy/<perfil>.md`
(arquétipos de gancho, exemplos com nomes reais, hashtags de tema e avisos legais). O
copywriter lê `references/padrao-copy.md` (universal) **+** esse arquivo. Perfis existentes:
`politica`, `financas`.

- **Nicho igual ao de um canal existente** (ex.: mais um canal de política): reutilize o
  `copy_profile` existente — nada a criar, só apontar. Dois canais podem dividir o perfil.
- **Nicho novo:** escolha um slug (`cripto`, `esportes`...), grave `copy_profile: "<slug>"`
  na conta e **crie `references/copy/<slug>.md`** copiando a estrutura de um existente
  (`politica.md`/`financas.md`): identidade editorial, arquétipos próprios, exemplos reais
  (citação crua + alvo do nicho), hashtags (default/tema/pessoa) e avisos legais/temas
  sensíveis do nicho. Peça ao usuário o material do nicho se não souber (alvos típicos,
  figuras, restrições legais/regulatórias).
- Conta **sem** `copy_profile` funciona (copywriter roda só com o universal + o texto livre
  de `niche`), mas a copy fica genérica — recomende criar o perfil.

## Passo 4 — Assets de marca

Convenção: `assets/<tipo>/<id>.<ext>` — `short-frame`/`corte-frame` (PNG, moldura
com janela transparente onde o vídeo entra), `short-end`/`corte-end` (MP4,
vinheta de fim, opcional), `music/<id>/` (pasta de faixas, opcional).

**Sem arte customizada ainda?** Funciona hoje mesmo sem nenhum PNG: `brand`
ausente ou `short_frame`/`corte_frame` vazios caem no fallback de cor chapada
(`short_bg_color` pro short, `border_color`/`accent_color` pro corte — moldura
gerada preto+amarelo por padrão, cor customizável). Dá pra colocar o canal no ar
só com as cores da marca e adicionar a arte PNG depois.

**Recolorindo uma moldura existente pra um canal novo** (atalho mais rápido que
desenhar do zero, e evita o problema de geometria abaixo): script Python
(numpy + PIL) que isola a cor de destaque atual por faixa de HSV/RGB e reatribui
só o HUE pro tom da marca nova, preservando saturação/valor (mantém sombra/
dithering do pixel art) e o canal alpha (janela transparente) intocado:

```python
import colorsys
import numpy as np
from PIL import Image

im = Image.open("assets/short-frame/<conta_origem>.png").convert("RGBA")
arr = np.array(im)
r, g, b, alpha = arr[...,0], arr[...,1], arr[...,2], arr[...,3]
# ajuste os limiares pra faixa de cor real da arte de origem
mask = (r > 150) & (g > 60) & (g < 200) & (b < 110) & (alpha > 10) & ((r.astype(int)-b.astype(int)) > 60)

rgb01 = arr[...,:3].astype(float) / 255.0
cmax, cmin = rgb01.max(-1), rgb01.min(-1)
v = cmax
s = np.where(cmax > 0, (cmax-cmin)/np.where(cmax==0,1,cmax), 0.0)

target_h, _, _ = colorsys.rgb_to_hsv(*(c/255 for c in (0x39,0xFF,0x14)))  # cor nova
# HSV->RGB vetorizado pra um H fixo (ver core/render/... nao ha helper pronto;
# implementar inline ou usar colorsys por pixel do mask, que ja e um subconjunto pequeno)
```

Confira visualmente o resultado (Read da imagem) antes de aceitar.

**Caveat de geometria**: a janela recortada da moldura (`WINDOW` em
`core/render/short_frame.py`/`corte_frame.py`) é uma constante **global** hoje,
não por conta — assume que toda arte tem o mesmo recorte da 1ª conta
(`principal`). Recolorir uma arte existente preserva a geometria automaticamente
(mesmo arquivo, só muda a cor). Se for desenhar arte nova do zero, mantenha a
janela transparente nas MESMAS coordenadas (documentado no topo dos dois
arquivos) — janela diferente exigiria refatorar `WINDOW` pra vir do bloco `brand`
da conta (fora do escopo desta skill; sinalize ao usuário se isso virar bloqueio
recorrente em canais futuros).

## Passo 5 — Cron (Agendador de Tarefas do Windows)

Os 2 crons genéricos já existentes (`publish_next.py --format short|corte`, sem
`--account`) **já publicam qualquer conta** cujos clips estejam `rendered`/`queued`
com QA `pass` — pela própria `publish.account` do clip. Pergunte ao usuário:

- **Reaproveitar os genéricos (default)**: zero mudança no Agendador — a conta
  nova já entra no round-robin assim que produzir clips com `--conta <id>`.
- **Tarefa dedicada** (cadência/horário próprio pro canal novo):
  1. Criar `scripts/publish_short_<id>.cmd`/`publish_corte_<id>.cmd` (mesmo
     padrão de `scripts/publish_short.cmd`, com `--account <id>` e log próprio
     em `logs/publish_<formato>_<id>.log`).
  2. Registrar via `schtasks /create /tn "YT Publish <Formato> (<Nome>)" /sc daily /st <hora> /ri <min> /du 24:00 /tr "wscript.exe //B \"<caminho>\\scripts\\run_hidden.vbs\" \"<caminho>\\scripts\\publish_<formato>_<id>.cmd\""`,
     com horário deslocado dos crons existentes pra não colidir no mesmo minuto.
     **Sempre via `run_hidden.vbs`** (nunca aponte `/tr` direto pro `.cmd`): sem
     ele o Agendador abre uma janela de cmd visível a cada disparo (a tarefa
     roda com `LogonType=InteractiveToken`, sessão interativa do usuário logado
     — sem sessão de serviço/hidden, todo processo console aloca janela). O
     wrapper (`WScript.Shell.Run` com `WindowStyle=0`) suprime a janela do
     cmd/python filho. Pra alterar o `/tr` de uma tarefa já existente, **não use
     `schtasks /change /tr`** — ele pede senha do usuário toda vez mesmo em
     logon interativo sem senha salva; exporte com `schtasks /query /tn "<nome>"
     /xml`, edite só o `<Command>`/`<Arguments>` e reimporte com `schtasks
     /create /xml <arquivo> /tn "<nome>" /f` (preserva `LogonType` e agenda, sem
     prompt).
  3. Validar antes: `python scripts/publish_next.py --format short --account <id> --dry-run`.

## Passo 6 — Lembrete crítico de uso

**Sempre passe `--conta <id>` pro `/produzir`/`/planejar`** ao trabalhar um vídeo
desta conta — é isso que o clip-scout usa pra gravar `publish.account` em cada
clip; sem isso, o render usa o brand errado (cai na conta `default`) e o publish
sobe no canal errado.

## Verificação final

1. `python -c "from core.accounts import get_account; print(get_account('youtube','<id>'))"` — resolve sem erro.
2. `python scripts/auth.py --platform youtube --account <id>` — `{"ok": true}`.
3. Se criou cron dedicado: `schtasks /query /tn "<nome da tarefa>"`.
4. Teste ponta-a-ponta antes de ligar auto-publish de vez:
   `/produzir <url-de-teste> --conta <id> --sem-upload` — confira que `clips.json`
   grava `publish.account: "<id>"` e que o render usa o brand certo.
5. `python scripts/publish_next.py --format short --account <id> --dry-run` —
   confirma qual clip seria escolhido antes de deixar o cron publicar de verdade.
6. **Docs:** o `copy_profile` aponta pra um `references/copy/<perfil>.md` existente (ou o
   novo foi criado, Passo 3.5), e o canal foi **adicionado à tabela "Canais atuais" do
   `CLAUDE.md` §8** — é o que mantém o orquestrador ciente de todos os canais.
