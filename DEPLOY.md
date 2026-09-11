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

---

## 5. (Optional) Dedicated render worker — for long / high-quality videos

The video render is the only heavy step. Run it on a **second Railway service** so a
30–60 min render never slows or crashes the main app, and so you can give the worker
lots of RAM without paying for it on the API 24/7. Same repo, same Docker image — only
the start command and a couple of env vars differ. **Requires R2** (the two services
hand assets off through it). If you skip this, everything still works — the API just
renders in-process with automatic quality-stepdown if memory is tight.

**A. Create the worker service**
1. Railway → your project → **New → GitHub Repo →** pick the **same** `fabula` repo.
2. Service **Settings**:
   - **Root Directory:** `backend`
   - **Dockerfile Path:** `Dockerfile.worker`  ← the worker image (adds Node + headless
     Chrome + the Remotion project on top of ffmpeg). The API keeps the lean `Dockerfile`.
   - **Custom Start Command:** leave blank — `Dockerfile.worker` already starts the worker.
   - **Resource Limits:** give it more **Memory** (e.g. 4–8 GB) — this is the box that
     actually renders. Add a **Volume** at `/app/data` if you want scratch space on disk.
3. **Variables** (must match the API where noted):
   | Name | Value |
   |---|---|
   | `FABULA_RENDER_SECRET` | a long random string (same on API + worker) |
   | `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` | same R2 values as the API |
   | `FABULA_VIDEO_HEIGHT` | `1080` (optional — full HD, since this box has the RAM) |
4. Deploy. Check its URL + `/health` → should show `"role":"render-worker"`.

**B. Point the API at the worker**
On the **API** service Variables, add:
   | Name | Value |
   |---|---|
   | `FABULA_RENDER_WORKER_URL` | the worker's public URL (e.g. `https://fabula-worker.up.railway.app`) |
   | `FABULA_RENDER_SECRET` | the **same** secret as the worker |

Redeploy the API. From now on, when a user approves a render, the API dispatches it to
the worker, shows the worker's live progress, and pulls the finished video from R2. To
turn it off, remove `FABULA_RENDER_WORKER_URL` — it renders locally again.

The `Dockerfile.worker` image already sets `FABULA_REMOTION_ENABLED=1`, so once the
worker is up, the **Cinematic (Remotion)** engine works with its **Built-in worker**
backend (Chrome). Good for Shorts; long videos are slow (a 10-min video ≈ 30–60 min).

## 6. (Optional) Remotion on AWS Lambda — fast long-video rendering

The render step offers two Remotion backends: **Built-in worker** (above) and **AWS
Lambda**. Lambda renders a 10-min video in ~1 minute by splitting it across dozens of
functions, and scales to many users. It needs a one-time AWS setup. **Licence:** an app
rendering for paying users is on Remotion's **Automators tier (~$0.01/render, $100/mo
minimum)** — keep Remotion **premium-only** at launch. Solo/private use now is free.

**A. One-time AWS setup (from AWS CloudShell — no tools needed on your machine)**
1. Create an **AWS account** (aws.amazon.com), then open **CloudShell** (icon in the top
   bar of the AWS console) — it's a browser terminal with Node + your credentials built in.
2. In CloudShell, install the Remotion Lambda CLI and deploy the function + the composition:
   ```
   npm i -g @remotion/lambda@4.0.513
   npx remotion lambda functions deploy
   npx remotion lambda sites create https://github.com/bevelui/fabula/.../remotion/src/index.ts --site-name=fabula
   ```
   (Or clone your repo in CloudShell and run `sites create src/index.ts` from `backend/remotion`.)
   Note the printed **function name** and the **serve URL** (the deployed site URL).
3. Create an **IAM user** with Remotion's policy (the CLI prints the exact policy, or see
   remotion.dev/docs/lambda/permissions) and generate an **access key + secret**.

**B. Point the worker at Lambda** — on the **worker** service Variables, add:
   | Name | Value |
   |---|---|
   | `REMOTION_LAMBDA_FUNCTION` | the function name from step A2 |
   | `REMOTION_LAMBDA_SERVE_URL` | the serve URL from step A2 |
   | `REMOTION_LAMBDA_REGION` | e.g. `us-east-1` |
   | `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | the IAM key from step A3 |

Redeploy the worker. Now picking **Remotion → AWS Lambda** at the render step dispatches
to Lambda (assets go by R2 presigned URL; the finished video is pulled back). If Lambda
isn't configured, it safely falls back to the Built-in worker. Keep the AWS keys **only**
on the worker — the API never needs them.

## Roadmap after this deploy
1. Postgres (Railway plugin) for durable projects/keys.
2. Cloudflare R2 for durable video/image storage. ✅ (done)
3. Dedicated render worker for long videos + concurrency. ✅ (section 5)
4. Remotion engine — worker (Chrome) ✅ + AWS Lambda ✅ (sections 5–6). Gate premium at launch.
5. Auth (Supabase/Clerk) + Stripe billing.
