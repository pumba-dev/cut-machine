# Padrão editorial de copy — título, descrição e tags

Fonte única do padrão de copy **universal** (vale para TODOS os canais). Em conflito com
qualquer outra referência (`heuristicas-virais.md`, `formatos-redes.md`), **este arquivo
vence**. As regras de quantidade/formato daqui têm espelho verificado em código
(`core/contracts.py`: `validate_plan` para erros duros, `lint_copy` para avisos) — mudou
aqui, mude lá.

**Multi-canal:** este arquivo é agnóstico de nicho — princípios, formato e limites que
valem para qualquer canal. O que é **específico de nicho** (arquétipos próprios, exemplos
de gancho com nomes reais, hashtags de tema, avisos legais) vive em
`references/copy/<perfil>.md`, onde `<perfil>` = campo `copy_profile` da conta em
`config/accounts.json` (ex.: `politica`, `financas`). O copywriter lê **os dois**: este +
o do perfil da conta. Conta sem `copy_profile` roda só com este (universal). Os exemplos
abaixo são **ilustrativos/neutros** — o caso real, com nomes e citações do nicho, vem do
arquivo de perfil.

## Objetivo e prioridades

O copywriter **não resume o vídeo** — resumo é trabalho da descrição, não do gancho. O
objetivo é maximizar, nesta ordem: CTR -> retenção -> compartilhamentos -> comentários ->
tempo de exibição. **SEO é secundário**: em conflito entre SEO e CTR, CTR vence.

Hierarquia de toda copy (título, `title_alts`, `thumbnail_text`): **Emoção > Curiosidade >
Clareza > Especificidade > SEO.** Nunca sacrificar emoção para deixar o título mais
descritivo.

**Antes de escrever qualquer título**, responda mentalmente (o raciocínio guia o texto
final, não precisa ser registrado em lugar nenhum):

- Qual é o momento mais forte do clip?
- Qual frase gera a maior reação emocional?
- Qual é o maior conflito?
- Existe uma fala memorável, uma contradição, uma revelação ou uma consequência importante?
- Existe uma pergunta que naturalmente surge na cabeça do espectador?

O título nasce dessas respostas — nunca do resumo do vídeo.

## Regra de ouro

A função da copy não é informar — é fazer a pessoa sentir que **precisa** clicar. O vídeo
entrega a informação prometida depois do clique.

- **Nunca afirme o que o conteúdo não sustenta.** Nunca apresente especulação como fato.
- **Nunca atribua crime, ilegalidade ou intenção a alguém sem que isso esteja explicitamente
  sustentado pelo conteúdo ou por fatos verificáveis** — em qualquer nicho que fale de pessoas
  ou instituições nomeadas (figuras públicas, empresas, gestores) isso não é só tom, é risco
  reputacional e legal real (difamação). Avisos legais próprios de cada nicho:
  `references/copy/<perfil>.md`.
- A intensidade emocional deve **aumentar o interesse**, nunca **alterar o significado** do
  que foi dito.

Isso vale igual para título, `title_alts` e `thumbnail_text`.

## Título

**Formato depende do formato do clip** (revisado — corte sem tag nenhuma no
título, short só com `#shorts`; as hashtags de nicho continuam existindo no
bloco 4 da descrição e no campo `tags`, então tirá-las do título não reduz
descoberta, só limpa o título):

```
corte: GANCHO CURTO E FORTE EM CAIXA ALTA
short: GANCHO CURTO E FORTE EM CAIXA ALTA | #shorts
```

- **Texto**: o gancho puro em **CAIXA ALTA**, seguindo `heuristicas-virais.md`
  §5 (curiosity gap honesto, número, polêmica, citação). **Sem categoria**, sem
  hashtags no meio do texto. Nunca prometer o que o clip não entrega — **e se a
  promessa só se cumpre muito tarde no clip, troque de gancho** em vez de forçar
  uma promessa que demora demais a pagar.
- **`corte`**: só o gancho. **Nenhum ` | `, nenhuma hashtag** no título — as
  hashtags de nicho vivem no bloco 4 da descrição e no campo `tags`.
- **`short`**: gancho + ` | #shorts` — **só essa hashtag, fixa, sem completar
  com mais nenhuma**. `#shorts` é obrigatória no título E no vídeo (bloco 4 da
  descrição) — as duas.
- Proibido `<` e `>` (a API do YouTube rejeita).

Orçamento: **limite duro da API 100 chars**. `corte` não perde chars com tag
(texto pode ir quase até 100); `short` perde só os ~11 chars de ` | #shorts`.
Em ambos, mire o **texto em <= ~70 chars** (`TITLE_RECOMMENDED`, mobile trunca
por volta daí). Aviso de lint acima de 100.

### Biblioteca de hooks (arquétipos)

