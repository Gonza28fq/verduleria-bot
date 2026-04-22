import logging
import hashlib
import hmac
from datetime import datetime
import httpx
from fastapi import Request, HTTPException

from config import SUCURSALES, MP_WEBHOOK_SECRET, MONTO_MINIMO
from telegram_bot import enviar_alerta, formatear_cobro

logger = logging.getLogger(__name__)


def _encontrar_sucursal_por_token(access_token: str):
    """Busca qué sucursal corresponde a un access token de MP."""
    for key, datos in SUCURSALES.items():
        if datos["mp_access_token"] == access_token:
            return key, datos
    return None, None


async def _obtener_detalle_pago(payment_id: str, access_token: str) -> dict | None:
    """Consulta la API de MP para obtener el detalle del pago."""
    url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error consultando pago {payment_id}: {e}")
            return None


def _validar_firma(request_body: bytes, firma_header: str) -> bool:
    """Valida que el webhook realmente proviene de Mercado Pago."""
    if not MP_WEBHOOK_SECRET or MP_WEBHOOK_SECRET == "TU_SECRET_AQUI":
        # Sin secret configurado se omite validación (solo para desarrollo)
        logger.warning("Webhook secret no configurado — saltando validación de firma")
        return True

    expected = hmac.new(
        MP_WEBHOOK_SECRET.encode(),
        request_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, firma_header or "")


async def procesar_webhook_mp(request: Request, sucursal_key: str):
    """
    Endpoint principal del webhook de Mercado Pago.
    MP llama a esta URL cuando entra un pago.
    URL sugerida: POST /webhook/mp/{sucursal_key}
    """
    body = await request.body()
    firma = request.headers.get("x-signature", "")

    if not _validar_firma(body, firma):
        logger.warning("Firma inválida en webhook MP")
        raise HTTPException(status_code=401, detail="Firma inválida")

    datos = await request.json()
    logger.info(f"Webhook MP recibido para {sucursal_key}: {datos}")

    # MP manda varios tipos de eventos, solo nos interesan los pagos
    if datos.get("type") != "payment":
        return {"status": "ignorado", "motivo": "evento no es payment"}

    payment_id = str(datos.get("data", {}).get("id", ""))
    if not payment_id:
        raise HTTPException(status_code=400, detail="ID de pago no encontrado")

    sucursal_datos = SUCURSALES.get(sucursal_key)
    if not sucursal_datos:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    # Consultar detalle del pago a la API de MP
    pago = await _obtener_detalle_pago(payment_id, sucursal_datos["mp_access_token"])
    if not pago:
        raise HTTPException(status_code=502, detail="No se pudo obtener el pago de MP")

    # Solo notificar pagos aprobados
    if pago.get("status") != "approved":
        logger.info(f"Pago {payment_id} con estado '{pago.get('status')}' — no se notifica")
        return {"status": "ignorado", "motivo": f"estado: {pago.get('status')}"}

    monto = float(pago.get("transaction_amount", 0))

    if monto < MONTO_MINIMO:
        logger.info(f"Pago de ${monto} menor al mínimo ${MONTO_MINIMO} — no se notifica")
        return {"status": "ignorado", "motivo": "monto menor al mínimo"}

    hora = datetime.now().strftime("%H:%M")
    mensaje = formatear_cobro(sucursal_datos["nombre"], monto, "Mercado Pago", hora)

    await enviar_alerta(sucursal_datos["chat_id"], mensaje)

    return {"status": "ok", "payment_id": payment_id, "monto": monto}