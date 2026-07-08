# Padrão editorial de copy — título, descrição e tags

Fonte única do padrão de copy do canal. Em conflito com qualquer outra referência
(`heuristicas-virais.md`, `formatos-redes.md`), **este arquivo vence**. As regras de
quantidade/formato daqui têm espelho verificado em código (`core/contracts.py`:
`validate_plan` para erros duros, `lint_copy` para avisos) — mudou aqui, mude lá.

## Título

**Formato: `<GANCHO EM CAIXA ALTA> | #tag #tag #tag`** (revisado 2026-07-08 v2 —
volta o ` | #tags`, mas **sem a CATEGORIA** que atrapalhava o gancho).

```
GANCHO CURTO E FORTE EM CAIXA ALTA | #tag1 #tag2 #tag3
```

- **Texto (antes do ` | `)**: o gancho puro em **CAIXA ALTA**, seguindo
  `heuristicas-virais.md` §5 (curiosity gap honesto, número, polêmica, citação).
  **Sem categoria**, sem hashtags no meio do texto. Nunca prometer o que o clip
  não entrega.
- **Exatamente 3 hashtags** depois do ` | `, minúsculas sem acento:
  - **short**: `#shorts` é OBRIGATÓRIA (primeira) **+ 2** das `default_hashtags`
    da conta, as mais coerentes com o clip.
  - **corte**: **3** das `default_hashtags` da conta, coerentes com o clip (SEM
    `#shorts`).
  - As hashtags que não são `#shorts` saem SEMPRE da lista `default_hashtags` de
    `config/accounts.json`.
- **`#shorts` em short é obrigatória no título E no vídeo** (bloco 4 da
  descrição) — as duas.
- Proibido `<` e `>` (a API do YouTube rejeita).

Orçamento: **limite duro da API 100 chars** (texto + ` | ` + 3 hashtags juntos).
As hashtags comem ~25–35 chars, então mire o **texto em <= ~50 chars** para caber.
Aviso de lint acima de 100.

### Variantes para teste A/B (`title_alts`)

Pool ranqueado de 6–10 variantes (best-first), **cada uma no MESMO formato**
`<TEXTO CAIXA ALTA> | #tag #tag #tag` — **as mesmas 3 hashtags** do `title` (só o
TEXTO muda entre as variantes), **minúsculas e SEM acento** (`#politica`, não
`#política`). O `title` recebe a variante mais forte (rank 1); **`title_alts` são
as DEMAIS variantes — NÃO repita o `title` dentro de `title_alts`** (o pool
`title` + `title_alts` tem que ser todo distinto).

- **Cada variante ataca um ângulo diferente** do MESMO clip (curiosity gap,
  número/dado, contradição, citação entre aspas, pergunta direta, callout
  ("VOCÊ...", "NINGUÉM TE CONTA..."), perda/medo, autoridade/bastidor).
- **Ranqueie** por potencial de CTR (a mais forte primeiro = vira o `title`).
- **Como testar:** o YouTube Studio ("Testar e comparar") rotaciona **até 3 títulos**
  e mede retenção/CTR — recurso **só do Studio, não da API**. Use as 3 primeiras do
  pool no teste nativo; as demais ficam de reserva. A Data API não rotaciona título.

### Palavras chamativas (power words pt-BR)

Vocabulário de alto CTR para os títulos/variantes — usar com **honestidade** (a
palavra tem que refletir o clip, senão vira clickbait e mata o canal):

- **Revelação/choque:** REVELADO, EXPÔS, ESCANCAROU, A VERDADE SOBRE, O SEGREDO,
  NINGUÉM TE CONTA, BASTIDORES, VAZOU, ADMITIU, CONFESSOU.
- **Conflito/polêmica:** DETONOU, ALFINETOU, RESPONDEU, CALOU, DESMASCAROU, CANSOU,
  RASGOU, POLÊMICA, GUERRA, x VERSUS y.
- **Curiosidade/urgência:** POR QUE, O QUE NINGUÉM VIU, ATÉ O FIM, O ERRO QUE,
  O MOMENTO EM QUE, VOCÊ NÃO VAI ACREDITAR (só se o clip sustenta), AGORA.
- **Número/perda:** cifras (R$), porcentagens, "3 SINAIS", "PERDEU TUDO",
  "CUSTOU CARO", "O PREÇO DE".
- Evite: caps-lock gritado sem gancho, promessa não cumprida, sensacionalismo que
  o clip não entrega, e repetir a MESMA palavra em todas as variantes.

## Descrição

**4 blocos, nesta ordem, separados por linha em branco** (`\n\n`):

```
🔥 Curtiu? Deixa o LIKE 👍, comenta o que achou 💬 e se INSCREVE no canal pra não perder os próximos cortes!

Vídeo original: <source.title> — <source.channel>
<source.url>

<conteúdo do clip>
```

seguido do bloco final de hashtags (ver abaixo).

1. **CTA fixa** — frase idêntica caractere a caractere em TODOS os vídeos.
   Espelho em código: `contracts.CTA_FIXA` (manter em sincronia com este arquivo).