Todo título e toda variante de `title_alts` usa um destes arquétipos. A diversidade
obrigatória (ver Variantes abaixo) é entre arquétipos, não só entre palavras:

- **Curiosidade** — O QUE NINGUÉM PERCEBEU, O DETALHE ESCONDIDO, NINGUÉM ESPERAVA ISSO,
  A VERDADE SOBRE...
- **Revelação** — ELE ADMITIU..., ELE REVELOU..., ESCANCAROU..., CONFESSOU...
- **Conflito** — DETONOU..., RESPONDEU..., CALOU..., PARTIU PRA CIMA..., BATEU DE FRENTE...
- **Contradição** — DISSE UMA COISA... MAS FEZ OUTRA, MUDOU O DISCURSO, VOLTOU ATRÁS...
- **Consequência** — ISSO MUDA TUDO, O PREÇO DISSO, O QUE ACONTECE AGORA, COMO ISSO
  IMPACTA...
- **Pergunta** — POR QUE ISSO ACONTECEU?, O QUE ELE QUIS DIZER?, COMO ISSO TERMINOU?,
  QUEM GANHA COM ISSO?
- **Citação** — a frase mais forte do clip entre aspas, verbatim. Citação crua > resumo
  parafraseado (ver critério de ranking em Variantes abaixo).
- **Número** — dinheiro, porcentagem, quantidade, prazo ou ranking como âncora emocional.
- **Sistema/Inimigo comum** — enquadra um "eles" contra o espectador: O QUE NÃO QUEREM
  QUE VOCÊ VEJA..., A ESTRATÉGIA POR TRÁS DE..., O QUE ESCONDERAM DE VOCÊ... O "inimigo"
  concreto depende do nicho (os alvos e exemplos reais estão em `references/copy/<perfil>.md`).
  **Só use quando a transcrição sustenta especificamente a alegação** (a pessoa realmente
  descreve algo sendo escondido, uma estratégia ou um plano) — nunca fabricar narrativa de
  conspiração que o clip não mostra (Regra de ouro).

### Variantes para teste A/B (`title_alts`)

Pool ranqueado de 6–10 variantes (best-first), **cada uma no MESMO formato do
`title`** (corte: só o gancho; short: gancho + ` | #shorts`) — só o TEXTO muda
entre as variantes. O `title` recebe a variante mais forte (rank 1);
**`title_alts` são as DEMAIS variantes — NÃO repita o `title` dentro de
`title_alts`** (o pool `title` + `title_alts` tem que ser todo distinto).

- **Cada variante usa um arquétipo diferente** da Biblioteca de hooks acima
  (curiosidade, revelação, conflito, contradição, consequência, pergunta, citação,
  número, sistema/inimigo comum) **ou dos arquétipos próprios do nicho** (ver
  `references/copy/<perfil>.md`). Sem clickbait mentiroso. **Diversidade
  obrigatória:** nunca duas variantes com a mesma estrutura de abertura ou o mesmo
  arquétipo — se acontecer, reescreva uma.
