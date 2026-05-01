# ⚡ All-in-One Platform

> A production-ready SaaS foundation built with Django 5, Tailwind CSS, Stripe, and ML-powered analytics. Ship your subscription business in days, not months.

![Django](https://img.shields.io/badge/Django-5.0-green?style=flat-square&logo=django)
![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)
![Tailwind](https://img.shields.io/badge/Tailwind-3.x-38bdf8?style=flat-square&logo=tailwindcss)
![Stripe](https://img.shields.io/badge/Stripe-Integrated-635bff?style=flat-square&logo=stripe)
![ML](https://img.shields.io/badge/ML-scikit--learn-f7931e?style=flat-square&logo=scikitlearn)

---

## 🎯 What Is This?

This is **not** another boilerplate. It's a fully wired, opinionated SaaS starter that includes the boring parts nobody wants to build:

- ✅ Subscription billing with Stripe (checkout, webhooks, cancellation)
- ✅ ML-powered user analytics (churn prediction, health scoring)
- ✅ REST API with Django REST Framework
- ✅ Auth with social login (GitHub + Google OAuth)
- ✅ User profiles with avatar uploads
- ✅ Dark mode, responsive UI, toast notifications
- ✅ Contact form with database storage
- ✅ SEO meta tags and Open Graph

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│                  Frontend                    │
│    Tailwind CSS + Flowbite + Inter Font      │
│    Dark Mode │ Responsive │ Animations       │
├─────────────────────────────────────────────┤
│                Django 5.0                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │   Auth   │ │ Billing  │ │  Analytics   │ │
│  │ allauth  │ │  Stripe  │ │  ML Engine   │ │
│  │ profiles │ │ webhooks │ │ scikit-learn │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ REST API │ │ Contact  │ │  Dashboard   │ │
│  │   DRF    │ │  forms   │ │  real data   │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
├─────────────────────────────────────────────┤
│  SQLite (dev) │ Postgres (prod) │ WhiteNoise│
└─────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

```bash
# 1. Clone
git clone <repo-url> && cd SaaS-Foundations-main

# 2. Virtual environment
python -m venv venv && venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# 3. Install
pip install -r requirements.txt

# 4. Configure
cp .env.sample .env
# Edit .env → set DJANGO_SECRET_KEY plus any OAuth/API keys you need (for example GOOGLE_CLIENT_ID/SECRET and STRIPE_SECRET_KEY)

# 5. Migrate & run
cd src
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open **http://127.0.0.1:8000/** — you should see a fully styled landing page.

---

## 📦 What's Included

### Pages & UI

| Page | URL | Description |
|------|-----|-------------|
| Landing | `/` | Hero, features, testimonials, FAQ, footer |
| Services | `/services/` | 6 service cards with gradient styling |
| Pricing | `/pricing/` | Dynamic plans from database |
| Contact | `/contact/` | Form → saved to DB |
| Signup/Login | `/accounts/signup/` | django-allauth + GitHub/Google OAuth |
| Dashboard | `/` (logged in) | ML widgets, stats, activity chart |
| Analytics | `/analytics/` | Full ML insights dashboard |
| Billing | `/accounts/billing/` | Subscription details, cancel flow |
| Profile | `/profiles/edit/` | Edit name, bio, avatar, company |

### 🧠 ML Analytics Engine

The `analytics/ml_engine.py` module runs a feature extraction → scoring → prediction pipeline:

```
User Activity Data (30-day window)
        │
        ├── Login frequency
        ├── Page views
        ├── Feature usage count
        ├── Days since last activity
        ├── Subscription age & status
        └── Support contact count
        │
        ▼
┌─────────────────────────────┐
│   Health Score (0-100)      │  Weighted scoring algorithm
│   Churn Prediction (0-100%) │  Heuristic + logistic regression
│   Usage Forecast            │  Linear trend analysis
│   Smart Recommendations     │  Rule-based + ML signals
└─────────────────────────────┘
        │
        ▼
   Dashboard Widgets + API Endpoints
```

**Recommendations are context-aware:**
- 🔴 High churn? → "We miss you!" with feature discovery
- ⭐ No plan? → Upgrade prompt with plan comparison
- 💡 Low usage? → Feature discovery nudge
- 🏆 Power user? → Positive reinforcement
- ⏰ Expiring soon? → Renewal reminder

### 🔌 REST API

```
GET /api/v1/me/                          → User + profile
GET /api/v1/subscription/                → Subscription status
GET /api/v1/analytics/health-score/      → ML health score
GET /api/v1/analytics/usage/             → Usage data + forecast
GET /api/v1/analytics/recommendations/   → Smart recommendations
GET /api/v1/analytics/activity/          → Recent activity log
```

All endpoints require session authentication.

### 💳 Stripe Integration

| Event | Handler |
|-------|---------|
| `checkout.session.completed` | Creates/activates subscription |
| `invoice.payment_succeeded` | Updates billing period |
| `invoice.payment_failed` | Marks subscription `past_due` |
| `customer.subscription.updated` | Syncs status changes |
| `customer.subscription.deleted` | Cancels subscription |

**Local webhook testing:**
```bash
stripe listen --forward-to localhost:8000/webhooks/stripe/
```

---

## 📁 Project Structure

```
src/
├── analytics/           # ML engine + activity tracking
│   ├── ml_engine.py     # Churn, health score, recommendations
│   ├── models.py        # UserActivity, MLPrediction
│   └── views.py         # Analytics dashboard
├── api/                 # REST API (DRF)
│   ├── serializers.py   # All model serializers
│   ├── views.py         # API endpoints
│   └── urls.py          # /api/v1/ routing
├── cfehome/             # Project config
│   ├── settings.py      # All settings
│   ├── urls.py          # Master URL routing
│   ├── views.py         # Home, services views
│   └── webhooks.py      # Stripe webhook handler
├── checkouts/           # Stripe checkout flow
├── contact/             # Contact form + model
├── customers/           # Stripe customer sync
├── dashboard/           # Dashboard views
├── helpers/             # Billing helper functions
├── landing/             # Landing page view
├── profiles/            # User profiles (model, forms, views)
├── subscriptions/       # Plans, prices, user subscriptions
├── templates/           # All Django templates
└── visits/              # Page visit analytics
```

---

## ⚙️ Environment Variables

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `DJANGO_SECRET_KEY` | ✅ | — | Django secret key |
| `DJANGO_DEBUG` | ✅ | — | `1` = dev, `0` = prod |
| `DATABASE_URL` | — | SQLite | Postgres connection string |
| `STRIPE_SECRET_KEY` | — | — | Stripe API key |
| `STRIPE_WEBHOOK_SECRET` | — | — | Webhook signing secret |
| `GITHUB_CLIENT_ID` | — | — | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | — | — | GitHub OAuth client secret |
| `GOOGLE_CLIENT_ID` | — | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | — | Google OAuth client secret |
| `EMAIL_HOST_USER` | — | — | SMTP username |
| `EMAIL_HOST_PASSWORD` | — | — | SMTP password |

---

## 🎨 UI & Design

- **Tailwind CSS** via CDN with custom config
- **Flowbite** component library for dropdowns, toggles, modals
- **Inter** font from Google Fonts
- **Dark mode** with localStorage persistence
- Custom CSS utilities: `.gradient-text`, `.btn-gradient`, `.card-hover`, `.glass`, `.fade-in-up`
- Animated background blobs on hero section
- Color-coded toast notifications (success/error/warning/info) with auto-dismiss

---

## 🧪 Testing

```bash
cd src
python manage.py check              # System checks
python manage.py test               # Run tests
python manage.py makemigrations --check  # Verify no pending migrations
```

---

## 🚢 Deployment (Railway)

1. Push to GitHub
2. Connect repo on [Railway](https://railway.app)
3. Add environment variables in Railway dashboard
4. Add Postgres addon (auto-sets `DATABASE_URL`)
5. Set build command: `pip install -r requirements.txt`
6. Set start command: `cd src && gunicorn cfehome.wsgi`

---

## 📜 License

MIT — use it however you want.
