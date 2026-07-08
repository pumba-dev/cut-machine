# YouTube API — Guia Operacional

Como configurar credenciais e o que esperar do upload via YouTube Data API v3. Público: humano fazendo o setup + subagente publisher. Regra do projeto: LLM nunca lê nem escreve nada dentro de `secrets/`.

## Setup GCP passo a passo (uma vez por conta)

1. Acessar https://console.cloud.google.com e criar um projeto (ex.: `social-accounts-poc`).
2. **APIs & Services → Library → "YouTube Data API v3" → Enable**.
3. **OAuth consent screen**: User Type `External`, modo **Testing**. Adicionar a conta Google dona do canal em **Test users** (sem isso o login falha com `access_denied`).
4. **Credentials → Create Credentials → OAuth client ID →** Application type **Desktop app** → baixar o JSON.
5. Salvar o JSON como `secrets/youtube/<conta>/credentials.json` — o diretório exato vem de `credentials_dir` da conta em `config/accounts.json` (ex.: `secrets/youtube/principal/credentials.json`).
6. Rodar `python scripts/auth.py --platform youtube --account <conta>`: abre o navegador (installed-app flow), pede consentimento e grava `secrets/youtube/<conta>/token.json`. Escopos: `youtube.upload` (subir vídeo + `thumbnails.set`) + `youtube.readonly` (reler status/estatísticas via `videos.list`). **Mudança de escopo exige re-consentimento**: apague `token.json` (ou deixe o refresh falhar) e re-rode `auth.py` para reautorizar com os dois escopos.

`secrets/` inteiro é gitignored; `credentials.json` e `token.json` nunca entram em commit.

## LIMITAÇÕES CRÍTICAS (política vigente do YouTube)

### Privacidade do upload — REVISADO 2026-07-08: público funciona neste projeto
A documentação original assumia que projeto de API não-auditado (criado após 28/07/2020) travaria todo `videos.insert` como **"locked private"**, sem apelação. **Isso NÃO se confirmou neste projeto.** Teste empírico em 2026-07-08 (`KGs0aTqKwaQ-c04`):

- `videos.insert` com `status.privacyStatus="public"` → resposta `privacyStatus="public"`, `uploadStatus="uploaded"`, `rejectionReason=null`, `failureReason=null`.
- `thumbnails.set` → **200 OK** (logo o canal está verificado por telefone, requisito da API para custom thumbnail).
- Vídeo público: https://youtu.be/cBLLaNkxhwk

Conclusão: este projeto GCP aparenta estar auditado/liberado (ou a política mudou). **Default do pipeline agora é `privacyStatus="public"`** (`upload_clip.py`/`youtube.py`); `privacy` por clip em `clips.json` pode ser `private`/`unlisted` para exceções.

Ressalvas: (1) a resposta do insert ecoa o status pedido — confirme na 1ª vez que o vídeo **permanece** público (abra a URL / Studio); a durabilidade de longo prazo não foi medida. (2) Publicar é ação externa/irreversível — confirmar com o usuário antes de subir em lote.

### Quota: DOIS contadores separados (revisado 2026-07-08)
No console GCP (APIs & Services → YouTube Data API v3 → Quotas) há **duas métricas distintas**:
- **Queries per day = 10.000 unidades/projeto** (leituras 1, `videos.insert` 1.600, `thumbnails.set` 50 — custo por chamada).
- **Video uploads per day = 100/projeto** — contador SEPARADO, NÃO é derivado das 10k. Constatado no console em 2026-07-08: no mesmo dia o painel mostrava **2/100** uploads e ~100/10.000 queries usados (2 uploads NÃO consumiram 2×1.600 das queries). A premissa antiga de "~6 uploads/dia = 10k÷1600" estava errada para este projeto.
- **Teto prático de upload = 100/dia.** `daily_upload_limit` por conta em `config/accounts.json` (setado **100**). Excedente fica `queued`, ordenado por score, sobe no dia seguinte. `quotaExceeded` real da API (se bater qualquer um dos dois) também re-enfileira sem gastar unidade.

### Aumentar a quota (auditoria + Quota Extension)

**Importante:** a verificação de **"recursos avançados"** do canal (telefone → libera vídeo > 15 min, miniatura personalizada, live) **NÃO** aumenta a quota da API. Quota é do **projeto GCP**, não do canal. São coisas separadas.

Três caminhos:

**1. Auditoria + Quota Extension (oficial, gratuito, ~semanas).** O único jeito de subir a quota do mesmo projeto.
- Pré-requisitos: (a) app do **OAuth consent screen publicado** (status *In production*, não *Testing* — isso também acaba com a expiração de 7 dias do token); (b) **Privacy Policy URL** + **Homepage URL** públicas e acessíveis; (c) app em conformidade com os *YouTube API Services Terms* + *Developer Policies* + *Branding Guidelines*.
- Passos: Google Cloud Console → **APIs & Services → YouTube Data API v3 → Quotas & System Limits** → link *"apply for higher quota"* → abre o **"YouTube API Services – Audit and Quota Extension Form"** (Google Form).
- O form pede: **project number** (Console → dashboard), descrição do caso de uso, quais métodos da API você chama e por quê, se/como exibe dados do YouTube na UI, screenshots ou vídeo demonstrando o fluxo, política de dados, e a **quota diária pedida + justificativa** (nº de canais, volume/dia).
- Google revisa e pode pedir ajustes/rejeitar; aprovação concede a quota justificada.

