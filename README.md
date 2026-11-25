# EzTractor

Transforma gravações longas de gameplay (VODs da Twitch, YouTube, Kick ou arquivo enviado) em **clipes verticais 9:16** com legenda animada, gancho e **nota de potencial viral (0–100)**, prontos para TikTok, Reels e Shorts.

```
web (Next.js) ──► api (FastAPI) ──► fila (Redis/RQ) ──► worker (pipeline de vídeo)
                     │                                     │
                     └──── PostgreSQL ◄────────────────────┤
                     └──── storage (disco local → S3/R2) ◄─┘
```

## Pipeline

| Etapa | Arquivo | O que faz |
|---|---|---|
| Ingestão | `pipeline/ingest.py` | Baixa o VOD com `yt-dlp` (ou usa o upload) |
| Transcrição | `pipeline/transcribe.py` | `faster-whisper` com tempo por palavra |
| Sinais | `pipeline/signals.py` | Por segundo: energia do áudio (z-score), cortes de cena (ffmpeg), palavras de empolgação, densidade de fala |
| Candidatos | `pipeline/candidates.py` | Picos locais → janelas com mais contexto antes do pico, estendidas até o fim do clímax, sem sobreposição e alinhadas às frases |
| Ranking | `pipeline/ranker.py` | Claude (`claude-opus-5-5`, saída em JSON estruturado) dá nota, título, gancho e refina os limites; cai para a heurística se a API falhar |
| Legendas | `pipeline/captions.py` | ASS com a palavra atual destacada, gancho nos 3 primeiros segundos e marca d'água |
| Render | `pipeline/render.py` | ffmpeg: layouts `crop` (recorte central), `fit` (vídeo inteiro + fundo desfocado), `split` (webcam em cima + jogo embaixo) |
| Orquestração | `pipeline/run.py` | Estados, progresso, cobrança e estorno de créditos |

## Regras de negócio

- **Créditos:** 1 crédito = 1 minuto de vídeo (arredondado para cima). Bônus de 120 no cadastro. Débito único por projeto; **estorno automático** se o processamento falhar. O saldo é a soma do extrato imutável (`credit_ledger`).
- **Planos** (`models.PLAN_LIMITS`):
  - `free`: 720×1280, com marca d'água, vídeos de até 60 min.
  - `pro`: 1080×1920, sem marca d'água, vídeos de até 6 h.
- Os arquivos são servidos por **URL assinada** com validade de 6 h, porque a tag `<video>` não envia o header `Authorization`.
- Editar o início, o fim ou o gancho de um clipe dispara um novo render só daquele clipe.

## Rodando com Docker

```bash
cp .env.example .env   # defina EZT_JWT_SECRET e, opcionalmente, ANTHROPIC_API_KEY
docker compose up --build
# web: http://localhost:3000  ·  API: http://localhost:8000/docs
```

## Rodando em desenvolvimento (sem Docker)

Requisitos: Python 3.11+, Node 22, `ffmpeg`.

```bash
# API: SQLite e pipeline numa thread, sem precisar de Redis
cd backend
pip install -e ".[dev,whisper]"
uvicorn eztractor.api.main:app --reload --port 8000

# front
cd web
npm install
npm run dev
```

Para usar a fila de verdade, defina `EZT_QUEUE_MODE=rq` e rode `python -m eztractor.worker`.

### Variáveis (prefixo `EZT_`)

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./eztractor.db` | Em produção, `postgresql+psycopg://…` |
| `QUEUE_MODE` | `inline` | `rq` (Redis + worker), `inline` (thread na API) ou `sync` (testes) |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `STORAGE_DIR` | `./data` | Onde ficam os vídeos e os clipes |
| `JWT_SECRET` | valor de dev | **Troque em produção** |
| `RANKER` | `claude` | `claude` ou `heuristic`. O modo `claude` lê `ANTHROPIC_API_KEY` |
| `TRANSCRIBER` | `faster_whisper` | `faster_whisper` ou `none` |
| `WHISPER_MODEL` | `small` | `tiny` … `large-v3` |
| `SIGNUP_BONUS_CREDITS` | `120` | |

## Testes

```bash
cd backend && pytest -q
```

A suíte gera um vídeo sintético com ffmpeg (com um pico de áudio em um trecho conhecido) e verifica o fluxo completo: cadastro → upload → cobrança → clipes ranqueados → render 720×1280 → URL assinada → edição com novo render → estorno em caso de falha → isolamento entre usuários. O ranking com Claude é testado com o cliente mockado.

## API

| Método | Rota | |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | Retorna `{token}` (JWT) |
| GET | `/me` | Plano e saldo de créditos |
| POST | `/projects/url` | `{url, title, settings}` |
| POST | `/projects/upload` | multipart: `file`, `title`, `settings` (JSON) |
| GET | `/projects`, `/projects/{id}` | O detalhe inclui os clipes com URLs assinadas |
| POST | `/projects/{id}/reprocess` | |
| DELETE | `/projects/{id}` | |
| PATCH | `/clips/{id}` | `{start_s, end_s, title, hook}` → novo render |

`settings`: `clip_min_s`, `clip_max_s`, `max_clips`, `language`, `layout` (`crop`/`fit`/`split`), `facecam` (`{x,y,w,h}` normalizado, obrigatório no `split`), `game`, `captions`.

## Roadmap

- [x] Fase 0: base (auth, banco, storage, fila)
- [x] Fase 1: detecção e ranking de destaques
- [x] Fase 2: render 9:16, legendas, layouts
- [x] Fase 4 (parcial): ingestão por link via yt-dlp
- [ ] Fase 3: Stripe (assinatura Pro, pacotes de créditos, webhooks)
- [ ] Migrações com Alembic (hoje é `create_all`)
- [ ] Storage S3/R2 com URLs pré-assinadas
- [ ] Detecção automática da webcam (MediaPipe/YOLO) e reenquadramento com acompanhamento
- [ ] Sinal do chat da Twitch e OCR do HUD (kills/vitória)
- [ ] Editor com linha do tempo e estilos de legenda
- [ ] Publicação e agendamento: TikTok, YouTube, Instagram
- [ ] Busca de momentos ("Find Moments") por texto
