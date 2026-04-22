# reportes.py
import logging
from telegram_bot import enviar_alerta
from database import obtener_cobros_semanales
from config import DUENO_CHAT_ID, SUCURSALES
from datetime import datetime

logger = logging.getLogger(__name__)


async def enviar_reporte_semanal(forzar: bool = False):
    """Envía el reporte semanal al dueño."""
    try:
        cobros = await obtener_cobros_semanales()
        
        # Si no hay datos y no es forzado, no enviamos
        if not cobros and not forzar:
            logger.info("No hay cobros para reportar esta semana")
            return {"status": "sin_datos"}
        
        fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        mensaje = f"📊 <b>REPORTE SEMANAL DE COBROS</b>\n"
        mensaje += f"─────────────────\n"
        mensaje += f"📅 <b>Período:</b> Últimos 7 días\n"
        mensaje += f"🕐 <b>Generado:</b> {fecha_hoy}\n"
        if forzar:
            mensaje += f"⚠️ <b>Modo:</b> TEST MANUAL\n"
        mensaje += f"─────────────────\n\n"
        
        total_general = 0
        
        # Si no hay cobros pero es forzado, mostramos mensaje de prueba
        if not cobros and forzar:
            mensaje += f"🧪 <b>Prueba de sistema</b>\n"
            mensaje += f"   No hay cobros registrados aún.\n"
            mensaje += f"   El formato del reporte es correcto.\n\n"
        else:
            for key, datos in cobros.items():
                mensaje += f"🏪 <b>{datos['nombre']}</b>\n"
                mensaje += f"   💵 Total: ${datos['total']:,.2f}\n"
                mensaje += f"   📋 Transacciones: {datos['cantidad']}\n\n"
                total_general += datos['total']
        
        mensaje += f"─────────────────\n"
        mensaje += f"💰 <b>TOTAL GENERAL:</b> ${total_general:,.2f}\n"
        mensaje += f"─────────────────\n"
        mensaje += f"✅ Sistema AVC Verduleria Bot"
        
        await enviar_alerta(DUENO_CHAT_ID, mensaje)
        logger.info("Reporte semanal enviado al dueño")
        
        return {"status": "ok", "total": total_general}
        
    except Exception as e:
        logger.error(f"Error enviando reporte semanal: {e}")
        return {"status": "error", "detalle": str(e)}
