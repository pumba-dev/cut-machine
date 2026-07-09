# Música de fundo — conta `principal`

Coloque aqui faixas `.mp3` / `.m4a` / `.wav` / `.ogg` / `.flac`.

**OBRIGATÓRIO: faixas livres de claim** (YouTube Audio Library, Epidemic Sound
licenciado, etc.). Música com copyright faz o Content ID passar a reclamar a
**própria trilha** — troca um problema por outro.

- O render escolhe uma faixa por clip de forma **determinística** (seed = `clip_id`):
  mesmo clip → mesma faixa; clips diferentes → faixas variadas.
- A música entra **baixa** (`music_volume` da conta, default 0.08) e **abaixa
  ainda mais quando alguém fala** (duck reverso por sidechain) — a voz do vídeo
  original é sempre prioridade.
- **Pasta vazia = música desligada** (sem erro). Ligar/desligar = pôr/tirar
  arquivos aqui + `music_dir` no bloco `transform` da conta em `config/accounts.json`.
