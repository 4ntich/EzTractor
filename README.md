# EzTractor

Transforma gravações longas de gameplay (VODs da Twitch, YouTube, Kick ou arquivo enviado) em **clipes verticais 9:16** com legenda animada, gancho e **nota de potencial viral (0–100)**, prontos para TikTok, Reels e Shorts.

App **de uso pessoal**: sem cadastro, sem créditos e sem marca d'água. **Funciona 100% grátis**. A IA paga (Claude) é opcional.

## Instalar no Windows (mais fácil)

1. Abra **Releases** no GitHub (https://github.com/4ntich/EzTractor/releases) e baixe o `EzTractor-Setup-<versão>.exe`.
2. Execute. Não precisa ser administrador nem ter Docker. Se aparecer "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo** (o app não é assinado digitalmente).
3. Abra o **EzTractor** pelo menu Iniciar. Ele abre numa **janela própria**, sem navegador e sem GitHub (usa o WebView2, que já vem no Windows 10 e 11). O menu **EzTractor** tem pasta dos vídeos, configurações e "abrir no navegador". Fechar a janela encerra o app.

Os vídeos, projetos e configurações ficam em `%LOCALAPPDATA%\EzTractor` (o botão **Configurações** da janelinha abre o `config.env`). Desinstalar não apaga esses dados.

## Aparência

Tema padrão **Aero Turquesa**: fundo turquesa escuro, painéis de vidro molhado e botões azuis brilhantes. No topo há o botão de **modo claro/escuro** e o seletor de **temas**: Aero Turquesa, Violeta Neon, Ouro Noir, Esmeralda e Pôr do Sol. A escolha fica salva no navegador. As cores ficam em `web/scripts/gen_themes.py`.

## Instalar e usar (Docker)

Pré-requisito: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac) ou Docker Engine (Linux).

```bash
git clone https://github.com/4ntich/EzTractor.git
cd EzTractor
cp .env.example .env          # opcional: ajuste o que quiser
docker compose up -d
```

Abra **http://localhost:8000**. Os vídeos, clipes e o banco ficam no volume `eztractor-data`.

- A imagem vem pronta do GitHub (`ghcr.io/4ntich/eztractor`). Se preferir compilar no seu PC: `docker compose up -d --build`.
- Para atualizar: `docker compose pull && docker compose up -d`.
- Na primeira transcrição, o modelo Whisper (cerca de 500 MB) é baixado uma vez e fica salvo.

## Projetos: cortes ou só download

- **Gerar cortes com IA:** encontra os melhores momentos e cria clipes verticais.
- **Só baixar o vídeo:** baixa o vídeo do link na qualidade escolhida (até 4K ou a melhor disponível). Sem template, você recebe o arquivo original. Com template, o vídeo inteiro é renderizado no formato do template, com textos, moldura e legendas.
- **Qualidade do vídeo final** escolhida na tela, por projeto: 360p, 480p, 720p, 1080p, 1440p ou 4K.
- **Pausar, Continuar e Cancelar** durante o download, a transcrição e a renderização. Na pausa nada é processado (o ffmpeg fica suspenso). No cancelamento os clipes já prontos são mantidos e dá para **Reprocessar** depois. Se o app for fechado no meio, o projeto aparece como interrompido para reprocessar.
- **⬇ Vídeo original:** baixa o vídeo de origem de qualquer projeto. Os clipes baixam com o título como nome do arquivo.

## Métodos de análise (escolha por projeto, no site)

| Método | Custo | O que faz |
|---|---|---|
| **Sinais** (padrão) | grátis | Nota pelos picos de volume, trocas de cena e palavras de empolgação. Título e gancho tirados da frase mais empolgada perto do pico (ex.: *"Meu deus que clutch!"*) ou de um modelo (*"Reação explosiva \| Valorant"*). |
| **IA local (Ollama)** | grátis | Um modelo de linguagem roda no seu computador e avalia cada trecho, como o Claude. Mais lento; precisa de PC razoável (ideal com placa de vídeo). |
| **Claude** | pago | API da Anthropic. Melhor qualidade de notas, títulos e ganchos. Precisa de `ANTHROPIC_API_KEY`. |

