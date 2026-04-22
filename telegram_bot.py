# telegram_bot.py
import logging
import telegram
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, DUENO_CHAT_ID, SUCURSALES
from database import obtener_cobros_semanales, obtener_ultimo_cobro, buscar_cobro_por_monto, obtener_total_dia

logger = logging.getLogger(__name__)

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# ── Funciones para Webhooks (las que ya existían) ──────────────────

async def enviar_alerta(chat_id: int, mensaje: str):
    """Envía un mensaje a un empleado vía Telegram."""
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=mensaje,
            parse_mode="HTML"
        )
        logger.info(f"Mensaje enviado a chat_id {chat_id}")
    except Exception as e:
        logger.error(f"Error enviando mensaje a {chat_id}: {e}")


def formatear_cobro(sucursal_nombre: str, monto: float, fuente: str, hora: str) -> str:
    """Arma el texto del mensaje de alerta."""
    return (
        f"💰 <b>COBRO CONFIRMADO</b>\n"
        f"─────────────────\n"
        f"📍 <b>Sucursal:</b> {sucursal_nombre}\n"
        f"💵 <b>Monto:</b> ${monto:,.2f}\n"
        f"📲 <b>Vía:</b> {fuente}\n"
        f"🕐 <b>Hora:</b> {hora}\n"
        f"─────────────────\n"
        f"✅ El pago fue acreditado."
    )


# ── Funciones para el Bot con Comandos (NUEVO) ──────────────────

def _es_dueno(chat_id: int) -> bool:
    """Verifica si el usuario es el dueño."""
    return chat_id == DUENO_CHAT_ID


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Muestra ayuda según el rol."""
    chat_id = update.effective_chat.id
    es_el_dueno = _es_dueno(chat_id)
    
    if es_el_dueno:
        ayuda = (
            "🤖 <b>Bienvenido - Bot de Cobros AVC (DUEÑO)</b>\n"
            "─────────────────\n"
            "📋 <b>Comandos disponibles:</b>\n\n"
            "💵 <code>1500?</code> — Consultar si ingresó un pago de $1.500\n"
            "📊 <code>/ultimo</code> — Ver el último pago registrado\n"
            "📈 <code>/total</code> — Ver total cobrado hoy\n"
            "📉 <code>/reporte</code> — Reporte semanal completo\n"
            "❓ <code>/ayuda</code> — Mostrar este mensaje\n\n"
            "─────────────────\n"
            "✅ Usted tiene acceso completo al sistema."
        )
    else:
        ayuda = (
            "🤖 <b>Bienvenido - Bot de Cobros AVC (EMPLEADO)</b>\n"
            "─────────────────\n"
            "📋 <b>Comandos disponibles:</b>\n\n"
            "💵 <code>1500?</code> — Consultar si ingresó un pago de $1.500\n"
            "❓ <code>/ayuda</code> — Mostrar este mensaje\n\n"
            "─────────────────\n"
            "⚠️ Para más opciones, contacte al dueño."
        )
    
    await update.message.reply_text(ayuda, parse_mode="HTML")


async def ayuda_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda."""
    await start_command(update, context)


async def ultimo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ultimo - SOLO DUEÑO."""
    chat_id = update.effective_chat.id
    
    if not _es_dueno(chat_id):
        await update.message.reply_text("⛔ Este comando es solo para el dueño.")
        return
    
    ultimo = await obtener_ultimo_cobro()
    
    if not ultimo:
        await update.message.reply_text("⚠️ No hay cobros registrados aún.")
        return
    
    mensaje = (
        f"📊 <b>ÚLTIMO PAGO REGISTRADO</b>\n"
        f"─────────────────\n"
        f"💵 <b>Monto:</b> ${ultimo['monto']:,.2f}\n"
        f"📲 <b>Vía:</b> {ultimo['fuente']}\n"
        f"🏪 <b>Sucursal:</b> {ultimo['sucursal_nombre']}\n"
        f"🕐 <b>Hora:</b> {ultimo['fecha_hora']}\n"
        f"─────────────────\n"
        f"✅ Pago confirmado en el sistema."
    )
    await update.message.reply_text(mensaje, parse_mode="HTML")


async def total_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /total - SOLO DUEÑO."""
    chat_id = update.effective_chat.id
    
    if not _es_dueno(chat_id):
        await update.message.reply_text("⛔ Este comando es solo para el dueño.")
        return
    
    total = await obtener_total_dia()
    
    mensaje = (
        f"📈 <b>TOTAL COBRADO HOY</b>\n"
        f"─────────────────\n"
        f"💰 <b>Total:</b> ${total['monto']:,.2f}\n"
        f"📋 <b>Transacciones:</b> {total['cantidad']}\n"
        f"─────────────────\n"
        f"🕐 Actualizado: {total['fecha']}"
    )
    await update.message.reply_text(mensaje, parse_mode="HTML")