- **Ranqueie** por potencial de CTR — e o critério nº1 de CTR é **carga emocional**,
  não precisão descritiva. Entre duas opções igualmente honestas, a que dói mais
  vence, mesmo que a mais "neutra" pareça editorialmente mais completa.
  - **Avalie cada variante** por: emoção, curiosidade, choque, surpresa, medo de
    perder, especificidade, clareza e potencial de compartilhamento. Ordene do
    maior pro menor potencial de CTR combinado — não só pela primeira impressão.
  - **Citação crua > paráfrase educada.** Se o entrevistado usou uma palavra forte
    ("escrota", "vagabundo", "roubo", "furada"), **use a palavra dele entre aspas** em
    vez de suavizar/generalizar — a fala crua bate mais forte que o resumo de aula. Ex.:
    "'ISSO É UM ROUBO', DISPAROU FULANO" vence "COMO O ESQUEMA FUNCIONA, SEGUNDO FULANO".
    Mesma regra vale pra `impact`/`hooks` da miniatura. Exemplos reais por nicho (com
    nomes e citações típicas): `references/copy/<perfil>.md`.
  - **Nomear o alvo/vilão específico > descrever o fenômeno em abstrato.** Cravar o nome
    próprio + a palavra forte lado a lado ("FULANO" + "CORRUPTO", "O BANCO X" + "TE
    ENGANA") cutuca; o enquadramento acadêmico ("COMO FUNCIONA O SISTEMA") não cutuca
    ninguém. Prefira o nome próprio, a cifra exata, a acusação direta — o que dá pra
    alguém discordar/concordar visceralmente — em vez do enquadramento explicativo. Quem
    é o "alvo" típico de cada nicho (instituições, figuras, empresas) está em
    `references/copy/<perfil>.md`.
  - A variante rank 1 é a que um leitor sente ANTES de entender — raiva, choque,
    indignação, alívio. Se a melhor variante do pool ainda soa como manchete de
    jornal, o pool está fraco: refaça mirando a citação ou o alvo mais crus que
    o clip sustenta (sempre dentro do que foi realmente dito — nunca invente).
- **Autocrítica antes de fechar o pool:** para a variante rank 1 (a que vira o
  `title`), pergunte "essa variante desperta emoção antes mesmo de ser
  completamente entendida?". Se a resposta for não, gere novas opções em vez de
  aceitar a que já tem.
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
- **Curiosidade/urgência:** POR QUE, O QUE NINGUÉM VIU, NINGUÉM ESPERAVA, O DETALHE,
  ATÉ O FIM, O ERRO QUE, O MOMENTO EM QUE, VOCÊ NÃO VAI ACREDITAR (só se o clip
  sustenta), AGORA, URGENTE (só quando genuinamente aplicável).
- **Número/perda:** cifras (R$), porcentagens, "3 SINAIS", "PERDEU TUDO",
  "CUSTOU CARO", "O PREÇO DE".
- **Sistema/inimigo comum** (arquétipo acima, mesma ressalva de honestidade):
  A ESTRATÉGIA DELES, O QUE ELES ESCONDEM, O PLANO POR TRÁS. O "eles" concreto e as
  power words próprias do nicho ficam em `references/copy/<perfil>.md`.
- Evite: caps-lock gritado sem gancho, promessa não cumprida, sensacionalismo que
  o clip não entrega, e repetir a MESMA palavra em todas as variantes.

## Anti-padrões (risco de shadowban/desmonetização)

Linguagem extrema derruba alcance/monetização **antes de alguém clicar** — o filtro de
anúncios do YouTube (advertiser-friendly guidelines) pode marcar o vídeo como "limited ads"
ou reduzir a distribuição; nesse caso o CTR do título deixa de importar porque o vídeo já não
é mostrado. Mais sensível em nichos que tocam pessoas/instituições nomeadas (política;
finanças com crítica a empresas/gestores) — avisos próprios do nicho em
`references/copy/<perfil>.md`. Evitar:

- Discurso de ódio, termos discriminatórios ou chamado à violência.
- **Acusação de crime/ilegalidade não sustentada** — liga direto com a Regra de ouro.
- Clickbait comprovadamente falso — além de matar retenção, a própria política de
  metadados enganosos do YouTube penaliza o vídeo.
- "URGENTE"/"ALERTA" vazio e repetido sem fato novo que sustente.
- Caps-lock gritado sem gancho real (já listado em "Evite" acima) — sinaliza spam pro
  classificador de anúncios, não só pro leitor.

**Isso não contradiz a citação crua/nomear o vilão específico já recomendado acima** — o
anti-padrão é *inventar ou escalar* além do que foi dito, não usar a intensidade real que já
está no clipe. Uma citação forte que a pessoa realmente disse é honesta; uma acusação que o
copywriter inventou por cima não é.

### Temas sensíveis (advertiser-friendly)

Em nichos de comentário jornalístico/notícia (política, economia, atualidades) as
**variantes de matar/morrer (matou, mataram, morreu, morte, morto) são LIBERADAS** — fazem
parte da cobertura e são o gancho real de muitos cortes. Não suavize essas palavras:
emburrecem o título e enfraquecem a citação crua. (Nicho que não cobre crime/morte
simplesmente não topa com elas — a regra não atrapalha.)

O que **NÃO** pode aparecer explícito no metadado (o classificador de anúncios do YouTube
marca "limited ads" / reduz a entrega antes de qualquer clique — gate técnico, como o `<`/`>`
que a API rejeita):

- **Assassinato** (e variantes: "assassinado", "assassino") e **arma / armas**.
- **Suicídio / automutilação** — inclui "se matou" descrito como método (o "matou" solto
  segue liberado; o gatilho é o tema suicídio).
- **Crimes hediondos sexuais explícitos** — estupro (e variantes: "estuprou", "estuprador"),
  abuso/exploração sexual, pedofilia/abuso infantil.
- **Conteúdo sexual explícito.**

Nesses casos, **contorne com termo genérico sem mudar o que foi dito** (a Regra de ouro
continua: suaviza o registro, nunca o significado). Vale para **título, `title_alts`,
descrição, `tags` e `thumbnail_text`** (o filtro lê o texto queimado na miniatura por OCR):

| Evite (tema sensível) | Prefira |
|---|---|
| assassinato / assassinado / assassino | crime, ataque, executou |
| arma / armas | equipamento |
| suicídio / se matou (como método) | tirou a própria vida, pôs fim à vida |
| estupro / estuprou / estuprador | crime bárbaro, crime hediondo, abuso, violência |
| abuso sexual / pedofilia | crime contra criança, crime hediondo |
| sexo / sexual (explícito) | intimidade, relacionamento íntimo (só quando necessário) |

- **Reconciliação com a citação crua:** a preferência por citação crua/palavra forte (seção
  Variantes) segue valendo para matar/morrer e para insulto/impacto (escrota, vagabundo,
  palhaçada) — mantenha. Só contorne quando a palavra for de um **tema sensível da lista
  acima** (assassinato, arma, suicídio, crime sexual hediondo, sexo explícito). Ex.: citação
  "ELE ESTUPROU" → "ELE COMETEU UM CRIME BÁRBARO" mantém o peso sem o gatilho.
- **Palavrão pesado:** uma palavra forte genuína numa única citação costuma passar; **não
  empilhe** vários numa mesma copy nem use termos discriminatórios/slur — aí é gatilho.
- **Não use gambiarra de grafia** (su1cídio, quebrar a palavra com espaço) — sinaliza spam pro
  classificador e polui a busca. Prefira o termo genérico real.

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

**10 a 15 tags por clip**, minúsculas, sem `#`, em ordem de prioridade:

1. **Nomes de pessoas citadas/faladas na transcrição do clip** — prioridade
   MÁXIMA, sempre primeiro na lista. É o que faz o clip aparecer em buscas por
   nome de figura pública (o sinal de busca mais forte que existe).
2. Assunto/tema exato dito na **transcrição do clip** (o que alguém buscaria
   para achar ESTE corte, além dos nomes).
3. Padrões das hashtags mais usadas no contexto/nicho do vídeo.
4. Completar até 10–15 com as **`default_hashtags` da conta** em
   `config/accounts.json` (removendo o `#`) — lista curada por canal, coerente
   com o `niche` da conta.

Orçamento da API: soma <= 500 chars, contando **+2 por tag com espaço** (a API
envolve em aspas). 15 tags de ~20 chars ≈ 330 — folga. Se estourar, corte do FIM
(as mais genéricas valem menos que nome/assunto específico — por isso nomes
vão primeiro: `_fit_tags`, `core/publishers/youtube.py`, corta sempre do fim da
lista, então nomes na frente nunca são cortados).

As hashtags do bloco 4 da descrição seguem as mesmas fontes das `tags`:
específicas da transcrição primeiro (pessoas, depois assunto), `default_hashtags`
da conta para completar. O título **não** leva mais hashtags de nicho — ver
seção Título (corte sem tag nenhuma, short só `#shorts`). A lista padrão de
cada canal vive em `config/accounts.json` (campo `default_hashtags` da conta) —
estender/ajustar lá, nada muda em código. Fallback genérico se a conta não
tiver lista: #shorts #cortes #podcast #brasil #viral #noticias.

Regras de uso das `default_hashtags` (pesquisa 2026):

- NUNCA despeje a lista inteira num vídeo: escolha as 3–5 mais relevantes ao
  clip + as específicas da transcrição, dentro das quantidades do bloco 4.
- Em short, `#shorts` vem PRIMEIRO no bloco: só as 3 primeiras hashtags da
  descrição aparecem acima do título no player.
- Grafia minúscula e SEM acento (#politica, #investimentos) — a versão sem
  acento domina a busca; não duplicar variantes acentuadas.
- Hashtag de pessoa/entidade só quando ela é citada/aparece na transcrição do
  clip — nunca como padrão. As hashtags de pessoa/tema típicas de cada nicho vivem em
  `references/copy/<perfil>.md` e no `default_hashtags` da conta.
- Hashtags classificam o tópico, não amplificam: a distribuição real vem de
  retenção e engajamento. Não sacrifique a copy por hashtag.

## Miniatura (`thumbnail_text`)

Texto queimado na miniatura (thumbnail) do clip — **não** é o título, é
linguagem de thumbnail: curta, emocional, alto contraste. Objeto no `clips.json`:

**Miniatura e título NUNCA repetem a mesma mensagem — eles se complementam.** Ex.:
thumb `"ELE ADMITIU"` + título `"O MOMENTO EM QUE ELE MUDOU O DISCURSO"` (a thumb dá o
estopim, o título dá o contexto/consequência). Se `impact`/`hooks` disserem quase a
mesma frase do `title`, reescreva um dos dois.

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
  - **Varie os tipos** — pense cada gancho numa categoria diferente (afirmação-
    revelação, pergunta-curiosidade, consequência, contradição), mas a forma final
    sempre cai em (a) afirmação com `!` ou (b) pergunta com `?` (a regra de
    pontuação acima não muda). Não repita o `impact` nem o arquétipo entre os
    próprios hooks.
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
