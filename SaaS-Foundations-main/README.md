# SaaS Platform — Django + ML Analytics

A production-ready SaaS foundation built with **Django 5**, **Tailwind CSS**, **Flowbite**, **Stripe**, and **ML-powered analytics**. Everything you need to launch, scale, and intelligently manage a subscription-based software business.

---

## ✨ Features

### 🔐 Authentication & User Management
- Email + password authentication via **django-allauth**
- Social login (GitHub OAuth)
- User profiles with avatar uploads, bio, company info
- Profile editing with image upload support
- Role-based access control with Django groups/permissions

### 💳 Subscription & Billing
- Full **Stripe** integration for recurring payments
- Subscription plans with configurable pricing (monthly/yearly)
- Checkout flow with success/cancel handling
- **Real-time webhook processing** for:
  - `checkout.session.completed`
  - `invoice.payment_succeeded` / `invoice.payment_failed`
  - `customer.subscription.updated` / `deleted`
- Subscription management dashboard (view, cancel, change plan)
- Automatic permission sync based on active subscription

### 🧠 ML-Powered Analytics Engine
- **Account Health Score** (0-100) — composite engagement metric
- **Churn Prediction** — logistic regression-based probability with risk levels (low/medium/high)
- **Usage Forecasting** — predicts next month's activity based on patterns
- **Smart Recommendations** — personalized, context-aware suggestions:
  - Upgrade prompts for free-tier users
  - Feature discovery for low-engagement users
  - Retention offers for high-churn-risk users
  - Subscription renewal reminders
- Activity tracking with timestamped user action logging
- 7-day usage trend charts (CSS-only, no JS libraries needed)

### 📊 Dashboard
- Real data widgets replacing placeholder content:
  - Active plan badge with status indicator
  - Page view statistics (total + weekly)
  - ML health score with color-coded gauge
  - Days remaining until subscription renewal
- Interactive activity chart (last 7 days)
- Churn risk donut gauge with percentage
- Smart recommendations panel
- Recent activity feed with timestamps
- Quick action cards linking to key sections

### 🔌 REST API
- Built with **Django REST Framework**
- Session-based authentication
- Endpoints:
  | Method | Endpoint | Description |
  |--------|----------|-------------|
  | `GET` | `/api/v1/me/` | Current user + profile |
  | `GET` | `/api/v1/subscription/` | Subscription status |
  | `GET` | `/api/v1/analytics/health-score/` | ML health score |
  | `GET` | `/api/v1/analytics/usage/` | Usage data + forecast |
  | `GET` | `/api/v1/analytics/recommendations/` | ML recommendations |
  | `GET` | `/api/v1/analytics/activity/` | Recent activity log |

### 🎨 UI/UX
- **Tailwind CSS** + **Flowbite** component library
- Dark mode with persistent toggle (localStorage)
- Google Fonts (Inter) for modern typography
- Gradient branding throughout (blue → purple)
- Responsive sidebar navigation with real links
- Toast notifications with color-coded message types
- SEO meta tags (viewport, description, Open Graph)

### 📄 Complete Pages
- **Landing page** — hero, features, social proof, testimonials, FAQ, footer
- **Services page** — 6 feature cards with gradient backgrounds
- **Pricing page** — dynamic subscription plan cards from database
- **Contact page** — form with validation, saved to database
- **Dashboard** — ML-powered analytics overview
- **Analytics page** — full ML insights dashboard
- **Profile** — view & edit with avatar support
- **Billing** — subscription details, cancel flow

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.0 |
| Frontend | Tailwind CSS, Flowbite, htmx |
| Database | SQLite (dev) / Neon Postgres (prod) |
| Payments | Stripe SDK |
| Auth | django-allauth (email + GitHub) |
| API | Django REST Framework |
| ML | scikit-learn, pandas, numpy |
| Static files | WhiteNoise |
| Deployment | Railway / Gunicorn |

---

## 🚀 Quick Start

### 1. Clone & Setup
```bash
git clone <repo-url>
cd SaaS-Foundations-main
```

