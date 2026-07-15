# Deploying MeetMind

## Read this first

MeetMind runs Whisper and Llama 3.2 in-process. Together they need roughly **6 GB
of RAM**. Every free hosting tier gives you 512 MB.

So the honest position is: **you cannot run the local-model version on a free
tier.** Anyone who tells you otherwise hasn't tried it. You have three options,
and I'd genuinely recommend the first.

---

## Option 1 — Don't deploy. Demo it locally. (Recommended)

For an interview this is the *stronger* story, not the weaker one.

Deploying to a free tier forces you to rip out the local models and call a hosted
API — which destroys the entire premise of the project. You'd be demoing a
generic API wrapper and claiming it's private.

Running it on your laptop lets you say something no deployed version can:

> "Open the network tab. Record a meeting. Watch — there are zero outbound
> requests. The audio never leaves this machine. Now let me disconnect the WiFi
> and do it again."

That demo is memorable, and it is impossible to fake. It also happens to be the
actual product thesis.

**What to do:** run it locally (see README), and put a 60-second screen recording
in your README so anyone can see it working without setting it up.

---

## Option 2 — Deploy with a hosted LLM

If a live URL is required, keep the architecture and swap the model provider.
This is exactly what `LLM_PROVIDER` exists for — no code changes.

```env
LLM_PROVIDER=anthropic          # or openai
ANTHROPIC_API_KEY=sk-ant-...
WHISPER_MODEL=tiny              # small won't fit a 512MB box
WHISPER_DEVICE=cpu
APP_ENV=production
FRONTEND_ORIGIN=https://your-app.example.com
```

**Be upfront about the trade-off** if asked: this version sends audio transcripts
to a third party. The privacy guarantee only holds in the local configuration. Say
that plainly — an interviewer will respect the distinction far more than a claim
that survives neither scrutiny nor a glance at the network tab.

Costs a few cents per meeting. Not free, but close.

### Free-tier hosts that can work

| Host | Notes |
|---|---|
| **Render** free | 512 MB, sleeps after 15 min idle. Postgres free for 90 days, then expires |
| **Fly.io** | 3 shared-cpu-1x VMs w/ 256 MB. Needs a card on file, no charge at this scale |
| **Railway** | $5 trial credit, then paid |
| **Neon / Supabase** | Free Postgres that does not expire — pair with any of the above |

Realistic combination: **Render (web) + Neon (Postgres) + Anthropic (LLM)**.

Even with `WHISPER_MODEL=tiny`, transcription on a 512 MB shared CPU is slow —
expect several minutes for a ten-minute meeting, and possible OOM kills. If you go
this route, use short demo recordings.

---

## Option 3 — Deploy the real thing on a real box

If you want the local-model version with a public URL, you need ~8 GB RAM.
Cheapest honest options: Hetzner CX22 (~€4/mo), Oracle Cloud Always Free ARM
(4 vCPU / 24 GB — genuinely free, but availability is famously scarce).

```bash
git clone <your-repo> && cd meetmind
python scripts/bootstrap_env.py
# edit .env: APP_ENV=production, FRONTEND_ORIGIN=https://your-domain
docker compose up -d --build
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull all-minilm
```

Put Caddy or nginx in front for TLS. **`APP_ENV=production` matters** — it turns on
`Secure` cookies and HSTS, and disables `/api/docs`. Without HTTPS in production
the refresh cookie won't be sent at all, and login will appear to silently fail.

---

## Pre-deploy checklist

- [ ] `python scripts/bootstrap_env.py` run on the **server** — never reuse local secrets
- [ ] `.env` is not in git (`git check-ignore .env` should print `.env`)
- [ ] `APP_ENV=production`
- [ ] `FRONTEND_ORIGIN` is your real HTTPS origin — it is the CORS allowlist
- [ ] TLS terminating in front of the app
- [ ] `python scripts/security_check.py` passes against the deployed URL
- [ ] Backups of the `pgdata` volume if the data matters

## The one that will bite you

**`ENCRYPTION_KEY` is not rotatable.** Every transcript, summary and chat message
is encrypted with it. Change it and all existing meetings become permanently
unreadable — there is no recovery, by design. Back it up somewhere safe before you
deploy, and never regenerate it on a machine that already holds data.
