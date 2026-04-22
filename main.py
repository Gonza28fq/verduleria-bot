# main.py
import logging
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from handlers.mercadopago import procesar_webhook_mp
from handlers.brubank import procesar_notificacion_brubank
from database import init_db, registrar_cobro
from reportes import enviar_reporte_semanal
from config import SUCURSALES

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────
app = FastAPI(title="Verduleria Bot — AVC", version="1.0.0")

# ── Scheduler para reportes ───────────────────────────────
scheduler = AsyncIOScheduler()
# ... (imports anteriores)

# ── Endpoint Admin: Forzar Reporte ─────────────────────────
@app.post("/admin/reporte")
async def forzar_reporte(request: Request):
    """
    Endpoint protegido para testear el reporte semanal manualmente.
    Enviar header: X-Admin-Token: TU_TOKEN_SECRETO
    """
    # Validación simple por header (en producción usar auth real)
    admin_token = request.headers.get("X-Admin-Token", "")
    if admin_token != os.getenv("ADMIN_TOKEN", "admin123"):
        raise HTTPException(status_code=401, detail="Token inválido")
    
    resultado = await enviar_reporte_semanal(forzar=True)
    return resultado


# ... (resto del código)



async def iniciar_scheduler():
    """Programa el reporte semanal (todos los lunes a las 9:00)."""
    scheduler.add_job(
        enviar_reporte_semanal,
        CronTrigger(day_of_week='mon', hour=9, minute=0),
        id='reporte_semanal'
    )
    scheduler.start()
    logger.info("Scheduler de reportes iniciado")


# ── Health check ─────────────────────────────────────────
@app.get("/")
async def health():
    return {"status": "online", "servicio": "Bot de Cobros"}


# ── Webhooks Mercado Pago ─────────────────────────────────
@app.post("/webhook/mp/{sucursal_key}")
async def webhook_mp(sucursal_key: str, request: Request):
    resultado = await procesar_webhook_mp(request, sucursal_key)
    
    # Registrar en DB si el pago fue exitoso
    if resultado.get("status") == "ok" and resultado.get("monto"):
        sucursal = SUCURSALES.get(sucursal_key)
        await registrar_cobro(
            sucursal_key=sucursal_key,
            sucursal_nombre=sucursal["nombre"],
            monto=resultado["monto"],
            fuente="Mercado Pago",
            payment_id=resultado.get("payment_id")
        )
    
    return resultado


# ── Endpoint Brubank (MacroDroid) ─────────────────────────
@app.post("/webhook/brubank/{sucursal_key}")
async def webhook_brubank(sucursal_key: str, request: Request):
    resultado = await procesar_notificacion_brubank(request, sucursal_key)
    
    # Registrar en DB si el cobro fue exitoso
    if resultado.get("status") == "ok" and resultado.get("monto"):
        sucursal = SUCURSALES.get(sucursal_key)
        await registrar_cobro(
            sucursal_key=sucursal_key,
            sucursal_nombre=sucursal["nombre"],
            monto=resultado["monto"],
            fuente="Brubank",
            payment_id=None
        )
    
    return resultado


# ── Endpoint de prueba ───────────────────────────────────
@app.post("/test/{sucursal_key}")
async def test_alerta(sucursal_key: str, request: Request):
    from telegram_bot import enviar_alerta, formatear_cobro
    from datetime import datetime

    datos = await request.json()
    sucursal = SUCURSALES.get(sucursal_key)
    if not sucursal:
        return JSONResponse(status_code=404, content={"error": "Sucursal no encontrada"})

    monto = float(datos.get("monto", 999))
    fuente = datos.get("fuente", "Prueba")
    hora = datetime.now().strftime("%H:%M")

    mensaje = formatear_cobro(sucursal["nombre"], monto, fuente, hora)
    await enviar_alerta(sucursal["chat_id"], mensaje)
    
    # Registrar en DB también
    await registrar_cobro(sucursal_key, sucursal["nombre"], monto, fuente, None)

    return {"status": "ok", "mensaje_enviado": mensaje}


# ── Startup Event ─────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    await init_db()
    await iniciar_scheduler()


# ── Entry point ───────────────────────────────────────────
if __name__ == "__main__":
    from config import PORT
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
