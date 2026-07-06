# Heurísticas de Cortes Virais — Base de Conhecimento

Referência para o subagente planejador de cortes (clip-scout). Aplica-se a transcrições com timestamps word-level.
Contexto de plataforma (2025/2026): Shorts aceita até 3 min (vídeo vertical), mas a performance concentra-se em 20–45s. 50–60% do drop-off acontece nos primeiros 3 segundos; a meta é reter >70% após o 3º segundo. #shorts não é mais obrigatório para classificação (duração + aspect ratio decidem), mas ainda ajuda em busca.

Nomenclatura de formato (a mesma de `core/contracts.py`): **`short`** = vertical 9:16, 1080x1920, 15–59s, legendas queimadas; **`corte`** = horizontal 16:9, 1920x1080, 120–600s, sem legenda queimada.

## 1. Sinais de momento virável (detectáveis na transcrição)

Um trecho é candidato quando exibe 2+ sinais abaixo. Cada sinal tem marcadores textuais objetivos:

| Sinal | O que é | Marcadores na transcrição |
|---|---|---|
| **Hook forte** | Primeira frase prende em ≤3s | Pergunta direta, afirmação absoluta ("ninguém te conta que..."), número específico ("perdi R$ 40 mil"), contradição ("todo mundo faz X errado"), promessa ("o segredo é...") |
| **História autocontida** | Arco completo: setup → tensão → resolução | "uma vez...", "aí eu...", "quando eu...", mudança de tempo verbal para narrativo, desfecho explícito |
| **Pico emocional** | Emoção intensa e legível | Risadas, exclamações, palavrões (censuráveis), voz elevada (interjeições: "caraca", "meu Deus", "não acredito"), pausas dramáticas seguidas de revelação |
| **Polêmica / opinião forte** | Posição que divide audiência | "eu discordo", "isso é mentira", "impopular, mas...", críticas nominais a práticas/consensos, comparações provocativas |
| **Payoff claro** | Recompensa concreta por assistir | Resposta à pergunta do hook, número final, moral da história, punchline, demonstração de resultado |
| **Loop potencial** | Fim conecta com o começo (rewatch) | Última frase reusa termo da primeira; frase final incompleta que o início "responde" |
| **Utilidade condensada** | Ensina algo acionável em 1 bloco | "faz assim", listas curtas ("3 coisas"), passo a passo verbal, definição contraintuitiva |
| **Identificação** | Espectador se vê no relato | "todo mundo já passou por...", situações cotidianas, dores comuns do nicho |

## 2. Rubrica de score (0–100)

Score = soma ponderada de 4 eixos. Avaliar cada eixo de 0–10 e multiplicar pelo peso. Os 4 eixos correspondem exatamente às chaves do `score_breakdown` de cada clip no `clips.json`: `{"hook": 0-10, "retencao": 0-10, "compartilhabilidade": 0-10, "clareza": 0-10}`. O campo `score` do clip é a soma ponderada (inteiro 0–100).

| Eixo (chave no `score_breakdown`) | Peso | 0–3 | 4–6 | 7–8 | 9–10 |
|---|---|---|---|---|---|
| **`hook`** — força do hook (primeiros 3s do clip) | ×3.5 | começa em contexto/enrolação | frase ok mas genérica | pergunta/afirmação que gera curiosidade | tensão imediata: número, contradição ou promessa irrecusável |
| **`retencao`** — potencial de retenção (estrutura interna) | ×3.0 | divaga, tem "gordura" no meio | arco existe mas com pausas mortas | tensão crescente até o fim | cada frase puxa a próxima; payoff só no final |
| **`compartilhabilidade`** | ×2.0 | interesse de nicho estreito | interessante, mas não "marca amigo" | gera reação ("olha isso") | polêmica/emoção/utilidade que a pessoa QUER repassar |
| **`clareza`** — clareza sem contexto | ×1.5 | depende do resto do vídeo | precisa de 1 frase de contexto | entende-se sozinho | primeiro segundo já situa qualquer estranho |

- Máximo: (10×3.5)+(10×3.0)+(10×2.0)+(10×1.5) = 100.
- **Corte de linha: só propor clips com score ≥ 60.** 75+ = prioridade alta. <60 = descartar.
- **Regra de veto: `clareza` ≤ 3 elimina o clip mesmo com score total alto** — clip incompreensível não performa, independente do resto.

## 3. Duração e escolha de formato

### `short` (9:16 vertical)
- **Ideal: 20–45s. Máximo aceito na POC: 59s.** Abaixo de 15s raramente entrega payoff; acima de 45s exige retenção excepcional.
- Escolher `short` quando: o momento é UMA ideia só (1 história, 1 opinião, 1 dica); o pico emocional/payoff cabe a <45s do hook; funciona com crop central (1 pessoa falando, sem depender de tela/slides largos).

### `corte` (16:9, 2–10 min)
- **Ideal: 3–7 min.** Máximo 10 min.
- Escolher `corte` quando: o assunto precisa de desenvolvimento (debate, explicação com camadas, história longa); há múltiplos picos encadeados no mesmo tema; o valor está na argumentação, não numa frase.