async def reporte_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /reporte - SOLO DUEÑO."""
    chat_id = update.effective_chat.id
    
    if not _es_dueno(chat_id):
        await update.message.reply_text("⛔ Este comando es solo para el dueño.")
        return
    
    cobros = await obtener_cobros_semanales()
    
    if not cobros:
        await update.message.reply_text("⚠️ No hay cobros para reportar esta semana.")
        return
    
    from datetime import datetime
    fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    mensaje = f"📊 <b>REPORTE SEMANAL</b>\n"
    mensaje += f"─────────────────\n"
    mensaje += f"📅 <b>Período:</b> Últimos 7 días\n"
    mensaje += f"🕐 <b>Generado:</b> {fecha_hoy}\n"
    mensaje += f"─────────────────\n\n"
    
    total_general = 0
    
    for key, datos in cobros.items():
        mensaje += f"🏪 <b>{datos['nombre']}</b>\n"
        mensaje += f"   💵 Total: ${datos['total']:,.2f}\n"
        mensaje += f"   📋 Transacciones: {datos['cantidad']}\n\n"
        total_general += datos['total']
    
    mensaje += f"─────────────────\n"
    mensaje += f"💰 <b>TOTAL GENERAL:</b> ${total_general:,.2f}\n"
    mensaje += f"─────────────────\n"
    mensaje += f"✅ Sistema AVC Verduleria Bot"
    
    await update.message.reply_text(mensaje, parse_mode="HTML")


async def consultar_monto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Consulta si hay un pago de un monto específico - TODOS PUEDEN USAR."""
    texto = update.message.text.strip()
    
    # Extraer el monto del mensaje (ej: "1500?" o "ingreso 1500?")
    match = re.search(r'(\d+[.,]?\d*)', texto)
    
    if not match:
        await update.message.reply_text(
            "⚠️ No entendí el monto. Usá el formato: <code>1500?</code>",
            parse_mode="HTML"
        )
        return
    
    monto_str = match.group(1).replace(".", "").replace(",", ".")
    
    try:
        monto = float(monto_str)
    except ValueError:
        await update.message.reply_text("⚠️ El monto no es válido.")
        return
    
    # Buscar en la base de datos (últimos 30 minutos)
    cobro = await buscar_cobro_por_monto(monto, minutos=30)
    
    if cobro:
        mensaje = (
            f"✅ <b>PAGO CONFIRMADO</b>\n"
            f"─────────────────\n"
            f"💵 <b>Monto:</b> ${cobro['monto']:,.2f}\n"
            f"📲 <b>Vía:</b> {cobro['fuente']}\n"
            f"🕐 <b>Hora:</b> {cobro['fecha_hora']}\n"
            f"─────────────────\n"
            f"✅ El cliente puede retirar la mercadería."
        )
    else:
        mensaje = (
            f"⚠️ <b>PAGO NO ENCONTRADO</b>\n"
            f"─────────────────\n"
            f"💵 <b>Monto consultado:</b> ${monto:,.2f}\n"
            f"─────────────────\n"
            f"❌ No hay registros de este pago en los últimos 30 minutos.\n"
            f"💡 Verificá que el cliente haya completado la transferencia."
        )
    
    await update.message.reply_text(mensaje, parse_mode="HTML")


async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los mensajes de texto que no son comandos."""
    texto = update.message.text.strip().lower()
    
    # Si el mensaje contiene "?", es una consulta de monto (todos pueden usar)
    if '?' in texto:
        await consultar_monto(update, context)
    else:
        await update.message.reply_text(
            "❓ No entendí el comando. Escribí <code>/ayuda</code> para ver las opciones.",
            parse_mode="HTML"
        )


def iniciar_bot():
    """Inicia el bot de Telegram con los handlers."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Comandos
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("ayuda", ayuda_command))
    app.add_handler(CommandHandler("ultimo", ultimo_command))
    app.add_handler(CommandHandler("total", total_command))
    app.add_handler(CommandHandler("reporte", reporte_command))
    
    # Mensajes de texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    
    return app


async def shutdown_bot():
    """Cierra el bot correctamente."""
    logger.info("Apagando bot de Telegram...")
