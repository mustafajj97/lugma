# Lugma: every food offer in Bahrain, in one place

A phone app (PWA) that gathers food offers from Talabat, restaurants' Instagram posts and Bahrain
press, tags them by cuisine and deal type, and **refreshes itself every morning**. Expired offers are
never shown.

```
GitHub Actions (06:00 Bahrain daily, or the app's Refresh button)      GitHub Pages            Your phone
  python refresh.py ─── collects offers ───▶ web/ + data/offers.json ──▶ Lugma (home-screen app)
```

You can also run it on your PC (`Start Lugma.bat`). The PC version reads the same data files and adds a
**Refresh** button and **Settings**.

---

## How it keeps offers current

Each offer carries a **valid-until date**. The app compares it with your phone's own clock, so an
expired offer disappears even if you open the app days after the last refresh.

| Source | Valid until |
|---|---|
| **Talabat** | Re-checked every morning. An offer that isn't re-confirmed disappears after 1 day. Cards say "Price checked on Talabat 3h ago". |
| **Instagram** | The end date written in the post ("until 30 Sept", "ends July 31st", "today only", "this weekend", "حتى 25 سبتمبر", …). If the post doesn't say, it's shown for **7 days** after posting. "Every Monday"-style deals are marked **Recurring deal** and kept for 30 days. |
| **News** | Same rules as Instagram, with a 10-day default. |
| **Added by me** | The "Ends on" date you enter, or 2 weeks if you leave it blank. Saved on that device only. |

If the daily refresh ever fails, a banner says when offers were last updated. The expiry rules still apply.
**Sort → Ending soonest** puts deals that are about to end first.

---

## One-time setup (about 10 minutes, all free)

Everything runs on GitHub: the daily refresh **and** the website (GitHub Pages). No other accounts, no
payment details, no secrets to copy around.

### 1. Create a GitHub account
Sign up at <https://github.com/signup> if you don't have one. The free plan is all you need.

### 2. Create an empty repository
- Top-right **+** → **New repository**.
- **Repository name:** `lugma`
- **Public** (GitHub Pages hosting is free only for public repos. The code and offers are public info, and there's nothing private in here.)
- Leave everything else unticked (no README, no .gitignore). **Create repository**.

### 3. Upload the code
From this folder (Claude can run these for you):
```
git remote add origin https://github.com/<your-username>/lugma.git
git push -u origin main
```
The first push opens a browser window to sign in to GitHub. That's normal.

### 4. Turn on the website
In the repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**. That's the only setting.

### 5. Run the first refresh
In the repo: **Actions** tab → if asked, click **"I understand my workflows, go ahead and enable them"** →
**Refresh offers** (left) → **Run workflow** → keep "news,instagram,talabat" → **Run workflow**.
It takes about 20 minutes. When it shows a green tick, your app is live at:

**`https://<your-username>.github.io/lugma/`**

From now on it refreshes **every morning at 6:00 Bahrain time**, by itself.

### 6. Put it on your phone
Open that address in **Safari** → **Share** → **Add to Home Screen**. It now opens like an app.

### 7. (Optional) Turn on the Refresh button on your phone
The daily refresh needs nothing from you. To also refresh **on demand**, the app needs a GitHub key that
can only start this one job:
1. github.com → your photo → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. **Name:** `Lugma refresh`, **Expiration:** 1 year.
3. **Repository access → Only select repositories → lugma**.
4. **Permissions → Repository permissions → Actions → Read and write**. Leave everything else as is.
5. **Generate token**, copy it.
6. In the app tap **Refresh** → paste the key (the repository `your-username/lugma` is filled in for you) → **Save**.

Then **Refresh → Quick** (Instagram + news, ~3 min) or **Full** (incl. Talabat, ~20 min). The app shows
progress and loads the new offers when done. You can close it meanwhile, since the refresh runs on GitHub.
The key stays on your phone only, and all it can do is start or check this app's refresh.

### What it costs
**Nothing.** Public repos get unlimited free GitHub Actions minutes and free GitHub Pages hosting. There's
no card on file, so there's nothing to be charged. The job makes a tiny automatic commit every ~25 days
because GitHub pauses schedules in repos with no activity for 60 days.

### Changing settings
Delivery areas and Instagram accounts to follow live in `config.json`. Edit it on github.com (pencil icon),
or use ⚙ Settings in the PC app and push. The next refresh uses them.

### If something goes wrong
- A refresh that fails is marked with a red ✗ in the Actions tab and GitHub emails you. Offers from the
  last good refresh stay until they expire, and the app shows a banner saying when it last updated.
- **Talabat may block GitHub's servers.** The first run (step 5) will tell. If the "Collect offers" step
  says Talabat returned no restaurants, the fallback is refreshing Talabat from the PC.

---

## Using it

- **Search** covers restaurants, dishes and deal wording: `karahi`, `zinger`, `buy 1 get 1`, `50%`. A `%` term means "at least that discount".
- **Cuisine chips:** Pakistani, Indian, Biryani, Burgers, Pizza, Shawarma, Arabic, Grills, Desserts, Coffee and more.
  A restaurant also counts when just one of its discounted dishes matches.
- **Deal-type chips:** 50% off or more · Buy 1 Get 1 · % off · Free item · Combos & meal deals · Fixed-price deals ·
  Day & time deals · Unlimited & buffets · Free delivery. They're detected from dish names and captions (English and Arabic).
- **Filters & sort** (folded behind one button on phones): delivery vs dine-in, sources, minimum discount, area, "New since last week".
- **+ Add offer** saves deals you spot yourself, like flyers or mall promos.

## Where offers come from

| Source | What you get |
|---|---|
| **Talabat** | Every restaurant with an offer in your chosen delivery areas, with **each discounted dish's old and new price** (~900 restaurants, ~14,000 dishes) |
| **Instagram** | Recent offer posts from Bahrain restaurants, mostly dine-in or pickup, found through DuckDuckGo because Instagram needs a login |
| **News** | Food promotions covered by the Bahrain press |

## Things to know

- **Jahez and Keeta aren't included.** Jahez blocks automated access and Keeta has no public web menu.
- **Instagram depends on DuckDuckGo**, which limits bursts of searches. Each run does a rotating batch and
  results build up across days. Adding restaurant handles in `config.json` → `igAccounts` helps most.
- Talabat prices are delivery prices. Dine-in prices can differ.

## Files

```
refresh.py              command-line refresh (what the daily job runs)
engine.py               shared refresh logic: collect → stamp valid-until → drop expired → write web/data/
server.py               PC app: serves web/ + Refresh/Settings API   (Start Lugma.bat)
config.json             areas, Instagram accounts/phrases, validity windows
collectors/             talabat.py · instagram.py · news.py · cuisine.py · freshness.py (end-date parsing)
web/                    the app: index.html, app.js, style.css, sw.js, manifest, icons
web/data/               offers.json + state.json (generated; not committed — the daily job reads them back from the site)
.github/workflows/      refresh.yml — the daily job (also started by the app's Refresh button)
```