### Regra de decisão para um mesmo momento
1. O payoff cabe em ≤45s a partir do hook? → **`short`.**
2. Não cabe, mas o bloco temático completo tem 2–10 min com ≥2 picos? → **`corte`.**
3. Momento excepcional (score ≥ 85) que funciona nos dois? → **Propor ambos**: `short` com o pico + `corte` com o contexto completo (o short vira funil para o corte).

## 4. Ajuste fino de início e fim (timestamps)

### Início — sempre NO hook
- Nunca começar em: saudação, "então...", "é...", risada residual do assunto anterior, contexto ("como eu tava falando").
- Começar na primeira palavra da frase-hook. Usar timestamps word-level: início = start da primeira palavra − 0.15s (respiro mínimo para não cortar o ataque da fala).
- Se o hook natural está no MEIO do trecho (payoff antes do setup na fala original), considerar reordenação: abrir com a frase de pico e deixar o setup vir depois — só quando a edição não quebra continuidade visual óbvia.

### Meio — cortar gordura
- Remover: "éééé", "tipo assim", repetições da mesma frase, pausas >1.0s sem função dramática, tangentes que não servem ao payoff.
- MANTER pausas dramáticas (<1.5s) antes de revelações — silêncio pré-payoff aumenta retenção.
- Cada corte interno (jump cut) deve emendar em fronteira de palavra (usar timestamps word-level, folga de ±0.05s).

### Fim — no payoff ou no gancho
- Terminar: na última palavra do payoff + 0.3–0.5s, OU numa frase-gancho que force rewatch/comentário ("e o pior nem é isso").
- Nunca terminar em: "né?", "enfim...", início de assunto novo, risada que se esvazia.
- Para loop: se a frase final ecoa o hook, cortar exato no fim da palavra para o replay emendar naturalmente.

## 5. Títulos, descrições e metadados (padrões BR)

### Padrões de título que funcionam (sem clickbait mentiroso)
- **Curiosity gap honesto:** "O erro que quase quebrou a empresa dele" — o vídeo DEVE revelar o erro.
- **Número específico:** "3 sinais de que você está sendo enrolado", "Perdeu R$ 200 mil com isso".
- **Polêmica/posição:** "Faculdade é perda de tempo? A resposta dele surpreende", "Por que ele DISCORDA de todo mundo sobre X".
- **Citação de impacto:** a frase mais forte do clip, entre aspas.
- Regras: ≤ 80 caracteres (100 é o limite, mas mobile trunca); primeira metade carrega a informação; CAPS em NO MÁXIMO 1 palavra; máximo 1 emoji; nunca prometer o que o clip não entrega (mata retenção e o canal).

### Descrição
- `short`: 1–2 linhas. Frase que complementa (não repete) o título + pergunta que puxa comentário + hashtags.
- `corte`: 2–4 linhas. Contexto do episódio, link/crédito do vídeo original, timestamps se houver capítulos.
- Crédito obrigatório ao canal original quando for corte de terceiros.

### Hashtags
- `short`: `#shorts` (opcional para classificação, ainda útil para busca) + 2–3 do nicho em pt-BR (ex.: `#podcast #cortes #empreendedorismo`). Máximo 3–4 no total; excesso dilui.
- `corte`: 3–5 hashtags de nicho, sem `#shorts`.

## 6. Anti-padrões — NUNCA cortar

- **Dependência de contexto anterior:** trechos com "como eu disse antes", "voltando naquilo", pronomes sem referente ("ele" — quem?), respostas cuja pergunta ficou de fora.
- **Inside jokes** e referências internas do canal/grupo que estranho não entende.
- **Áudio ruim:** sobreposição de vozes que impede transcrição confiável (confidence baixa no Whisper), música alta sobre a fala, trechos com palavras faltando na transcrição.
- **Meio de raciocínio:** começar no meio de um argumento ou terminar antes da conclusão — clip sem payoff é dislike.
- **Conteúdo sensível descontextualizado:** declarações que, isoladas, distorcem o que a pessoa disse (risco reputacional e de strike).
- **Trechos protegidos:** música com copyright tocando ao fundo, clipes de terceiros exibidos na tela.
- **Housekeeping:** patrocínio, pedidos de like/inscrição, avisos administrativos do vídeo original.

## 7. Densidade realista de propostas

Por hora de vídeo-fonte (conversa/podcast típico):
- **Candidatos brutos** (score calculado): 10–20.
- **`short` propostos** (score ≥ 60): **4–8**.
- **`corte` propostos:** **2–4**.
- Vídeo fraco (monótono, técnico): pode render 1–2 clips — **não inventar clip para bater cota**; propor menos é correto. **0 clips viáveis é resultado válido** — registre os descartes relevantes em `rejected_notable` e encerre.
- Vídeo excepcional (debate quente, histórias fortes): até 10 shorts, mas ranquear e sinalizar os top 3–5 para publicação; excesso de uploads do mesmo vídeo canibaliza.
