# MeetMind

A local-first AI meeting assistant. Record or upload a meeting and get back a
speaker-attributed transcript, a summary, action items with owners and deadlines,
searchable analytics, and a chatbot you can ask questions about what was said.

**Everything runs on your own machine.** Speech-to-text (Whisper) and the language
model (Llama 3.2) execute locally. There is no cloud API in the request path, no
API key, and no per-minute cost. You can disconnect from the internet and the app
still works end to end.

---

## Why this is built the way it is

Most "AI meeting assistant" projects are a thin wrapper around a hosted API: audio
goes to someone else's server, a summary comes back. That is easy to build and
impossible to use for anything confidential — which is most meetings worth
summarising.

This one inverts that. The models run here. The trade-off is real and I am not
going to pretend otherwise: a local 3B model writes a slightly less polished
summary than a frontier model would. In exchange, your board meeting never leaves
your laptop, and the running cost is zero forever. For meeting notes, that is the
right trade.

The provider is swappable (`LLM_PROVIDER` in `.env`), so a hosted model is one
line of config away if you ever want it.

---

## What it does

| | |
|---|---|
| **Record or upload** | Browser microphone capture, or drop a WAV/MP3/M4A/WEBM/OGG/FLAC file |
| **Transcribe** | Whisper `small`, running locally. Auto-detects language |
| **Identify speakers** | Voice-fingerprint clustering. Labels are editable — no diarizer is perfect |
| **Summarise** | Overview, key points, decisions, and risks — grounded in the transcript |
| **Extract action items** | Task, owner, deadline, priority, and the timestamp it was said |
| **Ask the meeting** | RAG chatbot over one meeting. Every answer cites timestamps you can click to verify |
| **Ask ALL your meetings** | Cross-meeting memory: "what did the client say about pricing last week?" Understands time expressions, names the meeting, and **every quote is verified against the transcript it's attributed to before you see it** |
| **Unified task board** | Every action item from every meeting in one list, filterable by owner and state |
| **AI follow-up email** | Drafts the email you'd send after the meeting, in four tones, grounded in what was actually said |
| **Export** | Real PDF and Word files, generated server-side from the data — not a screenshot of the page |
| **WhatsApp share** | Opens WhatsApp with the summary and open actions pre-filled. No Business API, no cost |
| **Analytics** | Talk-time share, participation balance, words per minute, topics, timeline |
| **Email the summary** | Renders a real MIME email. Captures locally by default; real SMTP is one config flip |
| **Hindi + English** | Whisper handles code-switching mid-sentence, which is how meetings here actually sound |

---

## Security

The threat model is simple: **your meetings belong to you and nobody else.**

