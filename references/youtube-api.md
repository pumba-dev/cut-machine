# YouTube API — Guia Operacional

Como configurar credenciais e o que esperar do upload via YouTube Data API v3. Público: humano fazendo o setup + subagente publisher. Regra do projeto: LLM nunca lê nem escreve nada dentro de `secrets/`.

## Setup GCP passo a passo (uma vez por conta)

1. Acessar https://console.cloud.google.com e criar um projeto (ex.: `social-accounts-poc`).
2. **APIs & Services → Library → "YouTube Data API v3" → Enable**.
3. **OAuth consent screen**: User Type `External`, modo **Testing**. Adicionar a conta Google dona do canal em **Test users** (sem isso o login falha com `access_denied`).
4. **Credentials → Create Credentials → OAuth client ID →** Application type **Desktop app** → baixar o JSON.
5. Salvar o JSON como `secrets/youtube/<conta>/credentials.json` — o diretório exato vem de `credentials_dir` da conta em `config/accounts.json` (ex.: `secrets/youtube/principal/credentials.json`).
6. Rodar `python scripts/auth.py --platform youtube --account <conta>`: abre o navegador (installed-app flow), pede consentimento e grava `secrets/youtube/<conta>/token.json`. Escopo mínimo usado: `https://www.googleapis.com/auth/youtube.upload`.

`secrets/` inteiro é gitignored; `credentials.json` e `token.json` nunca entram em commit.

## LIMITAÇÕES CRÍTICAS (política vigente do YouTube)

### Uploads via API ficam TRAVADOS como private
Todo vídeo enviado por `videos.insert` a partir de projeto de API **não auditado** (qualquer projeto criado após 28/07/2020 — caso deste) fica **bloqueado como privado** ("locked private"), **sem apelação** — não dá para tornar público nem pelo YouTube Studio. Para publicação real só existem dois caminhos:

- (a) passar pela auditoria de compliance da Google — formulário **"YouTube API Services – Audit and Quota Extension Form"**; ou
- (b) subir o arquivo manualmente no YouTube Studio.

Implicação na POC: `privacyStatus="private"` sempre (o bloco `publish` do clips.json já fixa `"privacy": "private"`). O upload via API valida o pipeline fim a fim; a publicação real é manual no Studio até a auditoria ser aprovada.

### Quota: 10.000 unidades/dia
- Cota padrão por projeto GCP: **10.000 unidades/dia**.
- `videos.insert` custa **1.600 unidades** → **~6 uploads/dia** por projeto.
- Aumento de quota passa pelo mesmo formulário de auditoria acima.
- No pipeline: cada conta tem `daily_upload_limit` em `config/accounts.json` (hoje 5, margem sob o teto de 6). Clips aprovados além do limite diário ficam com status `queued`, ordenados por score, e sobem no dia seguinte.

### Token em modo Testing expira em 7 dias
Com o OAuth consent screen em **Testing**, o refresh token **expira em 7 dias**. Sintoma típico: `invalid_grant` / `Token has been expired or revoked` no upload. Correção: re-rodar `python scripts/auth.py --platform youtube --account <conta>` e consentir de novo no navegador. Publicar o app (verificação da Google) elimina a expiração, mas não vale o custo na POC.

### Detecção de Shorts é automática
Não existe flag de Short na API: vídeo vertical/quadrado com ≤ 3 min vira Short automaticamente. O output do formato `short` (1080x1920, <60s) é classificado sem ação extra; 16:9 permanece long-form mesmo curto.

## Download bloqueado por anti-bot ("Sign in to confirm you're not a bot")

O YouTube bloqueia downloads sem sessão em muitos IPs residenciais. Constatado neste ambiente (2026-07): todos os `player_client` falham sem credencial, e `--cookies-from-browser` NÃO funciona com Chrome/Edge atuais no Windows (criptografia app-bound, yt-dlp issues #7271/#10927). Saídas, em ordem de preferência:

1. **Cookies exportados manualmente** (implementado): instalar a extensão "Get cookies.txt LOCALLY" no Chrome/Edge, abrir youtube.com logado, exportar e salvar como `secrets/youtube-cookies.txt` (formato Netscape). `core/sources/youtube.py` detecta o arquivo automaticamente. Cookies expiram de tempos em tempos — re-exportar quando o erro voltar. Recomendado: usar uma conta Google secundária, pois a conta dos cookies fica associada ao volume de downloads.
2. **Plugin PO token** (`bgutil-ytdlp-pot-provider`, requer Node): dispensa cookies, mas instala código de terceiros — decisão do dono do repo.

## Metadados do upload

- `title`: máx 100 caracteres (recomendado ≤ 80); não aceita `<` nem `>`.
- `description`: máx 5000 caracteres.
- `categoryId` comuns: **"22" = People & Blogs** (default do contrato `publish`), **"24" = Entertainment**. Outros úteis: "23" Comedy, "27" Education, "28" Science & Technology.
- `defaultLanguage` / `defaultAudioLanguage`: `"pt-BR"`.
- `selfDeclaredMadeForKids: false` — o campo `madeForKids` é derivado pelo YouTube; a declaração do dono é via `selfDeclared*`.

## Multi-conta

Cada conta é uma entrada em `config/accounts.json` com diretório de credenciais isolado. Para adicionar uma segunda conta YouTube:

1. Editar `config/accounts.json`:

```json
{
 "schema_version": 1,
 "accounts": [
  {
   "platform": "youtube",
   "id": "principal",
   "label": "Canal principal",
   "credentials_dir": "secrets/youtube/principal",
   "default": true,
   "daily_upload_limit": 5
  },
  {
   "platform": "youtube",
   "id": "cortes2",
   "label": "Segundo canal de cortes",
   "credentials_dir": "secrets/youtube/cortes2",
   "default": false,
   "daily_upload_limit": 5
  }
 ]
}
```

2. Credenciais: dá para **reusar o mesmo `credentials.json`** (mesmo client OAuth do mesmo projeto GCP) copiado para `secrets/youtube/cortes2/` — o que diferencia as contas é qual conta Google loga no navegador durante o auth. Adicionar essa segunda conta Google como Test user no consent screen. Atenção: contas no mesmo projeto GCP **dividem a quota de 10k unidades/dia**; projeto separado dá quota própria, mas exige setup e auditoria próprios.
3. Rodar `python scripts/auth.py --platform youtube --account cortes2` e logar com a conta dona do segundo canal → gera `secrets/youtube/cortes2/token.json`.
4. Usar: `python scripts/upload_clip.py --video-id <id> --clip <clip_id> --account cortes2`. Sem `--account`, o pipeline usa a conta com `"default": true` (resolução via `core.accounts.get_account`).
