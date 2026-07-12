# Formatos por Rede — Especificações

Specs de render, metadados e publicação por formato/plataforma. Nomenclatura de formato é a de `core/contracts.py` (`CLIP_FORMATS = ("short", "corte")`); os limites duros de duração/resolução vivem em `FORMAT_RULES` — este arquivo documenta o porquê e as regras de plataforma que não cabem em código.

## YouTube

### Formato `short` (YouTube Shorts)
- **Resolução:** 1080x1920 (9:16 vertical). Sem crop: o vídeo original (16:9) inteiro é escalado numa **janela** (1020×574) sobre uma **moldura fixa de marca** (arte PNG por conta em `brand.short_frame` ou cor chapada de fallback), sem cortar imagem. Substituiu o antigo fundo blur (animado, enjoava). **Toda** a marca (nome/número/@handle) e as CTAs (curtir/comentar/inscrever) já vêm **embutidas na própria arte PNG** (estética 8-bit); o render só compõe PNG + vídeo + legendas — não desenha texto por cima. Spec em `references/estilo-legendas.md` ("Moldura do short") + `core/render/short_frame.py`.
- **Duração do conteúdo: 30–165s (alvo média ~60s).** O YouTube aceita Shorts de até 3 min (180s) desde 2024. O teto de 165s é do conteúdo (`end-start`): reserva ~15s para intro (~0.5s) + vinheta de fim (~10s) → mp4 final ≤180s. O floor de 30s evita shorts pequenos demais (payoff raso).
- **Detecção de Shorts é automática** — não existe flag na API: vídeo enviado com aspecto vertical (ou quadrado) e duração ≤ 3 min é classificado como Short. O output `short` (1080x1920, <60s) vira Short sem nenhuma ação extra; um 16:9 permanece long-form mesmo se for curto.
- **Legendas queimadas obrigatórias** (spec em `references/estilo-legendas.md`).
- **Zona segura de legenda/elementos visuais:** evitar ~10% do topo e ~25% da base do frame — a UI do Shorts (título do vídeo, nome do canal, botões de like/comentário/compartilhar, descrição) cobre essas regiões no player. O estilo ASS do projeto (Alignment 2 + MarginV 550) já posiciona o texto no centro-baixo, dentro da zona segura.
- **Hashtags:** `#shorts` é opcional para classificação (duração + aspect ratio decidem), mas ainda ajuda em busca — vale incluir na descrição. Quantidade e seleção: ver `references/padrao-copy.md`.
- **Descrição:** estrutura (blocos, tamanho, CTA, hashtags) definida em `references/padrao-copy.md`.

### Formato `corte` (vídeo padrão 16:9)
- **Resolução:** 1920x1080 (16:9), sem crop e sem legenda de fala.
- **Moldura de marca:** o vídeo é reduzido e centralizado dentro de uma moldura preta com rim amarelo (`#FFD93D`) e uma faixa inferior com o CTA `"Curta e se inscreva no canal"` (configurável por conta em `brand`). Padding, não crop — nada do vídeo é cortado. Spec em `references/estilo-legendas.md` ("Texto de marca do corte") + `core/render/branding.py`.
- **Duração:** 480–600s (8–10 min); ideal 9–10 min. **Preferência forte por ≥8 min:** o YouTube só habilita mid-roll ads (monetização) em vídeos ≥8 min — cortes mais curtos reprovam em `FORMAT_RULES`. Ver `references/heuristicas-virais.md` para a regra de decisão de duração.
- **Descrição:** estrutura e tamanho em `references/padrao-copy.md` (inclui o crédito/link do vídeo original, obrigatório quando o corte é de canal de terceiros); somar timestamps se houver capítulos.
- **Hashtags:** **sem** `#shorts`; quantidade em `references/padrao-copy.md`.

### Limites de metadados (YouTube Data API v3)

| Campo | Limite da API | Recomendado |
|---|---|---|
| `title` | 100 caracteres; não aceita `<` nem `>` | gancho puro em CAIXA ALTA; `corte` sem tag nenhuma, `short` só ` \| #shorts` (`references/padrao-copy.md`); alvo ≤ 70 (mobile trunca) |
| `description` | 5000 **bytes** (UTF-8), não caracteres — a API conta bytes | curta e direta; links completos com `https://` |
| `tags` | 500 caracteres somados (tag com espaço conta +2) | 10–15 tags (`references/padrao-copy.md`), soma ≤ 500; hashtags vão no fim da descrição/título, tags são campo separado |

Campos do bloco `publish` do clips.json: `privacy: "public"` por padrão (revisado 2026-07-08; `private`/`unlisted` por clip só para exceções — ver `references/youtube-api.md`), `category_id: "22"` (People & Blogs) por padrão, `made_for_kids: false`.

### Miniatura (thumbnail)

Gerada localmente no render (`core/render/thumbnail.py`) para **ambos os formatos**: um frame chamativo do clip (timestamp `thumbnail_ts` do clip-scout) + frase de impacto e ganchos (`thumbnail_text` do copywriter). Arquivo `<clip_id>.thumb.jpg` na pasta do clip; path em `render.thumbnail_path`.

- **Resolução:** `corte` **1280x720** (16:9, tamanho recomendado), `short` **1080x1920** (vertical). Ambas < 2MB (JPG q2).
- **Upload:** primariamente **manual no YouTube Studio** (upload via API fica locked-private). O `upload_clip.py` ainda tenta `thumbnails.set` **best-effort** (custa 50 unidades; exige canal verificado por telefone) — falha vira aviso, não derruba o upload. Ver `references/youtube-api.md`.
- **Texto:** spec em `references/estilo-legendas.md` ("Texto da miniatura"); padrão das frases em `references/padrao-copy.md` ("Miniatura").

## TikTok (futuro)

Não implementado na POC. A arquitetura já está pronta para isso: o bloco `publish` de cada clip é parametrizado por `platform` + `account`, `config/accounts.json` aceita contas de qualquer plataforma e `core/publishers/` tem registry por plataforma. Basta implementar um `Publisher` com `platform = "tiktok"` (`authenticate()` + `upload()`) e registrar a conta — nenhum schema muda.

## Instagram Reels (futuro)

Não implementado na POC. Mesmo caminho do TikTok: novo `Publisher` com `platform = "instagram"` + conta em `config/accounts.json`. O render `short` (1080x1920, legendas queimadas) já é compatível com o formato Reels.