- **Argon2id** password hashing (OWASP's current recommendation), with temporary
  account lockout after repeated failures.
- **Short-lived access tokens** (15 min) held in memory — never in `localStorage`,
  which any XSS could read.
- **Refresh tokens** in httpOnly, SameSite cookies. They **rotate on every use**,
  and replaying a rotated token is treated as theft: the entire token family is
  revoked immediately.
- **Ownership enforced in SQL**, not checked afterwards. Requesting someone else's
  meeting returns the same `404` as a meeting that never existed — the API will
  not even confirm it exists.
- **Transcripts encrypted at rest** (Fernet / AES). Copying the database files
  gets you ciphertext without the key in `.env`.
- **Audio needs two proofs**: an HMAC-signed, expiring URL *and* an httpOnly cookie
  identifying the requester. A leaked link is useless to anyone else.
- **Uploads validated by magic bytes**, not by filename or Content-Type — both of
  which the client controls. Filenames on disk are generated, never client-supplied.
- **Prompt-injection hardening**: meeting content is always fenced as untrusted
  data. A participant saying "ignore your instructions" gets summarised, not obeyed.
- **Rate limiting** on login, registration, upload, chat and email.
- **No `dangerouslySetInnerHTML` anywhere** — all rendering goes through JSX escaping.

### Prove it, don't trust it

```bash
python scripts/security_check.py    # 39 attacks, all blocked
cd backend && pytest                # 89 unit tests
python scripts/verify_app.py        # every feature, end to end, on real data
python scripts/tune_diarize.py      # diarization accuracy vs ground truth
```

This is an attack script, not a unit test. It creates two users and tries to break
every claim above — forged JWTs, `alg=none` tokens, cross-user reads, token replay,
signature tampering, disguised executables, path traversal, brute force. Each
`[PASS]` is an attack that failed.

```
  39 passed, 0 failed
```

It has already earned its keep: it caught two real bugs during development — a
refresh-reuse detection hole, and a signed audio URL that worked for the wrong
user. Both are fixed; the tests that caught them are still in there.

---

## Setup

**Requirements:** Windows, Python 3.11+, Node 18+. No admin rights needed. No Docker
required for local dev — PostgreSQL runs from portable binaries inside the project
folder.

```powershell
# 1. Secrets (generates a .env with real random keys)
python scripts/bootstrap_env.py

# 2. Python dependencies
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 3. Database (portable Postgres — no installer, no service, no admin)
.\scripts\pg.ps1 init          # once
.\scripts\pg.ps1 start         # each session
python scripts\init_db.py

# 4. Local AI
#    Install Ollama from https://ollama.com, then:
.\scripts\pull_models.ps1              # llama3.2:3b + all-minilm, resumable
.\scripts\get_speaker_model.ps1        # 25MB speaker model for diarization

# 5. Frontend
cd frontend
npm install
npm run dev
```

Then, in a second terminal:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open **http://localhost:5173**.

### Optional: demo data

```powershell
python scripts\make_seed_audio.py   # renders 3 meetings using Windows TTS voices
python scripts\seed_meetings.py     # uploads them through the real pipeline
```

These are invented conversations between invented people, spoken by the TTS voices
Windows ships with. They are **not** hardcoded results — the audio is uploaded over
HTTP and processed by the same pipeline a live recording uses. The summaries,
timestamps and embeddings are all genuinely produced by the models.

---

## Performance

Measured on an i5-11400H (12 threads) with Whisper `small` on CPU:

| Stage | 3-minute meeting |
|---|---|
| Transcription | ~60s |
| Diarization | ~5s |
| Summary + actions + topics | ~40s |
| Embedding + indexing | ~5s |

**GPU:** the code auto-detects CUDA and validates it with a real inference before
committing to it — loading alone is not proof, since CTranslate2 constructs a CUDA
model happily and only fails on the first kernel if cuBLAS is missing. If the GPU
isn't usable it logs why and falls back to CPU rather than crashing mid-meeting.

To enable GPU acceleration:

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

---

## Cross-meeting memory, and why it verifies itself

"What did the client say about pricing last week?" is a harder question than it
looks. The answer must name the *right* meeting — quoting a real line but
attributing it to the wrong client is worse than saying "I don't know", because
the user acts on it.

Measured on Llama 3.2 3B (`scripts/tune_memory.py`), the model got this wrong
about **half the time**. It quoted real lines and credited the wrong meeting, and
it invented friendlier titles — "Acme pricing call" for a meeting actually named
"Acme Salesforce integration - scope call".

Prompting alone did not fix it. So the model is not trusted:

1. It must return each source as `{meeting: N, quote: "..."}`, quoted verbatim.
2. **Every quote is then looked up in the text of the meeting it names.**
3. Anything that fails — a quote from a different meeting, a fabricated quote, a
   meeting number that doesn't exist — is dropped before the user sees it.

| | Before | After |
|---|---|---|
| Citation accuracy | — | **85.7%** (6/7) |
| **Wrong meeting cited** | ~50% of answers | **0** |

The remaining failure is retrieval (one question where the right chunk wasn't
surfaced), not attribution. A citation shown in the UI is a checked fact about
the transcript, not a claim by a language model.

The same idea, stated generally: **the model proposes, the code verifies.** It is
also why action-item timestamps are located by searching the transcript rather
than trusting the model's guess.

---

## Architecture

```
frontend/           React 18 + TypeScript + Vite. No UI framework — hand-written CSS.
  src/lib/api.ts      Typed client. Transparent token refresh, single-flight.
  src/components/     Recorder, player, transcript, chat, analytics, email panels.

backend/
  app/main.py         App assembly, security headers, error handling.
  app/security.py     Argon2, JWT, HMAC URL signing, Fernet encryption.
  app/deps.py         get_current_user + owned_meeting — the ownership chokepoint.
  app/routers/        auth, meetings, chat, analytics, email.
  app/services/
    transcribe.py     faster-whisper. CTranslate2, deliberately not PyTorch.
    diarize.py        MFCC voice embeddings + agglomerative clustering, on numpy.
    analysis.py       Summary, action items, topics. Injection-hardened prompts.
    rag.py            Chunking, embeddings, cosine retrieval, cited answers.
    pipeline.py       Stage orchestration and progress reporting.
    emailer.py        MIME rendering, local capture or SMTP.

scripts/
  security_check.py   The attack suite.
  pg.ps1              Portable PostgreSQL control.
  make_seed_audio.py  TTS meeting generator.
```

### Decisions worth defending

**No PyTorch.** faster-whisper runs on CTranslate2. Importing Torch purely for
`cuda.is_available()` would add ~2.5 GB to the install for one boolean.

**No pyannote for diarization.** It is the standard answer, but its pretrained
pipelines are gated behind a HuggingFace account, a token, and manual licence
acceptance — meaning a fresh user could not run this app without signing up
somewhere. Instead: **WeSpeaker ResNet34-LM**, trained on VoxCeleb, exported to
ONNX. 25 MB, Apache-2.0, no account, and it runs on the `onnxruntime` that
faster-whisper already installs — so no PyTorch either. If the model is absent,
the code falls back to hand-built features (MFCC + pitch + spectral centroid)
automatically, so the app always works.

**It is measured, not guessed.** The seed audio is concatenated from individual
TTS lines, so the true speaker of every turn is known exactly. That makes
diarization a number rather than a vibe.

```
python scripts/tune_diarize_real.py     # the honest one
```

```
neural (WeSpeaker ResNet34 ONNX)          time-weighted accuracy, real Whisper segments
threshold  accuracy  speakers found (true = 3,3,3)
0.50        70.2%    [5, 5, 8]   badly over-split
0.60        90.2%    [4, 3, 6]
0.65        94.0%    [4, 3, 3]   <- shipped default
0.70        69.1%    [2, 2, 2]   under-split: two people merged

handbuilt fallback (MFCC + pitch + centroid, standardized)
1.10        79.5%    [2, 3, 2]   <- fallback default
```

The journey matters more than the number.

**44.9% → 89.2%.** The first version put every speaker into one cluster — exactly
the majority-class baseline, i.e. no better than guessing. Three fixes: add pitch
(male and female fundamental frequencies differ hugely, and MFCCs deliberately
discard that signal); drop the C0 coefficient (it tracks microphone distance, not
identity); and standardise features across the meeting before clustering. That
last one is the crux — in absolute terms all human speech looks alike, so every
cosine distance collapses toward zero until you rescale each dimension by how much
it actually varies *between these speakers*.

**89.2% → 95.7%.** A network trained on thousands of real voices beats features a
human reasoned out. Its embeddings separate 3.7× better: same-speaker distance
0.18 vs different-speaker 0.68, against hand-built's 1.6×.

**95.7% → 94.0%, and that drop is the most useful result here.** The 95.7% was a
lie I told myself. That benchmark fed the diarizer the *ground-truth turn
boundaries* — which the app never has. It has Whisper's segments: 44–57 of them
where there are only 28–31 real turns, so shorter and noisier. Re-measured on
those, the threshold tuned to 95.7% actually scored **70.2%** and reported 5–8
speakers in a three-person meeting. Retuning on real segments gives 94.0%.

The lesson, which cost a real bug: **tune on the input the system actually gets,
not the input you wish it got.** `tune_diarize.py` (idealised) is kept only to
show the gap; `tune_diarize_real.py` is the one that decides what ships.

Speaker labels are user-editable regardless, because no diarizer is perfect:
renaming "Speaker 1" to "Rahul" updates the transcript and his action items
together.

**No pgvector.** Retrieval is scoped to a single meeting — tens to hundreds of
chunks. Cosine similarity in numpy is microseconds at that size. pgvector is the
swap if this ever needs to search across millions.

**No `scikit-learn`.** Agglomerative clustering is ~40 lines; the dependency is 100 MB.

**Transcripts are encrypted, so SQL cannot search them.** Search covers titles and
topics. That is the deliberate cost of encryption at rest, not an oversight.

**No worked example in the action-item prompt.** There was one. Llama 3.2 3B
copied items straight out of it into real answers — a meeting about a Salesforce
integration came back with *"Trial the croissant recipe with the new oven
settings"* — and it did that even with an explicit "never copy this example"
warning sitting next to it. A 3B model does not reliably separate "illustrative"
from "extract this". The shape spec alone is enough, and `scripts/tune_actions.py`
now fails the build if example text ever reappears in output.

**Action-item timestamps are looked up, not predicted.** Asked for the timestamp
of a commitment, the model supplied one for 2 of 8 items — and those were
unverifiable guesses. But the transcript with exact per-utterance timings is
already in hand, so the timestamp is a lookup: score each utterance by how many of
the task's distinctive words it contains, take the best, and decline when nothing
matches well. A wrong timestamp that jumps the player to an unrelated moment is
worse than no link.

### Quality, measured

| | |
|---|---|
| Diarization | **94.0%** time-weighted, on real Whisper segments |
| Action items | **73%** recall vs a human answer key, **0** hallucinations, **0** example leakage |
| Chatbot honesty | Refuses off-transcript questions ("That wasn't covered in this meeting") |
| Processing speed | ~3.3× realtime on CPU (12-thread i5) |

---

## Deploying free

`docker-compose.yml` builds the whole stack. The catch worth knowing: free hosting
tiers cap out around 512 MB RAM, and Whisper `small` plus Llama 3.2 3B need roughly
6 GB. **A free tier cannot run the local models.**

Two honest options:

1. **Deploy with a hosted LLM.** Set `LLM_PROVIDER=anthropic` (or `openai`) and
   `WHISPER_MODEL=tiny`. Fits a small instance, costs a few cents per meeting.
2. **Keep it local and demo it locally.** For an interview this is the stronger
   story anyway: "it runs entirely on my machine, here is the network tab showing
   zero outbound calls."

See `DEPLOY.md`.

---

## Licences

All dependencies are permissively licensed and free for this use: Ollama (MIT),
Llama 3.2 (Meta Community License — restrictions begin at 700M monthly users),
faster-whisper and Whisper (MIT), PostgreSQL (PostgreSQL License), FastAPI, React,
and the rest (MIT/Apache-2.0). No account, no card, no bill.
