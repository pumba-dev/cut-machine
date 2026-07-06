# Formatos por Rede — Especificações

Specs de render, metadados e publicação por formato/plataforma. Nomenclatura de formato é a de `core/contracts.py` (`CLIP_FORMATS = ("short", "corte")`); os limites duros de duração/resolução vivem em `FORMAT_RULES` — este arquivo documenta o porquê e as regras de plataforma que não cabem em código.

## YouTube

### Formato `short` (YouTube Shorts)
- **Resolução:** 1080x1920 (9:16 vertical), crop central a partir do source 16:9.
- **Duração na POC: 15–59s.** O YouTube aceita Shorts de até 3 min desde 2024, mas a POC limita a 59s por decisão de escopo (crop central + legendas grandes performam melhor em clipes curtos).
- **Detecção de Shorts é automática** — não existe flag na API: vídeo enviado com aspecto vertical (ou quadrado) e duração ≤ 3 min é classificado como Short. O output `short` (1080x1920, <60s) vira Short sem nenhuma ação extra; um 16:9 permanece long-form mesmo se for curto.
- **Legendas queimadas obrigatórias** (spec em `references/estilo-legendas.md`).
- **Zona segura de legenda/elementos visuais:** evitar ~10% do topo e ~25% da base do frame — a UI do Shorts (título do vídeo, nome do canal, botões de like/comentário/compartilhar, descrição) cobre essas regiões no player. O estilo ASS do projeto (Alignment 2 + MarginV 550) já posiciona o texto no centro-baixo, dentro da zona segura.
- **Hashtags:** `#shorts` é opcional para classificação (duração + aspect ratio decidem), mas ainda ajuda em busca — vale incluir. Somar 2–3 hashtags de nicho em pt-BR. **Máximo 3–4 no total**; excesso dilui.
- **Descrição:** 1–2 linhas — frase que complementa o título + pergunta que puxa comentário + hashtags.

### Formato `corte` (vídeo padrão 16:9)
- **Resolução:** 1920x1080 (16:9), sem crop e sem legenda queimada.
- **Duração:** 120–600s (2–10 min); ideal 3–7 min.
- **Descrição:** 2–4 linhas com contexto do episódio, **crédito/link do vídeo original** (obrigatório quando o corte é de canal de terceiros) e timestamps se houver capítulos.
- **Hashtags:** 3–5 de nicho, **sem** `#shorts`.

### Limites de metadados (YouTube Data API v3)

| Campo | Limite da API | Recomendado |
|---|---|---|
| `title` | 100 caracteres; não aceita `<` nem `>` | ≤ 80 (mobile trunca; informação na primeira metade) |
| `description` | 5000 caracteres | curta e direta; links completos com `https://` |
| `tags` | ~500 caracteres somados | poucas e relevantes; hashtags vão no fim da descrição/título, tags são campo separado |

Campos fixos do bloco `publish` do clips.json: `privacy: "private"` (ver `references/youtube-api.md`), `category_id: "22"` (People & Blogs) por padrão, `made_for_kids: false`.

## TikTok (futuro)

Não implementado na POC. A arquitetura já está pronta para isso: o bloco `publish` de cada clip é parametrizado por `platform` + `account`, `config/accounts.json` aceita contas de qualquer plataforma e `core/publishers/` tem registry por plataforma. Basta implementar um `Publisher` com `platform = "tiktok"` (`authenticate()` + `upload()`) e registrar a conta — nenhum schema muda.

## Instagram Reels (futuro)

Não implementado na POC. Mesmo caminho do TikTok: novo `Publisher` com `platform = "instagram"` + conta em `config/accounts.json`. O render `short` (1080x1920, legendas queimadas) já é compatível com o formato Reels.
