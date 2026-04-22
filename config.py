# ============================================================
#  CONFIG - Lee variables desde .env
# ============================================================
import os
from dotenv import load_dotenv

# Cargar variables del archivo .env
load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DUENO_CHAT_ID = int(os.getenv("DUENO_CHAT_ID", 0))

# Mercado Pago
MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET")

# Configuración General
MONTO_MINIMO = float(os.getenv("MONTO_MINIMO", 0))
PORT = int(os.getenv("PORT", 8000))
NGROK_URL = os.getenv("NGROK_URL", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "admin123")

# Sucursales
SUCURSALES = {
    "sucursal_1": {
        "nombre": os.getenv("SUCURSAL_1_NOMBRE", "Feria"),
        "chat_id": int(os.getenv("SUCURSAL_1_CHAT_ID", 0)),
        "mp_access_token": os.getenv("SUCURSAL_1_MP_TOKEN") or None,
    },
    "sucursal_2": {
        "nombre": os.getenv("SUCURSAL_2_NOMBRE", "Local"),
        "chat_id": int(os.getenv("SUCURSAL_2_CHAT_ID", 0)),
        "mp_access_token": os.getenv("SUCURSAL_2_MP_TOKEN") or None,
    },
}
