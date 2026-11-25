# EzTractor

Transforma gravações longas de gameplay (VODs da Twitch, YouTube, Kick ou arquivo enviado) em **clipes verticais 9:16** com legenda animada, gancho e **nota de potencial viral (0–100)**, prontos para TikTok, Reels e Shorts.

App **de uso pessoal**: sem cadastro, sem créditos e sem marca d'água. **Funciona 100% grátis**. A IA paga (Claude) é opcional.

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
| `EZT_RENDER_HEIGHT` | `1920` | `1920` = 1080×1920; `1280` = 720×1280 (mais rápido) |
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
