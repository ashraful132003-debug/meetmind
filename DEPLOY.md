# Deploying MeetMind — free, no credit card

**Total cost: ₹0. No card needed anywhere. Takes about 15 minutes.**

---

## The one thing to understand first

The app runs in two modes. They are both real, and the difference is the most
interesting thing about this project — do not hide it in an interview, lead with it.

| | **Local mode** (your laptop) | **Deployed mode** (the live link) |
|---|---|---|
| Transcription | Whisper, on your machine | Groq's Whisper (free tier) |
| Language model | Llama 3.2 3B, on your machine | Llama 3.3 **70B** via Groq (free tier) |
| Retrieval | semantic (embeddings) | BM25 lexical |
| Audio leaves your machine? | **Never** | **Yes — sent to Groq** |
| Cost | ₹0 | ₹0 |
| Needs | a decent laptop | a browser |

**Why deployed mode cannot use the local models:** a free instance has 512 MB of
RAM. Whisper needs ~2 GB and Llama 3.2 needs ~3 GB. No configuration fixes that —
anyone claiming otherwise has not tried it. So deployed mode calls Groq's free
tier instead, which leaves the instance doing only web serving, diarization (a
25 MB ONNX model) and BM25. That fits in 512 MB.

**The upside nobody expects:** deployed mode is *smarter*. Groq serves Llama 3.3
70B and Whisper large-v3-turbo for free — both far better than what a laptop can
run. You trade privacy for quality, and get to explain exactly why.

**If asked "so is it private or not?"** — the honest answer, and a good one:
> "Local mode is genuinely private — open the network tab, there are zero outbound
> calls, unplug the WiFi and it still works. The deployed link trades that for
> free hosting: audio goes to Groq. Same codebase, one environment variable. The
> architecture supports both because the LLM provider is an interface, not a
> hardcoded call."

---

## What you need to create (5 minutes)

Three free accounts. **No credit card for any of them.**

1. **GitHub** — https://github.com/signup
2. **Groq** — https://console.groq.com → sign in with Google → *API Keys* → *Create API Key*.
   Copy it. It looks like `gsk_...`. This is the free AI.
3. **Neon** (free Postgres that never expires) — https://neon.tech → sign in with GitHub
4. **Render** (free hosting) — https://render.com → sign in with GitHub

> Render also offers Postgres, but its free tier **expires after 90 days**.
> Neon's does not. That is why there are two accounts rather than one.

---

## Step 1 — Push the code to GitHub

From the project folder:

```bash
git remote add origin https://github.com/YOUR-USERNAME/meetmind.git
git branch -M main
git push -u origin main
```

Your `.env`, database, models and audio are all git-ignored — nothing secret is
uploaded. Verify it yourself if you like:

```bash
git ls-files | grep -c "\.env$"     # must print 0
```

---

## Step 2 — Create the database (Neon)

1. Neon dashboard → **New Project** → name it `meetmind` → region closest to you
2. It shows a connection string like:
   ```
   postgresql://alex:AbC123xyz@ep-cool-name-123456.ap-southeast-1.aws.neon.tech/neondb
                └user┘ └password┘ └──────────── host ────────────────┘ └── db ──┘
   ```
3. Keep that tab open — you need those four pieces in the next step.

---

## Step 3 — Deploy (Render)

1. Render dashboard → **New** → **Blueprint**
2. Connect your GitHub repo. Render finds `render.yaml` and configures itself.
3. It will ask for the values marked `sync: false`. Fill them in:

| Key | Value |
|---|---|
| `GROQ_API_KEY` | your `gsk_...` key |
| `POSTGRES_HOST` | `ep-cool-name-123456.ap-southeast-1.aws.neon.tech` |
| `POSTGRES_DB` | `neondb` |
| `POSTGRES_USER` | `alex` |
| `POSTGRES_PASSWORD` | `AbC123xyz` |
| `ENCRYPTION_KEY` | see below |

For `ENCRYPTION_KEY`, run this **on your machine** and paste the output:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> **Generate a NEW key. Do not reuse your local one.** This is not about trusting
> anybody — it is that each deployment needs its own lock, the same way your house
> and your office do not share a key. If the server used your local key, anyone
> who ever saw the server's config could decrypt the meetings on your laptop.
>
> **Back this key up somewhere safe.** Change it later and every transcript
> already stored becomes permanently unreadable. There is no recovery — that is
> the encryption working correctly.

4. **Create Blueprint**. First build takes ~10 minutes (it downloads the speaker model).

---

## Step 4 — Check it

Your link will be `https://meetmind-XXXX.onrender.com`.

```
https://meetmind-XXXX.onrender.com/api/health
```

You want:

```json
{"status": "healthy", "database": true, "llm": {"provider": "groq", "reachable": true}}
```

`"status": "healthy"` means the database connected and Groq accepted the key.
If it says `degraded`, the `detail` field tells you exactly what is wrong — it is
written to be actionable, not decorative.

Then open the link, register an account, and upload a short recording.

---

## Known limits of the free tier — say these before you are asked

- **It sleeps after 15 minutes idle.** The first request afterwards takes ~50
  seconds to wake up. Hit the link a minute before demoing.
- **Uploads are capped at 24 MB** (Groq's limit, and a 512 MB box cannot buffer
  more). Roughly 20 minutes of audio. Local mode allows 200 MB.
- **Audio files do not persist.** Free instances have no disk, so recordings
  vanish on restart. Transcripts and summaries survive — they are in Neon.
- **Groq rate-limits** after a burst. Fine for a demo, not for real traffic.
- **Retrieval is BM25, not semantic.** Good at "what did Rahul say about the
  deadline", weaker on heavy paraphrase.

---

## Verify the deployment is actually secure

Point the attack script at the live URL:

```bash
BASE=https://meetmind-XXXX.onrender.com python scripts/security_check.py
```

39 attacks, all should be blocked — against the real deployment, not localhost.

---

## Option B — deploy the fully private version

If you want the local models with a public URL, you need ~8 GB RAM. That is not
free, but it is cheap: Hetzner CX22 is about €4/month. Oracle Cloud's Always Free
ARM tier (4 vCPU / 24 GB) is genuinely free but famously hard to get capacity for.

```bash
git clone <your-repo> && cd meetmind
python scripts/bootstrap_env.py       # fresh secrets ON THE SERVER
# edit .env: APP_ENV=production, FRONTEND_ORIGIN=https://your-domain
docker compose up -d --build
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull all-minilm
```

Put Caddy or nginx in front for TLS. **`APP_ENV=production` matters** — it enables
`Secure` cookies and HSTS and disables `/api/docs`. Without HTTPS in production
the refresh cookie is never sent and login will appear to fail silently.

---

## Honest recommendation

Deploy the link — it is worth having on a CV, and it costs nothing.

But **demo from your laptop.** A live URL proves you can deploy. Running it
locally with the network tab open, showing zero outbound requests, then pulling
the WiFi out and recording a meeting anyway — that proves something no deployed
demo can, and it is the actual point of the project.
