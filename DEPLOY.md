# Deploying Fábula — Railway (backend) + Cloudflare (domain)

First deploy ships **all seven stages, including video** — the render uses ffmpeg
(Ken Burns motion + burned-in captions), which is light enough to host. You'll get a
live URL you can open on your phone.

---

## 1. Put the code on GitHub

Railway builds from a GitHub repo (the build runs in the cloud, so your own machine
doesn't need Python/Node).

1. Create a free account at **github.com** if you don't have one.
2. Click **New repository** → name it `fabula` → **Private** → Create.
3. Upload the `fabula` folder:
   - Easiest no-tools way: on the empty repo page, click **uploading an existing file**
     and drag in the contents of `C:\Users\eiman\Downloads\fabula`
     (the `backend/` folder, `DEPLOY.md`, `.gitignore`).
   - Or, if you use Git/GitHub Desktop, commit and push that folder.
   - The `.gitignore` already keeps secrets and local data out.

## 2. Deploy on Railway

1. Sign in at **railway.app** (use "Login with GitHub").
2. **New Project → Deploy from GitHub repo →** pick your `fabula` repo.
3. In the service **Settings**:
   - **Root Directory:** `backend`   ← important (the Dockerfile lives there)
   - Railway auto-detects the Dockerfile and builds it.
4. Open the **Variables** tab and add:

   | Name | Value |
   |---|---|
   | `FABULA_SECRET` | `IuB9FmHJPbH-9e3NI7MILC-fA_IjTR3Z9EODMySriBA=` |
   | `FABULA_CORS` | `*`  (tighten to your domain later) |

   `FABULA_SECRET` is your app's encryption key for stored API keys — keep it private,
   don't put it in the repo. (It's already excluded by `.gitignore`.)
5. Railway builds and gives you a public URL like `fabula-production.up.railway.app`.
   Open it — you should see the Fábula app. Try `/health` too.

## 3. Point your Cloudflare domain at it

1. In **Railway → service → Settings → Networking → Custom Domain**, enter e.g.
   `app.yourdomain.com`. Railway shows a **CNAME target** (like `xxxx.up.railway.app`).
2. In **Cloudflare → your domain → DNS → Add record**:
   - Type **CNAME**, Name `app`, Target = the Railway target, **Proxied (orange cloud) ON**.
3. Wait a minute; `https://app.yourdomain.com` now serves Fábula with Cloudflare SSL + CDN.

## 4. Use it

- Open the app, click **🔑 Keys**, add your Claude / Fish / Gemini keys (BYOK).
- Create a project (channel + language + style) and **Generate** — all stages run,
  including the ffmpeg video render, and you can download the finished mp4.
- Give the service enough memory (Railway plan): a full-length render is fine on ffmpeg,
  but bump RAM if long videos are slow. One render runs at a time for now.

---

## Known limits of this first deploy (by design)

- **Temporary storage** — Railway's disk resets on redeploy. Projects, keys and files
  are not durable until we add **Postgres** + **Cloudflare R2**.
- **One render at a time** — the single in-process worker handles jobs sequentially; a
  real queue + more workers come when there are concurrent users.
- Keep `FABULA_SECRET` stable — if it changes, previously stored BYOK keys can't be read.

## Roadmap after this deploy
1. Postgres (Railway plugin) for durable projects/keys.
2. Cloudflare R2 for durable video/image storage.
3. A job queue + more render workers for concurrency (and optional Remotion for fancier
   visuals via `FABULA_RENDER_ENGINE=remotion`).
4. Auth (Supabase/Clerk) + Stripe billing.
