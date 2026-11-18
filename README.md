# 🏠 E-Homely — Online Food Ordering for a Campus Canteen

**E-Homely** is a Django web app for a home-style Kerala canteen near the campus. Students and staff browse a meal-wise menu, pay online, and get a **4-digit token** to collect their food at the counter — no standing in long queues.

> Pay online → get a token → watch the status update live → collect hot food.

---

## ✨ Features

### Customer side
- **Meal-wise menu** — Breakfast (7:00–10:30 AM), Lunch (12:00–3:00 PM) and Dinner (7:00–10:00 PM), each with its own dishes, photos and prices.
- **Cart & checkout** — the cart is kept in the browser (`localStorage`); only name and a 10-digit phone number are needed. Phone numbers are cleaned automatically (`+91`, `91-`, leading `0`).
- **One meal per order** — a cart can't mix dishes from different meal times.
- **Pre-orders** — if a meal's window has already passed, the order is automatically dated for tomorrow.
- **Online payment (Razorpay)** — full payment up front. Confirmed by both the browser callback *and* a webhook, so a payment isn't lost if the tab is closed.
- **Live token page** — the 4-digit token page refreshes every 5 seconds: `New → Preparing → Ready → Picked up`.
- **Self-service cancellation** — customers can cancel while the order is still `New` (or `Out of stock`); the payment is refunded automatically.
- **Daily limits** — popular dishes (Meals, Biriyani) are capped per day (75 by default); the app shows "only N left" or "sold out".
- **Order limit** — a phone number can hold at most **2 open orders** at a time.
- **Assistant chatbot** — a floating "E-Homely Assistant" that answers questions about the menu, timings, prices, payment, cancellation and location using live data from the database. It is rule-based (keyword matching), so it needs no external AI service.
- **Responsive UI** — separate phone and desktop templates, chosen from screen width (with a user-agent fallback).
- **About & Location pages**.

### Staff side
- **Kitchen dashboard** (`/staff/`) — live list of paid, open orders; move them through `New → Preparing → Ready → Picked up`, or mark as `Cancelled` / `Out of stock`.
- **Refunds** — cancelling an order refunds it; if Razorpay can't be reached, a **retry refund** button is available.
- **Stock & menu management** (`/staff/menu/`) — toggle dishes in/out of stock and add new dishes with a photo.
- **Django admin** (`/admin/`) — edit dishes, prices, daily limits, orders, and the site-wide **Accepting orders** switch.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Django 4.2 |
| Database | SQLite (switch to PostgreSQL for heavy production use) |
| Payments | Razorpay (Orders API, refunds, webhook) |
| Frontend | Django templates + vanilla HTML / CSS / JavaScript |
| Static files | WhiteNoise |
| Images | Pillow (uploaded dish photos are resized to 800 px and saved as WebP) |
| Server / hosting | Gunicorn · Render (`build.sh` included) |

---

## 📁 Project Structure

```
E-Homely/
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── build.sh                  # Render build script
│   ├── .env.example              # template for environment variables
│   ├── config/                   # settings, root URLs, wsgi/asgi
│   └── orders/                   # the single Django app
│       ├── models.py             # Dish, Order, OrderItem, SiteSetting
│       ├── views.py              # customer + staff views, meal windows, limits
│       ├── urls.py
│       ├── payments.py           # Razorpay: create order, verify, webhook, refund
│       ├── chatbot.py            # rule-based assistant
│       ├── staff_auth.py         # staff-only login/logout
│       ├── ui.py                 # phone vs. desktop template switching
│       ├── admin.py
│       ├── tests.py, test_flow.py
│       ├── management/commands/attach_dish_images.py
│       └── migrations/           # includes seed data for dishes and prices
├── frontend/
│   ├── templates/orders/         # phone templates
│   │   └── desktop/              # laptop / large-screen templates
│   └── static/orders/            # CSS, JS (cart, chatbot, nav), logo, favicons, hero image
└── media/dishes/                 # dish photos and token images
```

---

## 🚀 Getting Started (Local Development)

### Prerequisites
- Python 3.10 or newer
- pip and Git

### 1. Clone the repository
```bash
git clone https://github.com/anandhuuuuuuh/E-Homely.git
cd E-Homely
```

