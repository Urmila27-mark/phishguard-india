# 🎣 PhishGuard India — V1 (Ship-Ready)

AI-powered phishing simulation & security awareness training for Indian SMBs.

This is the **complete first version** — product, payments, lead capture, legal
protection, and a deployment path to take real money.

---

## What's actually in this package

```
phishguard-v1/
├── backend/
│   ├── main.py              # FastAPI — campaigns, payments, leads, training
│   ├── database.py          # SQLite — customers, leads, campaigns, payments
│   ├── .env.example         # Copy to .env and fill in your credentials
│   └── templates/
│       ├── hdfc_alert.html
│       ├── gst_notice.html
│       ├── epfo_refund.html
│       └── razorpay_hold.html
├── dashboard/
│   └── app.py                # Streamlit — your internal ops dashboard
├── landing/
│   └── index.html            # Public marketing site (wired to the API)
├── legal/
│   └── authorization_agreement.txt   # Sign this with EVERY customer before launching
└── requirements.txt
```

---

## Part 1 — Run it locally (15 minutes)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure email sending
```bash
cp backend/.env.example backend/.env
```
Edit `backend/.env`:
- Go to **myaccount.google.com → Security → 2-Step Verification → App Passwords**
- Generate an app password for "Mail"
- Set `SMTP_USER` to your Gmail address, `SMTP_PASS` to the 16-character app password

> Skip this and the product still works — campaigns get created and tracked,
> emails just won't physically send. Good for testing the dashboard first.

### 3. Start the backend
```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Start the dashboard (new terminal)
```bash
cd dashboard
streamlit run app.py
```

### 5. Open the landing page
Just open `landing/index.html` directly in your browser, or serve it:
```bash
cd landing
python3 -m http.server 5500
```
Visit `http://localhost:5500`

**The landing page's lead form posts to `http://localhost:8000` by default.**
Leads will show up in the dashboard's "📥 Leads" tab.

---

## Part 2 — Accept real payments (Razorpay)

1. Sign up at **dashboard.razorpay.com** (free, takes 10 minutes, needs basic
   business KYC — even as a sole proprietor/student this works)
2. Go to **Settings → API Keys** → generate a key pair
3. Add to `backend/.env`:
   ```
   RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
   RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxx
   ```
4. Start in **test mode** first (`rzp_test_` prefix) — verify the full flow
   with Razorpay's test cards before switching to live keys.
5. Once ready, switch to live keys (`rzp_live_`) — this requires Razorpay to
   approve your business KYC, which can take a few days. Start this early.

The `/payments/create-order` endpoint creates a Razorpay order; the
`/payments/webhook` endpoint receives the payment confirmation and
automatically activates the customer's plan.

---

## Part 3 — The legal step that protects you (do this before customer #1)

**Never launch a campaign for a real company without a signed authorization.**

1. Open `legal/authorization_agreement.txt`
2. Fill in your details, get it reviewed by a lawyer (~₹5,000–10,000, one-time —
   many firms discount for student founders)
3. Every new customer signs this **before** you upload their employee list
4. Mark them as "Authorized" in the dashboard's 🏢 Customers tab
5. The backend **automatically blocks** any campaign for an unauthorized
   customer — this is enforced in code, not just policy (see `/campaign/create`
   in `main.py`)

This single document is your main legal shield. Do not skip it for your first
"friendly" customer either — bad habits compound.

---

## Part 4 — Deploy it so it's live on the internet

Right now everything runs on `localhost`. To actually take customers:

### Backend (FastAPI) → Railway or Render (free tier works to start)
1. Push this folder to a GitHub repo
2. Connect the repo on **railway.app** or **render.com**
3. Set the start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add your `.env` variables in their dashboard's environment settings
5. Update `BASE_URL` in `.env` to your new public URL
   (e.g. `https://phishguard-api.up.railway.app`)

### Landing page → Vercel or Netlify (free, instant)
1. Drag-and-drop the `landing/` folder onto **vercel.com** or **netlify.com**
2. In `landing/index.html`, find this line near the bottom:
   ```js
   const API_BASE = window.PHISHGUARD_API || 'http://localhost:8000';
   ```
   Change `'http://localhost:8000'` to your deployed backend URL.
3. Buy a domain (₹500-800/year on GoDaddy or Namecheap) and point it at Vercel.

### Dashboard → keep this private
Run the Streamlit dashboard only on your own machine or a private server —
it's your internal ops tool, not something customers should access. If you
need remote access, deploy it behind a password using Streamlit's built-in
auth or a simple reverse-proxy basic-auth rule.

---

## Part 5 — Your first 10 customers (do this in parallel with deployment)

1. Cold-message 20 SMB owners on LinkedIn — offer the free 10-employee audit
2. Get the authorization agreement signed before anything else
3. Run their first campaign, generate the report, show them the dashboard
4. Convert free-audit companies to the Starter plan (₹4,999/mo)
5. Repeat — this is sales work, not more engineering work

---

## What this version does NOT have yet (intentionally — don't build it until you need it)

- WhatsApp simulation (Twilio) — add once 5+ customers ask for it
- Multi-language training beyond English — add once you have non-English customers
- HR system integrations — add once a customer's procurement team requires it
- A full subscription billing system (recurring auto-charge) — for now,
  manually invoice monthly via Razorpay Payment Links until volume justifies automation

Shipping less and proving people will pay is more valuable right now than
building features nobody has asked for yet.

---

## Tech Stack Summary

| Layer       | Tool                              |
|-------------|------------------------------------|
| Backend     | FastAPI + Python + SQLite          |
| Frontend    | Streamlit (internal) + HTML/CSS/JS (public landing) |
| Email       | Gmail SMTP (swap for AWS SES at scale) |
| Payments    | Razorpay                           |
| Hosting     | Railway/Render (API) + Vercel (landing) |