Se a IA escolhida não estiver disponível (Ollama desligado, sem chave), o app usa **Sinais** automaticamente. Cada clipe mostra um selo dizendo quem o analisou.

### Ativando a IA local (Ollama)

**Opção A, recomendada (usa a placa de vídeo no Windows/Mac):**
1. Instale o Ollama: https://ollama.com/download
2. Baixe um modelo: `ollama pull qwen2.5:7b`. Em PC mais fraco, use `qwen2.5:3b` e coloque `EZT_OLLAMA_MODEL=qwen2.5:3b` no `.env`.
3. Pronto: o container já procura o Ollama do seu PC em `host.docker.internal:11434`.

**Opção B, Ollama também em container:**
```bash
# no .env: EZT_OLLAMA_URL=http://ollama:11434
docker compose --profile ollama up -d
docker compose exec ollama ollama pull qwen2.5:7b
```

No formulário, o botão **IA local** avisa se o Ollama está fora do ar ou se o modelo ainda não foi baixado.

## Templates: textos, fontes, efeitos e molduras em todos os clipes

Na aba **Templates** você monta o visual dos clipes, e ele é aplicado automaticamente em todos os vídeos:

- **16 estilos prontos** (Gamer Neon, Impacto Amarelo, Meme Clássico, Top Ranking + CTA, Retrô Arcade, FPS Militar, Notícia, Cinema, Quadrinhos…). Dá para usar direto ou abrir no editor e mudar.
- **Editor visual:** arraste os textos na tela, com guias de centralização e área segura do TikTok/Reels. Até 10 textos (título, texto, etiqueta).
- **Textos automáticos por clipe:** `{titulo}` `{gancho}` `{jogo}` `{numero}` `{total}` `{nota}` `{projeto}` `{data}`. Ex.: `TOP {numero}` vira TOP 1, TOP 2… em cada clipe.
- **17 fontes** (Anton, Bebas Neue, Bangers, Luckiest Guy, Press Start 2P, Black Ops One, Russo One, Permanent Marker, Pacifico…), todas livres e incluídas no projeto (`web/public/fonts`).
- **Efeitos:** contorno, sombra, brilho neon, caixa atrás do texto, opacidade, inclinação, espaçamento, maiúsculas, itálico.
- **Animações:** fade, pop, zoom, subir, descer, entrar pela direita, máquina de escrever, pulsar. Cada texto pode aparecer no clipe todo, só no início ou só no final (ex.: "SEGUE PRA PARTE 2" nos últimos 3 s).
- **Vídeo e moldura:** formatos 9:16, 4:5, 1:1 e 16:9; vídeo preenchendo a tela, inteiro com fundo desfocado ou com fundo sólido; zoom; vinheta; faixas de cabeçalho, rodapé e laterais; barra de progresso.
- **Legendas automáticas estilizadas:** fonte, cores, palavra falada destacada com "pop", posição e palavras por vez.
- **Prévia real:** gera um quadro com o mesmo motor do vídeo final, se quiser sobre um vídeo seu.
- **Template padrão (★):** entra sozinho em todos os projetos novos. Na página do projeto, **Aplicar a todos os clipes** troca o template e renderiza tudo de novo.

O editor e o vídeo usam as mesmas fontes e a mesma escala, calibrada fonte a fonte e coberta por testes, então o que você vê na tela é o que sai no vídeo.

## Configuração (`.env`)

| Variável | Padrão | Descrição |
|---|---|---|
| `EZT_RANKER` | `heuristic` | Método padrão: `heuristic`, `ollama` ou `claude` |
| `EZT_OLLAMA_MODEL` | `qwen2.5:7b` | Modelo do Ollama |
| `EZT_OLLAMA_URL` | `http://host.docker.internal:11434` | Endereço do Ollama |
| `ANTHROPIC_API_KEY` | vazio | Só para o método Claude |
| `EZT_CLAUDE_MODEL` | `claude-opus-5-5` | Modelo do Claude |
| `EZT_APP_PASSWORD` | vazio | Senha do site. **Defina se for expor na internet** |
| `EZT_JWT_SECRET` | valor de dev | Troque se usar senha |
| `EZT_TRANSCRIBER` | `faster_whisper` | `none` desliga a transcrição (sem legendas, mais rápido) |
| `EZT_WHISPER_MODEL` | `small` | `tiny`/`base` (rápidos) … `large-v3` (melhor) |
| `EZT_WHISPER_DEVICE` | `auto` | `auto` usa a placa NVIDIA se o CUDA 12 + cuDNN 9 estiverem instalados, senão o processador. `cpu` ou `cuda` forçam |
| `EZT_RENDER_HEIGHT` | `1920` | Qualidade padrão (lado maior): 640, 854, 1280, 1920, 2560, 3840. Também escolhida por projeto na tela |
| `EZT_MAX_VIDEO_MINUTES` | `600` | Duração máxima do vídeo |

