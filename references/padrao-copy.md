# Padrão editorial de copy — título, descrição e tags

Fonte única do padrão de copy do canal. Em conflito com qualquer outra referência
(`heuristicas-virais.md`, `formatos-redes.md`), **este arquivo vence**. As regras de
quantidade/formato daqui têm espelho verificado em código (`core/contracts.py`:
`validate_plan` para erros duros, `lint_copy` para avisos) — mudou aqui, mude lá.

## Título

**O título é o gancho puro, TODO EM CAIXA ALTA.** Sem prefixo de categoria, sem
template de pipes, sem hashtags no título (revisado em 2026-07-08 — a categoria e
o formato `CATEGORIA | ... | #tags` atrapalhavam o gancho).

```
GANCHO CURTO E FORTE EM CAIXA ALTA
```

- **CAIXA ALTA obrigatória** no título inteiro — chama mais atenção no feed.
- O texto segue os padrões de `heuristicas-virais.md` §5 (curiosity gap honesto,
  número específico, polêmica/posição, citação de impacto). É a frase que faz a
  pessoa parar e clicar; **nunca prometer o que o clip não entrega.**
- **Sem categoria**, **sem hashtags no título** (hashtags vão só na descrição,
  bloco 4, e nas `tags`). Sem pipes/separadores decorativos.
- Proibido `<` e `>` (a API do YouTube rejeita).

Orçamento: **limite duro da API 100 chars**; **alvo <= 70** (mobile trunca ~70, e
todo o gancho precisa aparecer). Aviso de lint acima de ~85.

### Variantes para teste A/B (`title_alts`)

O `title` é a aposta principal (rank 1). `title_alts` é um **pool ranqueado de até
10 variantes** (best-first) para teste A/B — todas no mesmo padrão (CAIXA ALTA, sem
categoria/hashtags, <= 70 chars, sem clickbait mentiroso).

- **Cada variante ataca um ângulo diferente** do MESMO clip (não são reescritas
  triviais): curiosity gap, número/dado, contradição, citação de impacto entre
  aspas, pergunta direta, callout ("VOCÊ...", "NINGUÉM TE CONTA..."), perda/medo,
  autoridade/bastidor. Quanto mais distintos os ângulos, melhor o teste.
- **Ranqueie** por potencial de CTR (a mais forte primeiro = vira o `title`).
- **Como testar:** o YouTube Studio ("Testar e comparar") rotaciona **até 3 títulos**
  e mede retenção/CTR — recurso **só do Studio, não da API**. Use as 3 primeiras do
  pool no teste nativo; as demais ficam de reserva para trocar depois. A Data API
  não rotaciona título automaticamente.

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
"thumbnail_text": {"impact": "PERDI R$ 40 MIL", "hooks": ["VOCÊ NÃO SABIA?", "ELE ADMITIU"]}
```

- `impact`: a frase MAIS forte do clip (a "citação de impacto" da
  `heuristicas-virais.md` §5 — número, promessa, contradição). **CAIXA ALTA,
  <= 40 chars.** É a manchete grande da imagem.
- `hooks`: **2–3** ganchos ainda mais curtos (**<= 30 chars** cada), CAIXA ALTA,
  que criam curiosidade sem repetir o `impact`.
- Sem `#`, sem `<`/`>`, pontuação mínima (`?`/`!` no máximo). Acentos pt-BR OK
  (a fonte renderiza Ã/Ç/É).
- Coerente com o nicho e com o que o clip mostra — **nunca** prometer o que não
  aparece. Vale para short e corte.
- Espelho de avisos em código: `contracts.lint_copy` (impact vazio/longo, hooks
  fora de 2–3). Ausência não bloqueia: o render tem fallback para `hook_text`.

## Escopo

- Padrão vale para vídeos processados a partir da adoção (2026-07-07).
  **Nunca** reescrever copy de clips com status diferente de `planned`.
- `metadata.json` de cada clip deriva `hashtags` do bloco 4 da descrição
  (automático, `core/contracts.py`); o copywriter não escreve nele.
