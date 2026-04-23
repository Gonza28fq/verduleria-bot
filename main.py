# main.py
import logging
import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update

from handlers.mercadopago import procesar_webhook_mp
from handlers.brubank import procesar_notificacion_brubank
from database import init_db, registrar_cobro
from reportes import enviar_reporte_semanal
from config import SUCURSALES, ADMIN_TOKEN
from telegram_bot import iniciar_bot, shutdown_bot

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────
app = FastAPI(title="Verduleria Bot — AVC", version="2.0.0")

# ── Scheduler ────────────────────────────────────────────
scheduler = AsyncIOScheduler()
telegram_app = None


async def iniciar_scheduler():
    scheduler.add_job(
        enviar_reporte_semanal,
        CronTrigger(day_of_week='mon', hour=9, minute=0),
        id='reporte_semanal'
    )
    scheduler.start()
    logger.info("Scheduler de reportes iniciado")


async def iniciar_telegram_bot():
    global telegram_app
    telegram_app = iniciar_bot()
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot de Telegram iniciado")


async def cerrar_telegram_bot():
    global telegram_app
    if telegram_app:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
    logger.info("Bot de Telegram apagado")


# ── Health check ─────────────────────────────────────────
@app.get("/")
async def health():
    return {"status": "online", "servicio": "Bot de Cobros AVC"}


# ── Endpoint DEBUG (Para verificar que llega el request) ───
@app.post("/webhook/mp/debug/{sucursal_key}")
async def webhook_mp_debug(sucursal_key: str, request: Request):
    """Endpoint sin validación para debug."""
    try:
        logger.info(f"🔍 DEBUG: Request recibido para {sucursal_key}")
        datos = await request.json()
        logger.info(f"🔍 DEBUG: Datos: {datos}")
        return {"status": "ok", "received": datos, "sucursal": sucursal_key}
    except Exception as e:
        logger.error(f"🔍 DEBUG Error: {e}")
        return {"status": "error", "detalle": str(e)}


# ── Endpoint Admin ─────────────────────────────────────────
@app.post("/admin/reporte")
async def forzar_reporte(request: Request):
    admin_token = request.headers.get("X-Admin-Token", "")
    if admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido")
    
    resultado = await enviar_reporte_semanal(forzar=True)
    return resultado


# ── Webhooks Mercado Pago ─────────────────────────────────
@app.post("/webhook/mp/{sucursal_key}")
async def webhook_mp(sucursal_key: str, request: Request):
    logger.info(f"📩 Webhook MP recibido para {sucursal_key}")
    try:
        resultado = await procesar_webhook_mp(request, sucursal_key)
        
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
    except Exception as e:
        logger.error(f"Error en webhook_mp: {e}")
        return {"status": "error", "detalle": str(e)}


# ── Endpoint Brubank ──────────────────────────────────────
@app.post("/webhook/brubank/{sucursal_key}")
async def webhook_brubank(sucursal_key: str, request: Request):
    logger.info(f"📩 Webhook Brubank recibido para {sucursal_key}")
    try:
        resultado = await procesar_notificacion_brubank(request, sucursal_key)
        
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
    except Exception as e:
        logger.error(f"Error en webhook_brubank: {e}")
        return {"status": "error", "detalle": str(e)}


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
    
    await registrar_cobro(sucursal_key, sucursal["nombre"], monto, fuente, None)

    return {"status": "ok", "mensaje_enviado": mensaje}


# ── Startup Event ─────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    await init_db()
    await iniciar_scheduler()
    await iniciar_telegram_bot()
    logger.info("✅ Sistema completo iniciado")


# ── Shutdown Event ────────────────────────────────────────
@app.on_event("shutdown")
async def shutdown_event():
    await cerrar_telegram_bot()
    scheduler.shutdown()
    logger.info("🛑 Sistema apagado correctamente")


# ── Entry point ───────────────────────────────────────────
if __name__ == "__main__":
    from config import PORT
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