2. **Crédito/link do vídeo original** — título, canal e URL (`source.*` do
   `clips.json`). Obrigatório em ambos os formatos.
3. **Conteúdo** — `short`: 1–2 linhas que complementam (não repetem) o título +
   pergunta que puxa comentário; `corte`: 2–4 linhas de contexto do episódio.
4. **Hashtags** — `short`: `#shorts` + 2–4 de nicho pt-BR; `corte`: 3–5 de nicho,
   SEM `#shorts`. Não confundir com `tags` (campo separado, ver abaixo).

Proibido `<` e `>` em QUALQUER bloco da descrição (a API do YouTube rejeita em
título e descrição). Escreva "menor que"/"maior que" ou use "menos de R$ 5".

## Tags

**10 a 15 tags por clip**, minúsculas, sem `#`, do específico para o genérico:

1. Assunto, pessoas e termos exatos ditos na **transcrição do clip** (o que
   alguém buscaria para achar ESTE corte).
2. Padrões das hashtags mais usadas no contexto/nicho do vídeo.
3. Completar até 10–15 com as **`default_hashtags` da conta** em
   `config/accounts.json` (removendo o `#`) — lista curada por canal, coerente
   com o `niche` da conta.

Orçamento da API: soma <= 500 chars, contando **+2 por tag com espaço** (a API
envolve em aspas). 15 tags de ~20 chars ≈ 330 — folga. Se estourar, corte do FIM
(as genéricas valem menos que as específicas).

As hashtags do bloco 4 da descrição e do título seguem as mesmas duas fontes:
específicas da transcrição primeiro, `default_hashtags` da conta para completar.
A lista padrão de cada canal vive em `config/accounts.json` (campo
`default_hashtags` da conta) — estender/ajustar lá, nada muda em código.
Fallback genérico se a conta não tiver lista: #shorts #cortes #podcast #brasil
#viral #noticias.

Regras de uso das `default_hashtags` (pesquisa 2026):

- NUNCA despeje a lista inteira num vídeo: escolha as 3–5 mais relevantes ao
  clip + as específicas da transcrição, dentro das quantidades do bloco 4.
- Em short, `#shorts` vem PRIMEIRO no bloco: só as 3 primeiras hashtags da
  descrição aparecem acima do título no player.
- Grafia minúscula e SEM acento (#politica, #eleicoes2026) — a versão sem
  acento domina a busca; não duplicar variantes acentuadas.
- Hashtag de pessoa (#lula, #bolsonaro, #kimkataguiri, #gutozacarias,
  #amandavettorazzo...) só quando a pessoa é citada/aparece na transcrição do
  clip — nunca como padrão.
- Hashtags classificam o tópico, não amplificam: a distribuição real vem de
  retenção e engajamento. Não sacrifique a copy por hashtag.

## Miniatura (`thumbnail_text`)

Texto queimado na miniatura (thumbnail) do clip — **não** é o título, é
linguagem de thumbnail: curta, emocional, alto contraste. Objeto no `clips.json`:

```json
"thumbnail_text": {"impact": "PERDI R$ 40 MIL", "hooks": ["ELE ADMITIU TUDO!", "VOCÊ FARIA IGUAL?"]}
```

- `impact`: a frase MAIS forte do clip (a "citação de impacto" da
  `heuristicas-virais.md` §5 — número, promessa, contradição). **CAIXA ALTA,
  <= 40 chars**, pontuação mínima. É a manchete grande AMARELA no topo da imagem
  (ocupa boa parte da largura).
- `hooks`: **2–3** ganchos curtos (**<= 30 chars** cada), CAIXA ALTA. Cada um é
  renderizado como um **CHIP separado** na faixa inferior (caixas alternando
  preto/amarelo, com folga) — o usuário tem que ler 3 frases DISTINTAS, não um
  bloco. Por isso:
  - **NÃO copie a transcrição literal** — reformule para o máximo de impacto.
  - Cada gancho é OU (a) uma **afirmação com `!`** no fim (ex.: "ELE ADMITIU
    TUDO!", "PERDEU R$ 40 MIL!", "ACABOU A AMIZADE!") OU (b) uma **pergunta
    aberta chamativa** com `?` (ex.: "ELE TENTOU UM GOLPE DE ESTADO?", "QUEM
    PAGOU A CONTA?", "VOCÊ FARIA IGUAL?").
  - **Varie os tipos** (misture afirmação-`!` e pergunta-`?`); não repita o
    `impact`.
- Sem `#`, sem `<`/`>`. Acentos pt-BR OK (a fonte renderiza Ã/Ç/É).
- Curiosidade HONESTA — a afirmação/resposta aparece no clip. **Nunca** prometer
  o que não aparece. Vale para short e corte.
- Espelho de avisos em código: `contracts.lint_copy` (impact vazio/longo, hooks
  fora de 2–3). Ausência não bloqueia: o render tem fallback para `hook_text`.

## Escopo

- Padrão vale para vídeos processados a partir da adoção (2026-07-07).
  **Nunca** reescrever copy de clips com status diferente de `planned`.
- `metadata.json` de cada clip deriva `hashtags` do bloco 4 da descrição
  (automático, `core/contracts.py`); o copywriter não escreve nele.
