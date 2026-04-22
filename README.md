# 🥬 AVC Verduleria Bot

A real-time payment notification system for grocery stores. Automatically detects payments from **Mercado Pago** and **Brubank**, and sends instant alerts to employees via **Telegram**.

---

## 📋 Table of Contents

- [Features](#-features)
- [How It Works](#-how-it-works)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [API Endpoints](#-api-endpoints)
- [Telegram Bot Commands](#-telegram-bot-commands)
- [Deployment](#-deployment)
- [Security](#-security)
- [License](#-license)

---

## ✨ Features

- **🔔 Real-Time Notifications**: Instant Telegram alerts when payments are received
- **💳 Multiple Payment Sources**: Supports Mercado Pago (webhook) and Brubank (MacroDroid)
- **👥 Role-Based Access**: Different permissions for employees and owners
- **📊 Daily Reports**: Automatic weekly reports to the owner
- **💾 Payment History**: SQLite database for tracking all transactions
- **🔒 Secure**: Environment variables for sensitive data, webhook signature validation
- **☁️ Cloud-Ready**: Deployed on Railway with persistent storage

---

## 🔄 How It Works

### Mercado Pago Flow
```
Customer Pays → Mercado Pago Webhook → FastAPI → Database → Telegram Alert
```

### Brubank Flow
```
Customer Pays → Brubank Notification → MacroDroid → HTTP POST → FastAPI → Database → Telegram Alert
```

### Employee Verification
```
Employee asks bot "1500?" → Bot checks database → Returns payment confirmation
```

---

## 🛠 Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Python 3.11+, FastAPI |
| **Database** | SQLite (aiosqlite) |
| **Notifications** | Telegram Bot API (python-telegram-bot v22.7) |
| **Webhooks** | Mercado Pago Official API |
| **Mobile Automation** | MacroDroid (Android) |
| **Deployment** | Railway |
| **Scheduler** | APScheduler |

---

## 📁 Project Structure

```
verduleria-bot/
├── main.py                 # FastAPI application entry point
├── config.py               # Configuration loader (reads .env)
├── database.py             # SQLite database operations
├── telegram_bot.py         # Telegram bot with commands & roles
├── reportes.py             # Weekly report generation
├── requirements.txt        # Python dependencies
├── Procfile                # Railway deployment config
├── .env                    # Environment variables (NOT committed)
├── .gitignore              # Git ignore rules
└── handlers/
    ├── __init__.py
    ├── mercadopago.py      # Mercado Pago webhook handler
    └── brubank.py          # Brubank notification handler
```

---

## 🚀 Installation

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/Gonza28fq/verduleria-bot.git
   cd verduleria-bot
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create `.env` file** (see [Configuration](#-configuration))

5. **Run the server**
   ```bash
   python main.py
   ```

6. **Test the API**
   ```bash
   curl http://localhost:8000
   ```

---

## ⚙️ Configuration

Create a `.env` file in the root directory with the following variables:

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
DUENO_CHAT_ID=owner_telegram_chat_id

# Mercado Pago
MP_WEBHOOK_SECRET=your_webhook_secret_here

# General
MONTO_MINIMO=0
PORT=8000
ADMIN_TOKEN=your_admin_token_here

# Branch 1 - Feria (Brubank only)
SUCURSAL_1_NOMBRE=Feria
SUCURSAL_1_CHAT_ID=employee_chat_id
SUCURSAL_1_MP_TOKEN=

# Branch 2 - Local (Mercado Pago only)
SUCURSAL_2_NOMBRE=Local
SUCURSAL_2_CHAT_ID=employee_chat_id
SUCURSAL_2_MP_TOKEN=your_mp_access_token_here
```

### ⚠️ Security Notes

- **Never commit `.env`** to GitHub (it's in `.gitignore`)
- **Regenerate tokens** regularly, especially after sharing code
- **Use strong `ADMIN_TOKEN`** for protected endpoints

---

## 🌐 API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `GET` | `/` | Health check | None |
| `POST` | `/webhook/mp/{sucursal_key}` | Mercado Pago webhook | MP Signature |
| `POST` | `/webhook/brubank/{sucursal_key}` | Brubank webhook (MacroDroid) | None |
| `POST` | `/test/{sucursal_key}` | Test alert endpoint | None |
| `POST` | `/admin/reporte` | Force weekly report | `X-Admin-Token` |

---

## 🤖 Telegram Bot Commands

### 👤 Employee Commands

| Command | Description |
|---------|-------------|
| `1500?` | Check if a payment of $1,500 was received |
| `/start` | Show available commands |
| `/ayuda` | Show help message |

### 👨‍💼 Owner Commands (Additional)

| Command | Description |
|---------|-------------|
| `/ultimo` | View last payment registered |
| `/total` | View total collected today |
| `/reporte` | Weekly report by branch |

### 🔐 Role-Based Access

| Information | Employee | Owner |
|-------------|----------|-------|
| Check specific payment (`1500?`) | ✅ Yes | ✅ Yes |
| View last payment | ❌ No | ✅ Yes |
| View daily total | ❌ No | ✅ Yes |
| View weekly report | ❌ No | ✅ Yes |

---

## ☁️ Deployment (Railway)

1. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Deploy to Railway"
   git push origin main
   ```

2. **Create Railway Project**
   - Go to [railway.app](https://railway.app)
   - New Project → Deploy from GitHub
   - Select your repository

3. **Configure Environment Variables**
   - Add all variables from `.env` in Railway's Variables tab

4. **Generate Domain**
   - Settings → Domains → Generate Domain
   - Copy the URL for webhook configuration

5. **Configure Webhooks**
   - **Mercado Pago**: `https://your-domain.railway.app/webhook/mp/sucursal_2`
   - **MacroDroid**: `https://your-domain.railway.app/webhook/brubank/sucursal_1`

---

## 📱 MacroDroid Configuration (Brubank)

For Brubank notifications (no official webhook):

1. **Install MacroDroid** from Google Play Store
2. **Create new macro** with:
   - **Trigger**: Notification Received → App: Brubank
   - **Action**: HTTP Request → POST
   - **URL**: `https://your-domain.railway.app/webhook/brubank/sucursal_1`
   - **Body**: `{"titulo": "{notification_title}", "texto": "{notification_text}"}`

---

## 🔒 Security

- ✅ Webhook signature validation for Mercado Pago
- ✅ Environment variables for sensitive data
- ✅ Role-based access control for Telegram commands
- ✅ `.env` file excluded from version control
- ✅ Admin token protection for sensitive endpoints

### Recommendations

1. **Regenerate Telegram Bot Token** via [@BotFather](https://t.me/BotFather) with `/revoke`
2. **Regenerate Mercado Pago Access Token** from [Developer Panel](https://www.mercadopago.com.ar/developers/panel)
3. **Use HTTPS** for all webhook URLs (Railway provides this by default)
4. **Rotate `ADMIN_TOKEN`** periodically

---

## 📝 License

This project is proprietary software developed for AVC Verdulería.

---

## 📞 Support

For issues or questions, contact the development team.

---

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/)
- [python-telegram-bot](https://python-telegram-bot.org/)
- [MacroDroid](https://macrodroid.net/)
- [Railway](https://railway.app/)
- [Mercado Pago Developers](https://www.mercadopago.com.ar/developers)

---

<div align="center">

**Built with ❤️ for AVC Verdulería**

</div>
