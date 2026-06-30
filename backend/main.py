import os
import uuid
import random
import smtplib
import csv
import io
import hmac
import hashlib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from jinja2 import Template

from database import init_db, get_conn, seed_demo_data

load_dotenv()
init_db()
seed_demo_data()

app = FastAPI(title="PhishGuard India API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your real domain before going live
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL       = os.getenv("BASE_URL", "http://localhost:8000")
SMTP_HOST      = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", 587))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASS      = os.getenv("SMTP_PASS", "")

RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

PLAN_PRICES = {
    "starter":    499900,    # in paise = ₹4,999
    "growth":     1299900,   # ₹12,999
    "enterprise": 2999900,   # ₹29,999
}
PLAN_EMPLOYEE_LIMITS = {"starter": 25, "growth": 100, "enterprise": 999999}

TEMPLATE_META = {
    "hdfc_alert": {
        "subject": "⚠️ HDFC Bank: Unusual Login Detected – Verify Immediately",
        "file": "hdfc_alert.html",
        "from_name": "HDFC Bank Security",
    },
    "gst_notice": {
        "subject": "GST Notice: Discrepancy in GSTR-3B Filing | Action Required",
        "file": "gst_notice.html",
        "from_name": "GST Department",
    },
    "epfo_refund": {
        "subject": "✅ EPFO: Your PF Refund Has Been Approved",
        "file": "epfo_refund.html",
        "from_name": "EPFO",
    },
    "razorpay_hold": {
        "subject": "🚨 Razorpay: Your Settlement Has Been Withheld",
        "file": "razorpay_hold.html",
        "from_name": "Razorpay",
    },
}

SIM_DISCLOSURE = (
    "This is a PhishGuard India security-awareness simulation, run with the explicit, "
    "signed authorization of your employer for employee training purposes. No real "
    "financial institution, government body, or company is involved. If you have "
    "concerns, contact your IT/security team."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def render_template(template_name: str, context: dict) -> str:
    path = os.path.join(TEMPLATES_DIR, TEMPLATE_META[template_name]["file"])
    with open(path, encoding="utf-8") as f:
        content = f.read()
    context.setdefault("sim_disclosure", SIM_DISCLOSURE)
    return Template(content).render(**context)


def send_email(to_email: str, subject: str, html_body: str, from_name: str):
    if not (SMTP_USER and SMTP_PASS):
        return False, "SMTP not configured"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{SMTP_USER}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        return True, None
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Health / root
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <h2>PhishGuard India API — running ✅</h2>
    <p>Endpoints: /leads/create · /campaign/create · /track/{token} ·
    /payments/create-order · /payments/webhook · /analytics/* </p>
    """


# ---------------------------------------------------------------------------
# LEADS — captured from the landing page "Get free audit" form
# ---------------------------------------------------------------------------
@app.post("/leads/create")
async def create_lead(
    email: str = Form(...),
    company_name: str = Form(""),
    phone: str = Form(""),
    source: str = Form("landing_page"),
):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO leads (email, company_name, phone, source) VALUES (?, ?, ?, ?)",
        (email, company_name, phone, source),
    )
    conn.commit()
    lead_id = c.lastrowid
    conn.close()
    return {"status": "ok", "lead_id": lead_id, "message": "Thanks! We'll reach out within 24 hours with your free audit."}


@app.get("/leads/all")
def get_leads():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# CUSTOMERS
# ---------------------------------------------------------------------------
@app.post("/customers/create")
async def create_customer(
    company_name: str = Form(...),
    contact_name: str = Form(...),
    contact_email: str = Form(...),
    phone: str = Form(""),
    plan: str = Form("trial"),
):
    conn = get_conn()
    c = conn.cursor()
    employee_limit = PLAN_EMPLOYEE_LIMITS.get(plan, 10)
    try:
        c.execute(
            """INSERT INTO customers (company_name, contact_name, contact_email, phone, plan, employee_limit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (company_name, contact_name, contact_email, phone, plan, employee_limit),
        )
        conn.commit()
        customer_id = c.lastrowid
    except Exception as e:
        conn.close()
        return JSONResponse({"error": str(e)}, status_code=400)
    conn.close()
    return {"customer_id": customer_id, "status": "created"}


@app.post("/customers/{customer_id}/sign-authorization")
def sign_authorization(customer_id: int):
    """Marks that the customer has signed the legal authorization MoU
    permitting PhishGuard to run simulated phishing campaigns on their employees."""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE customers SET authorization_signed = 1, authorization_signed_at = CURRENT_TIMESTAMP WHERE id = ?",
        (customer_id,),
    )
    conn.commit()
    conn.close()
    return {"status": "authorization recorded"}


@app.get("/customers/all")
def get_customers():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM customers ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# PAYMENTS — Razorpay
# ---------------------------------------------------------------------------
@app.post("/payments/create-order")
async def create_order(customer_id: int = Form(...), plan: str = Form(...)):
    """Creates a Razorpay order for a one-time or first subscription payment."""
    if plan not in PLAN_PRICES:
        return JSONResponse({"error": "Invalid plan"}, status_code=400)

    if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
        return JSONResponse({
            "error": "Razorpay not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env",
            "demo_mode": True,
            "would_charge": PLAN_PRICES[plan] / 100,
        }, status_code=200)

    try:
        import razorpay
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        order = client.order.create({
            "amount": PLAN_PRICES[plan],
            "currency": "INR",
            "notes": {"customer_id": str(customer_id), "plan": plan},
        })

        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT INTO payments (customer_id, razorpay_order_id, amount, plan, status)
               VALUES (?, ?, ?, ?, 'created')""",
            (customer_id, order["id"], PLAN_PRICES[plan], plan),
        )
        conn.commit()
        conn.close()

        return {
            "order_id": order["id"],
            "amount": PLAN_PRICES[plan],
            "currency": "INR",
            "key_id": RAZORPAY_KEY_ID,
        }
    except ImportError:
        return JSONResponse({"error": "razorpay package not installed. Run: pip install razorpay"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/payments/webhook")
async def razorpay_webhook(request: Request):
    """Razorpay calls this when a payment succeeds/fails. Verifies signature, updates DB."""
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if RAZORPAY_WEBHOOK_SECRET:
        expected = hmac.new(
            RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    import json
    payload = json.loads(body)
    event = payload.get("event", "")

    if event == "payment.captured":
        payment_entity = payload["payload"]["payment"]["entity"]
        order_id = payment_entity.get("order_id")
        payment_id = payment_entity.get("id")

        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE payments SET status = 'captured', razorpay_payment_id = ? WHERE razorpay_order_id = ?",
            (payment_id, order_id),
        )
        row = c.execute("SELECT customer_id, plan FROM payments WHERE razorpay_order_id = ?", (order_id,)).fetchone()
        if row:
            c.execute(
                "UPDATE customers SET plan = ?, status = 'active', employee_limit = ? WHERE id = ?",
                (row["plan"], PLAN_EMPLOYEE_LIMITS.get(row["plan"], 25), row["customer_id"]),
            )
        conn.commit()
        conn.close()

    return {"status": "ok"}


@app.get("/payments/all")
def get_payments():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM payments ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# CAMPAIGNS
# ---------------------------------------------------------------------------
@app.post("/campaign/create")
async def create_campaign(
    name: str = Form(...),
    template: str = Form(...),
    csv_file: UploadFile = File(...),
    customer_id: int = Form(None),
):
    if template not in TEMPLATE_META:
        return JSONResponse({"error": f"Unknown template '{template}'"}, status_code=400)

    # Check authorization if linked to a real customer
    if customer_id:
        conn_check = get_conn()
        cust = conn_check.execute("SELECT authorization_signed FROM customers WHERE id = ?", (customer_id,)).fetchone()
        conn_check.close()
        if cust and not cust["authorization_signed"]:
            return JSONResponse(
                {"error": "Customer has not signed the authorization agreement. Campaign blocked."},
                status_code=403,
            )

    raw = await csv_file.read()
    decoded = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))

    rows = []
    for row in reader:
        email = (row.get("email") or row.get("Email") or "").strip()
        emp_name = (row.get("name") or row.get("Name") or email.split("@")[0]).strip()
        dept = (row.get("department") or row.get("Department") or "").strip()
        if email:
            rows.append({"email": email, "name": emp_name, "department": dept})

    if not rows:
        return JSONResponse({"error": "CSV has no valid rows. Need columns: email, name, department (optional)"}, status_code=400)

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO campaigns (customer_id, name, template) VALUES (?, ?, ?)",
        (customer_id, name, template),
    )
    campaign_id = c.lastrowid

    meta = TEMPLATE_META[template]
    sent, failed = [], []

    for row in rows:
        token = str(uuid.uuid4())
        track_url = f"{BASE_URL}/track/{token}"

        html = render_template(template, {
            "name": row["name"],
            "track_url": track_url,
            "datetime": datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "rand1": random.randint(10, 99),
            "rand2": random.randint(1, 254),
        })

        c.execute(
            "INSERT INTO recipients (campaign_id, email, name, department, token) VALUES (?, ?, ?, ?, ?)",
            (campaign_id, row["email"], row["name"], row["department"], token),
        )

        ok, err = send_email(row["email"], meta["subject"], html, meta["from_name"])
        if ok:
            sent.append(row["email"])
        else:
            failed.append({"email": row["email"], "error": err})

    conn.commit()
    conn.close()

    return {
        "campaign_id": campaign_id,
        "campaign_name": name,
        "template": template,
        "total": len(rows),
        "sent": len(sent),
        "failed": len(failed),
        "failures": failed[:5],
        "message": "Campaign launched ✅" if not failed else f"Campaign launched — {len(failed)} email(s) failed to send",
    }


@app.get("/track/{token}", response_class=HTMLResponse)
def track_click(token: str, request: Request):
    conn = get_conn()
    c = conn.cursor()
    recipient = c.execute("SELECT * FROM recipients WHERE token = ?", (token,)).fetchone()
    if not recipient:
        conn.close()
        return HTMLResponse("<h3>Invalid or expired link.</h3>", status_code=404)

    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "unknown")
    c.execute("INSERT INTO clicks (token, ip, user_agent) VALUES (?, ?, ?)", (token, ip, ua))
    conn.commit()

    campaign = c.execute("SELECT template FROM campaigns WHERE id = ?", (recipient["campaign_id"],)).fetchone()
    conn.close()

    return HTMLResponse(training_page(recipient["name"] or "there", campaign["template"] if campaign else "hdfc_alert"))


def training_page(name: str, template: str) -> str:
    # ── Forensic breakdowns: the EXACT signals present in THIS specific email ──
    forensics_by_template = {
        "hdfc_alert": {
            "sender_shown": "HDFC Bank Security",
            "sender_real": "security-alerts@hdfcbank-verify.com",
            "sender_correct": "Real HDFC emails only ever come from @hdfcbank.com — nothing else, no hyphens, no extra words.",
            "red_flags": [
                ("The domain", "hdfcbank-verify.com is NOT hdfcbank.com. Scammers add words like '-verify', '-secure', '-alert' to real brand names to look legitimate at a glance."),
                ("The urgency", "\"24 hours or your account is suspended\" is a manufactured deadline. Real banks do not threaten suspension over email — they call you or notify you in-app."),
                ("The generic threat", "\"Unusual login detected\" with no specific device, browser, or app name is vague on purpose — it has to apply to anyone."),
                ("The button, not the link", "The email hides the real destination behind a button labelled \"Verify Now\" — hover-checking is exactly what this trick is designed to discourage."),
            ],
            "verify_action": "Open the HDFC Bank app directly (not from this email) or call 1800-202-6161 — the number printed on the back of your physical debit/credit card.",
            "cost": "If this had been real and you'd entered your NetBanking password and OTP, an attacker could have emptied your account within minutes — UPI transfers are typically irreversible.",
        },
        "gst_notice": {
            "sender_shown": "GST Department",
            "sender_real": "notices@gst-gov-india.com",
            "sender_correct": "Real GST communication happens inside the GST portal (gst.gov.in) after you log in — not via unsolicited email with a clickable link.",
            "red_flags": [
                ("The domain", "gst-gov-india.com is not a real Indian government domain. Official government sites end in .gov.in, never .com."),
                ("The fear lever", "Threatening GSTIN suspension and bank account attachment is designed to trigger panic in accounts/finance staff specifically."),
                ("The fake reference number", "Reference numbers like 'GST/NOT/4782/2025' are made up to look official — there's no way to verify them without logging into the real portal anyway."),
                ("The artificial deadline", "\"7 working days\" pressure is used to stop you from calmly verifying through official channels first."),
            ],
            "verify_action": "Log in directly at gst.gov.in (type it yourself, never click a link) and check the official Notices & Orders tab. If nothing's there, the email was fake.",
            "cost": "Entering company GST credentials here could let an attacker file fraudulent returns or access your company's complete tax and banking history.",
        },
        "epfo_refund": {
            "sender_shown": "EPFO",
            "sender_real": "epfo-refunds@gov-india-epfo.com",
            "sender_correct": "EPFO communicates through the official unifiedportal-mem.epfindia.gov.in member portal — never asks for bank re-verification by email.",
            "red_flags": [
                ("The domain", "gov-india-epfo.com is a fake construction — real government domains never put 'gov' in the middle of a .com address."),
                ("The reward bait", "Promising unexpected money (a refund you didn't request) lowers your guard faster than a threat does — greed bypasses suspicion."),
                ("The bank verification ask", "EPFO never asks you to 're-verify bank details' via an email link — refunds process automatically to your UAN-linked account."),
                ("The artificial deadline", "\"Claim within 72 hours\" exists purely to stop you from checking the real portal first."),
            ],
            "verify_action": "Log in directly at unifiedportal-mem.epfindia.gov.in and check your claim status there. Never enter bank details from an email link.",
            "cost": "Entering bank details here hands an attacker everything needed to redirect your real PF withdrawals to their own account.",
        },
        "razorpay_hold": {
            "sender_shown": "Razorpay",
            "sender_real": "noreply@razorpay-settlements.net",
            "sender_correct": "Real Razorpay emails come from @razorpay.com only. Razorpay never uses a separate '-settlements' domain.",
            "red_flags": [
                ("The domain", "razorpay-settlements.net is not razorpay.com. The .net extension and extra word are both fabricated."),
                ("The cash-flow panic", "Threatening a withheld settlement targets business owners' single biggest fear — not getting paid."),
                ("The KYC re-verification ask", "Razorpay never requires KYC re-verification through an emailed link — it happens inside your dashboard only, when YOU initiate it."),
                ("The 48-hour threat", "\"Funds returned to customers\" in 48 hours is designed to make you click before calling support to confirm."),
            ],
            "verify_action": "Log in directly at dashboard.razorpay.com and check Settlements. If there's no real hold showing there, the email is fake.",
            "cost": "Completing 'KYC verification' here gives an attacker direct access to your payment gateway account and all customer transaction data.",
        },
    }

    f = forensics_by_template.get(template, forensics_by_template["hdfc_alert"])

    redflag_html = "".join(f"""
      <div class="redflag">
        <div class="redflag-num">{i+1}</div>
        <div class="redflag-text"><h4>{title}</h4><p>{body}</p></div>
      </div>""" for i, (title, body) in enumerate(f["red_flags"]))

    return f"""
<!DOCTYPE html>
<html><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>PhishGuard – Security Training</title>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#0f0f13; color:#e8e8ec; font-family:'Segoe UI',Arial,sans-serif; min-height:100vh; padding:24px; }}
.wrap {{ max-width:640px; margin:0 auto; }}
.card {{ background:#1a1b22; border:1px solid #2a2d38; border-radius:12px; padding:36px; margin-bottom:20px; }}
.icon {{ font-size:48px; margin-bottom:12px; text-align:center; }}
h1 {{ font-size:23px; font-weight:700; color:#ff4c29; margin-bottom:10px; text-align:center; }}
.subtitle {{ color:#9ca3af; font-size:14.5px; margin-bottom:8px; line-height:1.6; text-align:center; }}
.name {{ color:#fff; font-weight:600; }}
.badge {{ display:block; width:fit-content; margin:0 auto 20px; background:rgba(255,76,41,0.1); border:1px solid rgba(255,76,41,0.3); color:#ff4c29; font-size:11px; padding:5px 14px; border-radius:20px; letter-spacing:1px; text-transform:uppercase; }}

.section-label {{ font-size:11px; letter-spacing:1.5px; text-transform:uppercase; color:#ff4c29; font-weight:700; margin-bottom:14px; }}

.sender-compare {{ background:#111318; border-radius:8px; padding:18px; margin-bottom:8px; }}
.sender-row {{ display:flex; justify-content:space-between; align-items:center; padding:8px 0; font-size:13.5px; }}
.sender-row .lbl {{ color:#6b7280; }}
.sender-row .val {{ font-family:monospace; }}
.val-fake {{ color:#ff4c29; }}
.val-real {{ color:#00d4aa; }}
.sender-note {{ font-size:12.5px; color:#9ca3af; margin-top:10px; padding-top:10px; border-top:1px solid #2a2d38; line-height:1.6; }}

.redflag {{ display:flex; gap:14px; padding:14px 0; border-bottom:1px solid #2a2d38; }}
.redflag:last-child {{ border-bottom:none; }}
.redflag-num {{ width:24px; height:24px; border-radius:50%; background:rgba(255,76,41,0.15); color:#ff4c29; font-size:12px; font-weight:700; display:flex; align-items:center; justify-content:center; flex-shrink:0; margin-top:1px; }}
.redflag-text h4 {{ font-size:14px; font-weight:600; color:#fff; margin-bottom:4px; }}
.redflag-text p {{ font-size:13px; color:#9ca3af; line-height:1.6; }}

.cost-box {{ background:rgba(255,76,41,0.08); border:1px solid rgba(255,76,41,0.25); border-radius:8px; padding:16px 18px; margin-bottom:8px; }}
.cost-box .lbl {{ font-size:11px; letter-spacing:1px; text-transform:uppercase; color:#ff4c29; font-weight:700; margin-bottom:6px; }}
.cost-box p {{ font-size:13.5px; color:#e8e8ec; line-height:1.6; }}

.verify-box {{ background:rgba(0,212,170,0.08); border:1px solid rgba(0,212,170,0.25); border-radius:8px; padding:16px 18px; }}
.verify-box .lbl {{ font-size:11px; letter-spacing:1px; text-transform:uppercase; color:#00d4aa; font-weight:700; margin-bottom:6px; }}
.verify-box p {{ font-size:13.5px; color:#e8e8ec; line-height:1.6; }}

.checklist {{ display:flex; flex-direction:column; gap:10px; }}
.check-item {{ display:flex; gap:12px; align-items:flex-start; font-size:13.5px; color:#d1d5db; line-height:1.5; }}
.check-item .box {{ width:18px; height:18px; border:1.5px solid #4b5563; border-radius:4px; flex-shrink:0; margin-top:1px; }}

.quiz {{ background:#111318; border-radius:8px; padding:20px; }}
.quiz-q {{ font-size:14px; font-weight:600; color:#fff; margin-bottom:14px; }}
.quiz-opt {{ display:block; width:100%; text-align:left; background:#1a1b22; border:1px solid #2a2d38; color:#d1d5db; padding:11px 16px; border-radius:6px; font-size:13.5px; margin-bottom:8px; cursor:pointer; transition:all 0.15s; }}
.quiz-opt:hover {{ border-color:#4b5563; }}
.quiz-feedback {{ display:none; margin-top:12px; padding:12px 14px; border-radius:6px; font-size:13px; line-height:1.6; }}
.quiz-feedback.correct {{ background:rgba(0,212,170,0.1); border:1px solid rgba(0,212,170,0.3); color:#00d4aa; }}
.quiz-feedback.wrong {{ background:rgba(255,76,41,0.1); border:1px solid rgba(255,76,41,0.3); color:#ff4c29; }}

.footer-note {{ font-size:11px; color:#4b5563; margin-top:8px; line-height:1.6; text-align:center; }}
</style></head>
<body>
<div class="wrap">

  <div class="card">
    <div class="icon">🎣</div>
    <div class="badge">Security Training — Confidential</div>
    <h1>You clicked a simulated phishing link</h1>
    <p class="subtitle">Don't worry, <span class="name">{name}</span> — this was a safe simulation. No data was stolen. But here's exactly what fooled you, so it never works on you again.</p>
  </div>

  <div class="card">
    <div class="section-label">① The sender — side by side</div>
    <div class="sender-compare">
      <div class="sender-row"><span class="lbl">What you saw:</span><span class="val">{f["sender_shown"]}</span></div>
      <div class="sender-row"><span class="lbl">Actual address:</span><span class="val val-fake">{f["sender_real"]}</span></div>
      <div class="sender-note">✅ {f["sender_correct"]}</div>
    </div>
  </div>

  <div class="card">
    <div class="section-label">② Every red flag in this exact email</div>
    {redflag_html}
  </div>

  <div class="card">
    <div class="cost-box">
      <div class="lbl">⚠ What this would have cost you, for real</div>
      <p>{f["cost"]}</p>
    </div>
    <div class="verify-box">
      <div class="lbl">✅ What to do instead, every time</div>
      <p>{f["verify_action"]}</p>
    </div>
  </div>

  <div class="card">
    <div class="section-label">③ Your 10-second check — use this on EVERY email, forever</div>
    <div class="checklist">
      <div class="check-item"><div class="box"></div>Does the sender's domain EXACTLY match the real company's domain — not similar, not close, exact?</div>
      <div class="check-item"><div class="box"></div>Is the email creating urgency, fear, or excitement to make me act fast?</div>
      <div class="check-item"><div class="box"></div>Is it asking me to click a link or button instead of logging in directly myself?</div>
      <div class="check-item"><div class="box"></div>Did I request this, or is it unprompted?</div>
      <div class="check-item"><div class="box"></div>Can I verify this independently — by typing the real website myself, or calling an official number — instead of trusting anything in this email?</div>
    </div>
  </div>

  <div class="card">
    <div class="section-label">④ Quick check — does this skill generalize?</div>
    <div class="quiz">
      <div class="quiz-q">You get an email from "support@amaz0n-orders.com" saying your order is delayed and you must confirm your address within 2 hours or it will be cancelled. What do you do?</div>
      <button class="quiz-opt" onclick="showFeedback(this, 'wrong')">Click the link quickly — 2 hours isn't much time</button>
      <button class="quiz-opt" onclick="showFeedback(this, 'wrong')">Reply asking them to confirm it's really Amazon</button>
      <button class="quiz-opt" onclick="showFeedback(this, 'correct')">Ignore the email and check my order status by typing amazon.in directly into my browser</button>
      <div class="quiz-feedback correct" id="feedback-correct">✅ Exactly right. The domain "amaz0n-orders.com" (with a zero instead of an 'o') and the artificial 2-hour deadline are both classic phishing signals — just like the email you clicked today. You're already getting better at spotting this.</div>
      <div class="quiz-feedback wrong" id="feedback-wrong">❌ Not quite — both of those options still engage with the suspicious email. The safest move is always to ignore it completely and verify independently, exactly like the "what to do instead" step above.</div>
    </div>
  </div>

  <p class="footer-note">{SIM_DISCLOSURE}</p>
</div>

<script>
function showFeedback(btn, result) {{
  document.querySelectorAll('.quiz-opt').forEach(b => b.disabled = true);
  document.getElementById('feedback-' + result).style.display = 'block';
  if (result === 'correct') {{ btn.style.borderColor = '#00d4aa'; btn.style.color = '#00d4aa'; }}
  else {{ btn.style.borderColor = '#ff4c29'; btn.style.color = '#ff4c29'; }}
}}
</script>
</body></html>
"""


# ---------------------------------------------------------------------------
# ANALYTICS
# ---------------------------------------------------------------------------
@app.get("/analytics/campaigns")
def get_campaigns():
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.id, c.name, c.template, c.created_at, c.customer_id,
               COUNT(DISTINCT r.id) AS total_sent,
               COUNT(DISTINCT cl.token) AS total_clicks
        FROM campaigns c
        LEFT JOIN recipients r ON r.campaign_id = c.id
        LEFT JOIN clicks cl ON cl.token = r.token
        GROUP BY c.id ORDER BY c.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/analytics/campaign/{campaign_id}")
def get_campaign_detail(campaign_id: int):
    conn = get_conn()
    campaign = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    if not campaign:
        conn.close()
        return JSONResponse({"error": "Not found"}, status_code=404)

    recipients = conn.execute("""
        SELECT r.email, r.name, r.department, r.sent_at,
               COUNT(cl.id) AS click_count, MIN(cl.clicked_at) AS first_click
        FROM recipients r
        LEFT JOIN clicks cl ON cl.token = r.token
        WHERE r.campaign_id = ?
        GROUP BY r.id ORDER BY click_count DESC, r.email
    """, (campaign_id,)).fetchall()
    conn.close()
    return {"campaign": dict(campaign), "recipients": [dict(r) for r in recipients]}


@app.get("/analytics/preview/{template}")
def preview_template(template: str):
    if template not in TEMPLATE_META:
        return JSONResponse({"error": "Unknown template"}, status_code=400)
    html = render_template(template, {
        "name": "Priya Sharma", "track_url": "#",
        "datetime": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        "rand1": 47, "rand2": 182,
    })
    return HTMLResponse(html)


@app.get("/analytics/compliance-report/{customer_id}")
def compliance_report_data(customer_id: int):
    """Returns the data needed to render a CERT-In/RBI compliance PDF for a customer."""
    conn = get_conn()
    customer = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        conn.close()
        return JSONResponse({"error": "Customer not found"}, status_code=404)

    campaigns = conn.execute("""
        SELECT c.id, c.name, c.template, c.created_at,
               COUNT(DISTINCT r.id) AS total_sent,
               COUNT(DISTINCT cl.token) AS total_clicks
        FROM campaigns c
        LEFT JOIN recipients r ON r.campaign_id = c.id
        LEFT JOIN clicks cl ON cl.token = r.token
        WHERE c.customer_id = ?
        GROUP BY c.id ORDER BY c.created_at DESC
    """, (customer_id,)).fetchall()
    conn.close()

    return {
        "customer": dict(customer),
        "campaigns": [dict(c) for c in campaigns],
        "generated_at": datetime.now().isoformat(),
    }