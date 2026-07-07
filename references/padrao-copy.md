# Padrão editorial de copy — título, descrição e tags

Fonte única do padrão de copy do canal. Em conflito com qualquer outra referência
(`heuristicas-virais.md`, `formatos-redes.md`), **este arquivo vence**. As regras de
quantidade/formato daqui têm espelho verificado em código (`core/contracts.py`:
`validate_plan` para erros duros, `lint_copy` para avisos) — mudou aqui, mude lá.

## Título

Template obrigatório (os separadores são ` | ` — espaço, pipe, espaço):

```
CATEGORIA | <título do clip> | #hashtag1 #hashtag2
```

- `CATEGORIA`: **uma** palavra-tema em MAIÚSCULAS, escolhida por vídeo conforme o
  conteúdo dominante — a MESMA para todos os clips do mesmo vídeo. Exemplos:
  POLÍTICA, ECONOMIA, ELEIÇÕES, NEGÓCIOS, TECNOLOGIA, SAÚDE, HISTÓRIA. Até 12 chars.
- Miolo: segue os padrões de `heuristicas-virais.md` §5 (curiosity gap honesto,
  número específico, polêmica/posição, citação de impacto entre aspas). CAPS no
  miolo em no máximo 1 palavra; nunca prometer o que o clip não entrega.
- 1–2 hashtags de nicho/tema no final. **SEM `#shorts` no título** (vai na
  descrição; aqui só desperdiça 7 chars).
- Proibido `<` e `>` (a API do YouTube rejeita).

Orçamento de caracteres (limite duro da API: 100):

| Peça | Chars |
|---|---|
| CATEGORIA | <= 12 |
| ` \| ` x2 | 6 |
| miolo | <= 55 |
| 1–2 hashtags | <= 25 |
| **Total** | **alvo <= 85** (aviso acima); 100 = erro |

Mobile trunca ~70 chars: CATEGORIA + miolo carregam toda a informação; as
hashtags no fim são o sacrificável.

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

## Escopo

- Padrão vale para vídeos processados a partir da adoção (2026-07-07).
  **Nunca** reescrever copy de clips com status diferente de `planned`.
- `metadata.json` de cada clip deriva `hashtags` do bloco 4 da descrição
  (automático, `core/contracts.py`); o copywriter não escreve nele.