**2. Múltiplos projetos GCP (multiplicador imediato).** Cada projeto = +10k/dia próprios. 1 projeto por canal/conta. A arquitetura multi-conta já suporta: `config/accounts.json` com `credentials_dir` isolado por conta, cada uma apontando pro seu projeto. Google desencoraja fatiar só pra furar quota — usar quando há canais/finalidades realmente distintos.

**3. Reduzir custo — não existe.** `videos.insert` fixo 1.600.

**⚠️ Risco de compliance específico deste projeto:** os clips são **cortes de vídeos de terceiros** (canais originais). A auditoria (e o próprio YouTube) checa direitos sobre o conteúdo — repost de terceiros sem autorização/transformação suficiente pode reprovar a auditoria E gerar strike de copyright, independentemente da quota. Ter direito/parceria sobre a fonte, ou transformação clara (comentário/edição), reduz o risco.

### Token em modo Testing expira em 7 dias
Com o OAuth consent screen em **Testing**, o refresh token **expira em 7 dias**. Sintoma típico: `invalid_grant` / `Token has been expired or revoked` no upload. Correção: re-rodar `python scripts/auth.py --platform youtube --account <conta>` e consentir de novo no navegador. Publicar o app (verificação da Google) elimina a expiração, mas não vale o custo na POC.

### Detecção de Shorts é automática
Não existe flag de Short na API: vídeo vertical/quadrado com ≤ 3 min vira Short automaticamente. O output do formato `short` (1080x1920, <60s) é classificado sem ação extra; 16:9 permanece long-form mesmo curto.

## Download bloqueado por anti-bot ("Sign in to confirm you're not a bot")

O YouTube bloqueia downloads sem sessão em muitos IPs residenciais. Constatado neste ambiente (2026-07): todos os `player_client` falham sem credencial, e `--cookies-from-browser` NÃO funciona com Chrome/Edge atuais no Windows (criptografia app-bound, yt-dlp issues #7271/#10927). Cookies exportados manualmente também se mostraram frágeis: uma sessão de teste (poucas dezenas de chamadas em minutos) foi suficiente para o YouTube invalidar o cookie e voltar `LOGIN_REQUIRED` mesmo com o cookie presente. Configuração atual, em camadas:

1. **Runtime JS + solver EJS** (obrigatório, sempre ativo): `js_runtimes` (Node) + `remote_components: ["ejs:github"]` em `core/sources/youtube.py`. O yt-dlp moderno não entrega NENHUM formato sem resolver os desafios JS do YouTube; o solver é componente oficial do projeto yt-dlp, baixado do GitHub deles e cacheado localmente (autorizado pelo dono do repo). **Node >= 20 é OBRIGATÓRIO** para o solver do desafio **nsig** (n challenge): com um Node EOL o solver falha (`WARNING: n challenge solving failed` → `Only images are available`) e o YouTube devolve **só storyboard, zero formato A/V — mesmo com cookie e PO token válidos**. Sintoma enganoso: `ERROR: Requested format is not available` em TODOS os vídeos (inclusive os que baixavam antes). Aqui o **nvm-for-windows** deixava o v12.22.12 (EOL) como ativo; `core/sources/youtube.py._node_ge20()` agora resolve automaticamente um Node ≥ 20 dentre as versões do nvm (`%APPDATA%\nvm\v*`) — ou defina `YTDLP_NODE` apontando pro node.exe. Constatado 2026-07-08.
2. **Cookies exportados** (principal, detecção automática): extensão "Get cookies.txt LOCALLY" → salvar como `secrets/youtube-cookies.txt` (formato Netscape). Exportar em janela anônima e fechá-la sem deslogar. Sessão é frágil a uso em rajada — evitar rodar dezenas de extrações/testes seguidos contra o mesmo vídeo em poucos minutos; isso sozinho já foi suficiente para invalidar a sessão. Re-exportar quando `LOGIN_REQUIRED`/bot-check voltar.
3. **Plugin PO token** (reserva, instalado e buildado): `bgutil-ytdlp-pot-provider` (pip) + repo em `C:\Users\eduar\bgutil-ytdlp-pot-provider`. Dois modos: HTTP server (`node build/main.js`, porta 4416, recomendado — script mode tem spawn lento e já beirou o timeout de 15s do yt-dlp) ou script mode (auto-detectado, sem daemon, mas mais lento/frágil). PO token não substitui cookies quando o YouTube já retorna `LOGIN_REQUIRED` — só ajuda a passar no bot-check quando a sessão está válida.

**Testado e descartado**: OAuth2 device-flow (`yt-dlp-youtube-oauth2`, PyPI) — falha com HTTP 400 no passo de device code; o repositório está arquivado (jan/2026) com esse bug aberto sem correção desde nov/2024. Não reinstalar.

**Mitigação real de longo prazo**: como toda credencial de download eventualmente expira/é invalidada por uso automatizado, o ganho maior é disciplina de uso — rodar `download.py` uma vez por vídeo (é idempotente, script pula se `source.mp4` já existe) em vez de repetir chamadas de diagnóstico manualmente, e evitar rajadas de teste contra o mesmo `video_id`.

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
