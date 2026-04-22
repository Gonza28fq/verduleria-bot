import logging
import re
from datetime import datetime
from fastapi import Request, HTTPException

from config import SUCURSALES, MONTO_MINIMO
from telegram_bot import enviar_alerta, formatear_cobro

logger = logging.getLogger(__name__)

# Patrones para extraer el monto del texto de la notificación de Brubank
# Ajustar si Brubank cambia el formato del mensaje
PATRONES_MONTO = [
    r"\$\s?([\d.,]+)",           # "$1.200,00" o "$ 1200"
    r"(\d[\d.,]+)\s?pesos",      # "1200 pesos"
    r"transferencia de\s?\$?\s?([\d.,]+)",  # "transferencia de $1200"
]


def _extraer_monto(texto_notificacion: str) -> float | None:
    """Intenta extraer el monto del texto de la notificación de Brubank."""
    for patron in PATRONES_MONTO:
        match = re.search(patron, texto_notificacion, re.IGNORECASE)
        if match:
            monto_str = match.group(1)
            # Normalizar separadores: "1.200,50" → "1200.50"
            monto_str = monto_str.replace(".", "").replace(",", ".")
            try:
                return float(monto_str)
            except ValueError:
                continue
    return None


async def procesar_notificacion_brubank(request: Request, sucursal_key: str):
    """
    Endpoint que recibe el POST de MacroDroid cuando Brubank
    muestra una notificación de cobro en el Android del dueño.

    MacroDroid debe configurarse para hacer POST a:
    /webhook/brubank/{sucursal_key}

    Con body JSON:
    {
        "titulo": "texto del título de la notificación",
        "texto": "texto del cuerpo de la notificación"
    }
    """
    sucursal_datos = SUCURSALES.get(sucursal_key)
    if not sucursal_datos:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    try:
        datos = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body JSON inválido")

    titulo = datos.get("titulo", "")
    texto = datos.get("texto", "")
    texto_completo = f"{titulo} {texto}"

    logger.info(f"Notificación Brubank recibida para {sucursal_key}: {texto_completo}")

    # Verificar que sea una notificación de cobro (no cualquier notif de Brubank)
    palabras_clave = ["transferencia", "recibiste", "ingreso", "acreditado", "cobro"]
    es_cobro = any(p in texto_completo.lower() for p in palabras_clave)

    if not es_cobro:
        logger.info("Notificación de Brubank no es un cobro — ignorada")
        return {"status": "ignorado", "motivo": "no parece un cobro"}

    monto = _extraer_monto(texto_completo)

    if monto is None:
        # Si no se puede extraer el monto, notificar igual pero sin monto
        logger.warning(f"No se pudo extraer monto de: {texto_completo}")
        hora = datetime.now().strftime("%H:%M")
        mensaje = (
            f"💰 <b>COBRO DETECTADO — BRUBANK</b>\n"
            f"─────────────────\n"
            f"📍 <b>Sucursal:</b> {sucursal_datos['nombre']}\n"
            f"🕐 <b>Hora:</b> {hora}\n"
            f"─────────────────\n"
            f"⚠️ No se pudo leer el monto. Verificar en la app.\n"
            f"📩 Notif: <i>{texto_completo[:100]}</i>"
        )
        await enviar_alerta(sucursal_datos["chat_id"], mensaje)
        return {"status": "ok", "monto": None}

    if monto < MONTO_MINIMO:
        logger.info(f"Monto ${monto} menor al mínimo — ignorado")
        return {"status": "ignorado", "motivo": "monto menor al mínimo"}

    hora = datetime.now().strftime("%H:%M")
    mensaje = formatear_cobro(sucursal_datos["nombre"], monto, "Brubank", hora)
    await enviar_alerta(sucursal_datos["chat_id"], mensaje)

    return {"status": "ok", "monto": monto}