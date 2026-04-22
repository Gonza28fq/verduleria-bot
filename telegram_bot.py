import logging
import telegram
from config import TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)


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