## Deploy pelo GitHub

- **`Testes`** (`.github/workflows/ci.yml`): roda os testes do back-end e o build do site a cada push.
- **`Publicar imagem Docker`** (`.github/workflows/docker.yml`): a cada push na branch padrão (ou em tags `v*`, ou manualmente pela aba *Actions*), constrói a imagem e publica em `ghcr.io/4ntich/eztractor:latest`. Usa o `GITHUB_TOKEN` do próprio repositório, sem configurar nada.

O GitHub guarda e compila o app; quem **roda** é o seu PC ou um servidor (VPS) com Docker. Num servidor, é o mesmo `docker compose up -d`. Defina `EZT_APP_PASSWORD` e coloque HTTPS na frente (ex.: Caddy ou Cloudflare Tunnel).

> Se o repositório for privado, faça `docker login ghcr.io` antes do `pull`, ou use `docker compose up -d --build`.

## Como funciona

```
navegador ──► FastAPI (serve o site + API) ──► thread de processamento
                         │                          │
                         └── SQLite + /data ◄────────┘
```

| Etapa | Arquivo | O que faz |
|---|---|---|
| Ingestão | `pipeline/ingest.py` | Baixa o VOD com `yt-dlp` (ou usa o upload) |
| Transcrição | `pipeline/transcribe.py` | `faster-whisper` com tempo por palavra |
| Sinais | `pipeline/signals.py` | Por segundo: energia do áudio, cortes de cena, palavras de empolgação, fala |
| Candidatos | `pipeline/candidates.py` | Picos → janelas com contexto antes do clímax, estendidas até ele acabar, sem sobreposição |
| Ranking | `pipeline/ranker.py` | Sinais, Ollama ou Claude (JSON estruturado), com fallback automático |
| Títulos sem IA | `pipeline/headlines.py` | Frase mais empolgada perto do pico, ou modelos por idioma (pt/en/es) |
| Legendas | `pipeline/captions.py` | ASS com a palavra atual destacada + gancho |
| Templates | `pipeline/template_render.py`, `presets.py`, `fonts.py` | Camadas, variáveis, efeitos e animações em ASS; molduras, vinheta e barra de progresso no ffmpeg |
| Render | `pipeline/render.py` | ffmpeg: `crop`, `fit` (fundo desfocado), `split` (webcam + jogo) |

## Desenvolvimento

Requisitos: Python 3.11+, Node 22, `ffmpeg`.

```bash
cd backend && pip install -e ".[dev,whisper]"
uvicorn eztractor.api.main:app --reload --port 8000     # API

cd web && npm install && npm run dev                    # site em http://localhost:3000
```

Testes: `cd backend && pytest -q`. A suíte gera um vídeo sintético com um pico de áudio conhecido e verifica o fluxo completo, os três métodos de análise (Ollama e Claude com respostas simuladas), o modo com senha e o site estático.

Para escalar (Postgres e worker separado): `EZT_DATABASE_URL=postgresql+psycopg://…`, `EZT_QUEUE_MODE=rq`, `EZT_REDIS_URL=…` e `python -m eztractor.worker`.

## Roadmap

- [ ] Detecção automática da webcam (MediaPipe/YOLO)
- [ ] Sinal do chat da Twitch e leitura do HUD (kills/vitória)
- [ ] Editor com linha do tempo e estilos de legenda
- [ ] Publicação e agendamento: TikTok, YouTube, Instagram
