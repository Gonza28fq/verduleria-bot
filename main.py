# main.py
import logging
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from handlers.mercadopago import procesar_webhook_mp
from handlers.brubank import procesar_notificacion_brubank
from database import init_db, registrar_cobro
from reportes import enviar_reporte_semanal
from config import SUCURSALES, ADMIN_TOKEN, TELEGRAM_BOT_TOKEN
from telegram_bot import enviar_alerta, formatear_cobro

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Global ───────────────────────────────────────────────
scheduler = AsyncIOScheduler()
bot_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja el startup y shutdown de la app correctamente."""
    # Startup
    logger.info("🚀 Iniciando sistema...")
    await init_db()
    
    # Iniciar scheduler
    scheduler.add_job(
        enviar_reporte_semanal,
        CronTrigger(day_of_week='mon', hour=9, minute=0),
        id='reporte_semanal'
    )
    scheduler.start()
    logger.info("📅 Scheduler de reportes iniciado")
    
    # Iniciar bot de Telegram EN BACKGROUND
    import asyncio
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters
    
    bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Importar handlers del bot
    from telegram_bot import (
        start_command, ayuda_command, ultimo_command, 
        total_command, reporte_command, manejar_mensaje
    )
    
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("ayuda", ayuda_command))
    bot_app.add_handler(CommandHandler("ultimo", ultimo_command))
    bot_app.add_handler(CommandHandler("total", total_command))
    bot_app.add_handler(CommandHandler("reporte", reporte_command))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    
    await bot_app.initialize()
    await bot_app.start()
    
    # Iniciar polling en background (no bloquea)
    bot_task = asyncio.create_task(
        bot_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    )
    logger.info("🤖 Bot de Telegram iniciado en background")
    
    logger.info("✅ Sistema completo iniciado")
    
    yield  # La app corre aquí
    
    # Shutdown
    logger.info("🛑 Apagando sistema...")
    if bot_app:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
    scheduler.shutdown()
    logger.info("✅ Sistema apagado correctamente")


# ── App ──────────────────────────────────────────────────
app = FastAPI(title="Verduleria Bot — AVC", version="2.0.0", lifespan=lifespan)


# ── Health check ─────────────────────────────────────────
@app.get("/")
async def health():
    logger.info("Health check recibido")
    return {"status": "online", "servicio": "Bot de Cobros AVC"}


# ── Endpoint DEBUG ───────────────────────────────────────
@app.post("/webhook/mp/debug/{sucursal_key}")
async def webhook_mp_debug(sucursal_key: str, request: Request):
    """Endpoint sin validación para debug."""
    logger.info(f"🔍 DEBUG: Request recibido para {sucursal_key}")
    try:
        datos = await request.json()
        logger.info(f"🔍 DEBUG: Datos: {datos}")
        return {"status": "ok", "received": datos, "sucursal": sucursal_key}
    except Exception as e:
        logger.error(f"🔍 DEBUG Error: {e}")
        return {"status": "error", "detalle": str(e)}


# ── Endpoint Admin ───────────────────────────────────────
@app.post("/admin/reporte")
async def forzar_reporte(request: Request):
    admin_token = request.headers.get("X-Admin-Token", "")
    if admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido")
    
    resultado = await enviar_reporte_semanal(forzar=True)
    return resultado


# ── Webhooks Mercado Pago ────────────────────────────────
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


# ── Endpoint Brubank ─────────────────────────────────────
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
    datos = await request.json()
    sucursal = SUCURSALES.get(sucursal_key)
    if not sucursal:
        return JSONResponse(status_code=404, content={"error": "Sucursal no encontrada"})

    monto = float(datos.get("monto", 999))
    fuente = datos.get("fuente", "Prueba")
    hora = uvicorn.config.datetime.now().strftime("%H:%M")

    mensaje = formatear_cobro(sucursal["nombre"], monto, fuente, hora)
    await enviar_alerta(sucursal["chat_id"], mensaje)
    
    await registrar_cobro(sucursal_key, sucursal["nombre"], monto, fuente, None)

    return {"status": "ok", "mensaje_enviado": mensaje}


# ── Entry point ───────────────────────────────────────────
if __name__ == "__main__":
    from config import PORT
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