### 2. Create Virtual Environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
cp .env.sample .env
# Edit .env with your values:
# - DJANGO_SECRET_KEY (generate one)
# - STRIPE_SECRET_KEY (from Stripe dashboard)
# - STRIPE_WEBHOOK_SECRET (from Stripe webhook settings)
```

### 5. Run Migrations
```bash
cd src
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

### 6. Sync Subscription Permissions
```bash
python manage.py sync_permissions
```

### 7. Start Development Server
```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` to see the landing page.

---

## 📁 Project Structure

```
src/
├── analytics/          # ML engine, activity tracking, predictions
│   ├── ml_engine.py    # Churn prediction, health scoring, recommendations
│   ├── models.py       # UserActivity, MLPrediction
│   └── views.py        # Analytics dashboard view
├── api/                # REST API (DRF)
│   ├── serializers.py  # User, Subscription, Analytics serializers
│   ├── views.py        # API endpoints
│   └── urls.py         # /api/v1/ routes
├── cfehome/            # Project settings & root URL config
│   ├── settings.py     # All configuration
│   ├── urls.py         # Master URL routing
│   ├── views.py        # Home, about, services views
│   └── webhooks.py     # Stripe webhook handler
├── checkouts/          # Stripe checkout flow
├── contact/            # Contact form & message storage
├── customers/          # Stripe customer model
├── dashboard/          # Dashboard views
├── helpers/            # Billing helper functions
├── landing/            # Landing page views
├── profiles/           # User profiles with avatar support
├── subscriptions/      # Subscription & pricing models
├── templates/          # All Django templates
│   ├── analytics/      # ML analytics dashboard
│   ├── contact/        # Contact form page
│   ├── dashboard/      # Dashboard layout (base, nav, sidebar, main)
│   ├── landing/        # Hero, features, testimonials, FAQ, footer
│   ├── profiles/       # Profile detail & edit
│   ├── services/       # Services showcase
│   └── subscriptions/  # Billing & cancel pages
└── visits/             # Page visit tracking
```

---

## 🔧 Stripe Webhook Setup

### Local Development
```bash
# Install Stripe CLI, then:
stripe listen --forward-to localhost:8000/webhooks/stripe/
```

### Production
1. Go to Stripe Dashboard → Developers → Webhooks
2. Add endpoint: `https://yourdomain.com/webhooks/stripe/`
3. Select events: `checkout.session.completed`, `invoice.payment_succeeded`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`
4. Copy the webhook signing secret to your `.env` as `STRIPE_WEBHOOK_SECRET`

---

## 🧪 ML Analytics Details

The ML engine (`analytics/ml_engine.py`) uses a **feature extraction → scoring → prediction** pipeline:

### Features Extracted (per user, 30-day window)
- Login count
- Page views
- Feature usage count
- Days since last activity
- Subscription age
- Active subscription status
- Support contact count

### Models
| Model | Algorithm | Output |
|-------|-----------|--------|
| Health Score | Weighted scoring algorithm | 0-100 score |
| Churn Prediction | Heuristic + Logistic Regression | 0-100% probability |
| Usage Forecast | Linear trend analysis | Predicted actions next month |
| Recommendations | Rule-based + ML signals | Personalized action cards |

The engine self-improves as user data accumulates and can be retrained via:
```bash
python manage.py shell -c "from analytics.ml_engine import analyze_user; from django.contrib.auth import get_user_model; [analyze_user(u) for u in get_user_model().objects.all()]"
```

---

## 📝 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SECRET_KEY` | ✅ | Django secret key |
| `DJANGO_DEBUG` | ✅ | `1` for dev, `0` for production |
| `DATABASE_URL` | ❌ | Postgres URL (defaults to SQLite) |
| `STRIPE_SECRET_KEY` | ❌ | Stripe API secret key |
| `STRIPE_WEBHOOK_SECRET` | ❌ | Stripe webhook signing secret |
| `EMAIL_HOST_USER` | ❌ | SMTP email username |
| `EMAIL_HOST_PASSWORD` | ❌ | SMTP email password |

---

## 📜 License

MIT