### 2. Create and activate a virtual environment
```bash
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 4. Configure environment variables
```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```
Open `backend/.env` and set at least `DJANGO_DEBUG=1` and a `DJANGO_SECRET_KEY`. The `.env` file is loaded automatically.

### 5. Set up the database
```bash
python manage.py migrate
```
The migrations also **seed the full menu** (breakfast, lunch, dinner) with prices, daily limits and photos, and create a default staff account (see [Staff login](#-staff-login)).

### 6. Run the server
```bash
python manage.py runserver
```
- Customer site → http://127.0.0.1:8000/
- Staff dashboard → http://127.0.0.1:8000/staff/
- Django admin → http://127.0.0.1:8000/admin/ *(run `python manage.py createsuperuser` first)*

> **Development payments:** with `DJANGO_DEBUG=1` and no Razorpay keys, checkout shows a **"Demo Pay"** button that simulates a successful payment, so you can test the whole flow without a Razorpay account. With debug off and no keys, online checkout is disabled.

### Run the tests
```bash
python manage.py test
```
The tests cover the full order flow: payment, webhook-before-browser, bad signatures, cancellation and refund, daily limits, order ownership, and pre-order dating.

---

## ⚙️ Environment Variables

| Variable | Purpose | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django secret key | **Required** when debug is off |
| `DJANGO_DEBUG` | `1` = development, `0` = production | Defaults to `0` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts | Default `localhost,127.0.0.1,[::1]`; Render's host is added automatically |
| `DJANGO_CSRF_ORIGINS` | Trusted HTTPS origins, e.g. `https://yourapp.onrender.com` | Optional |
| `RAZORPAY_KEY_ID` | Razorpay API key ID | Empty = payments disabled / demo mode |
| `RAZORPAY_KEY_SECRET` | Razorpay API key secret | |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook signing secret | |

> 🔒 Never commit your real `.env` file. Only `.env.example` should be in version control.

---

## 💳 Razorpay Setup

1. Create an account at [razorpay.com](https://razorpay.com) and generate keys under **Account & Settings → API Keys**.
2. Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
3. In the Razorpay dashboard, add a webhook pointing to `https://<your-domain>/payment/webhook/` and subscribe to **`payment.captured`** and **`order.paid`**.
4. Copy the webhook secret into `RAZORPAY_WEBHOOK_SECRET`.

---

## 🔑 Staff Login

Staff sign in at `/staff/login/`. Only users with `is_staff` can enter.

A fresh database comes with a default account created by a migration:

⚠️ **Change this password (or delete the account) before going live.** Create real staff users from the Django admin (`/admin/` → Users → tick *Staff status*).

---

## 🗺️ Order Flow

```
Customer picks dishes (one meal at a time)
              ↓
   Checkout: name + phone number
              ↓
   Pays the full amount via Razorpay
              ↓
   Token page: 4-digit token + live status
              ↓
   Kitchen: New → Preparing → Ready
              ↓
   Customer shows token at the counter → Picked up
```

*Cancelled before cooking starts? The amount is refunded automatically.*

---

## 📌 Key URLs

| URL | Purpose |
|---|---|
| `/` | Welcome page |
| `/home/` | Home — meal categories |
| `/menu/<breakfast\|lunch\|dinner>/` | Dishes for a meal |
| `/checkout/` | Checkout form |
| `/pay/<id>/` | Payment page |
| `/token/<id>/` · `/order/<id>/` | Token / order status page |
| `/order/<id>/status/` | Status JSON (polled by the token page) |
| `/order/<id>/cancel/` | Cancel an order (POST) |
| `/chat/` | Chatbot endpoint (POST) |
| `/stock/` | Live stock JSON |
| `/about/` · `/location/` | Info pages |
| `/payment/webhook/` | Razorpay webhook |
| `/staff/login/` | Staff sign-in |
| `/staff/` | Kitchen dashboard |
| `/staff/menu/` | Stock and menu management |
| `/admin/` | Django admin |

---

## ☁️ Deployment (Render)

1. Create a **Web Service** from this repository with the root directory set to `backend`.
2. **Build command:** `./build.sh` (installs requirements, collects static files, runs migrations).
3. **Start command:** `gunicorn config.wsgi`
4. Add the environment variables from the table above (`DJANGO_DEBUG=0`).
5. Add the Razorpay webhook for your Render URL.

> SQLite and the `media/` folder live on the server's disk, which is wiped on every deploy on Render's free tier. For real use, attach a persistent disk or move to PostgreSQL and external media storage.

---

## 🧰 Useful Commands

```bash
# Attach photos from a folder to dishes with matching names (preview first)
python manage.py attach_dish_images --dry-run
python manage.py attach_dish_images --source "path/to/images"

# Create an admin user
python manage.py createsuperuser
```

---

## 🛣️ Status & Roadmap

- ✅ Menu, cart, Razorpay payments, token system, live status, refunds
- ✅ Staff dashboard and stock control
- ✅ Chatbot assistant
- 🔜 Production database and persistent media storage

---

## 🤝 Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

Built for personal and educational use. Feel free to adapt it for your own canteen or mess.
