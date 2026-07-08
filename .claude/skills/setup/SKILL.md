---
name: setup
description: Prepara o ambiente do zero - instala ffmpeg e dependencias Python, roda smoke tests (CUDA, filtro ass, compileall), guia a criacao do projeto GCP/OAuth do YouTube e executa a primeira autenticacao. Uso - /setup
---

# /setup — preparar o ambiente

Execute os passos abaixo **em ordem**, verificando antes de instalar (idempotente: se um passo ja esta ok, pule e informe). Ao final, apresente um resumo do que foi instalado, do que ja existia e do que ficou pendente.

## 1. ffmpeg

1. Verifique se ja existe: `ffmpeg -version`. Se funcionar, pule a instalacao.
2. Se nao existir: `winget install --id=Gyan.FFmpeg -e`
3. Atencao: apos instalar via winget, o PATH so atualiza em um terminal novo. Se `ffmpeg -version` continuar falhando na sessao atual, avise o usuario que pode ser preciso reiniciar o terminal/Claude Code antes de prosseguir.

## 2. Dependencias Python

```
pip install -r requirements.txt
```

## 3. Smoke tests

Rode os quatro testes e reporte o resultado de cada um:

1. `ffmpeg -version` — deve imprimir a versao.
2. `ffmpeg -filters | findstr ass` — deve listar o filtro `ass` (necessario para queimar legendas). Se nao aparecer, o build do ffmpeg nao tem libass: reinstalar com o pacote Gyan.FFmpeg (build full).
3. `python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` — esperado `1` (GTX 1660 SUPER). Se imprimir `0`, a transcricao vai cair em CPU (funciona, porem lenta, e o transcribe.py usa fallback modelo `small`); avise o usuario e siga em frente.
4. `python -c "import sherpa_onnx; print(sherpa_onnx.__version__)"` — deve imprimir a versao (>= 1.10.28). Necessario para a diarizacao de falantes (cor por falante nas legendas). Os modelos ONNX (~103 MB) sao baixados sob demanda na primeira transcricao, para `models/diarization/` — nao baixe aqui. Se falhar o import, `pip install sherpa-onnx`.
5. `python -m compileall core scripts -q` — exit code 0, sem output. Erro aqui indica problema de sintaxe no repo; pare e reporte.

## 4. Projeto GCP + credenciais do YouTube (acao do usuario)

Guie o usuario pelo walkthrough resumido abaixo. Detalhes completos (prints de tela, custos de quota, limitacoes) estao em `references/youtube-api.md` — leia esse arquivo e use-o como fonte se o usuario tiver duvidas.

1. Acessar https://console.cloud.google.com e criar um projeto novo.
2. Ativar a **YouTube Data API v3** (APIs & Services > Library).
3. Configurar a **OAuth consent screen**: tipo External, modo **Testing**, adicionar o e-mail do proprio usuario como *test user*.
   - Importante: em modo Testing o refresh token **expira em 7 dias** — sera preciso re-rodar `scripts/auth.py` semanalmente (o /status alerta).
4. Criar credencial **OAuth client ID** do tipo **Desktop app** e baixar o JSON.
5. Crie o diretorio de credenciais da conta default (`config/accounts.json` -> conta `principal`):
   - `secrets/youtube/principal/`
   - Oriente o usuario a salvar o JSON baixado como `secrets/youtube/principal/credentials.json`.
   - **Nunca leia nem imprima o conteudo desse arquivo** — apenas confirme que ele existe.

## 5. Primeira autenticacao

Com `credentials.json` no lugar:

```
python scripts/auth.py --platform youtube
```

O script abre o browser para o consentimento OAuth e salva `token.json` em `secrets/youtube/principal/`. A ultima linha do stdout e JSON `{"ok": ...}` — confira `ok: true`. Se `token.json` ja existir e for valido, o script emite `{"ok": true, "skipped": true}` (nao refaca nada).

## Resumo final

Apresente uma tabela: passo | status (ok / ja existia / pendente / falhou) | observacao. Se algo ficou pendente (ex.: credentials.json ainda nao colocado), diga exatamente o que o usuario precisa fazer e que pode re-rodar `/setup` — o skill e idempotente.
