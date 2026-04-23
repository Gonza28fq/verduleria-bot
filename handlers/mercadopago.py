# handlers/mercadopago.py
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
        if datos.get("mp_access_token") == access_token:
            return key, datos
    return None, None


async def _obtener_detalle_pago(payment_id: str, access_token: str) -> dict | None:
    """Consulta la API de MP para obtener el detalle del pago."""
    url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"MP API devolvió {resp.status_code} para payment {payment_id}")
                return None
            return resp.json()
        except Exception as e:
            logger.error(f"Error consultando pago {payment_id}: {e}")
            return None


def _validar_firma(payment_id: str, request_id: str, firma_header: str) -> bool:
    """Valida firma según el formato oficial de Mercado Pago."""
    if not MP_WEBHOOK_SECRET or MP_WEBHOOK_SECRET == "TU_SECRET_AQUI":
        logger.warning("Webhook secret no configurado — saltando validación")
        return True

    if not firma_header:
        logger.warning("No se recibió firma en el header")
        return False

    try:
        # Parsear ts y v1 del header x-signature
        partes = dict(p.split("=", 1) for p in firma_header.split(","))
        ts = partes.get("ts", "")
        v1 = partes.get("v1", "")

        # Armar el manifest exactamente como lo hace MP
        manifest = f"id:{payment_id};request-id:{request_id};ts:{ts};"

        expected = hmac.new(
            MP_WEBHOOK_SECRET.encode(),
            manifest.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, v1)
    except Exception as e:
        logger.error(f"Error validando firma: {e}")
        return False


async def procesar_webhook_mp(request: Request, sucursal_key: str):
    """
    Endpoint principal del webhook de Mercado Pago.
    """
    try:
        body = await request.body()
        firma = request.headers.get("x-signature", "")
        request_id = request.headers.get("x-request-id", "")

        datos = await request.json()
        logger.info(f"Webhook MP recibido para {sucursal_key}: {datos}")

        payment_id = str(datos.get("data", {}).get("id", ""))

        # Validar firma con el formato correcto de MP
        if not _validar_firma(payment_id, request_id, firma):
            logger.warning("Firma inválida en webhook MP")
            raise HTTPException(status_code=401, detail="Firma inválida")

        # MP puede enviar "type" o "action" dependiendo del evento
        evento_type = datos.get("type") or datos.get("action", "")

        # Solo procesar eventos de payment
        if "payment" not in evento_type.lower():
            logger.info(f"Evento '{evento_type}' no es de pago — ignorado")
            return {"status": "ignorado", "motivo": f"evento: {evento_type}"}

        # Ignorar el payment ID de prueba que manda MP al configurar el webhook
        if not payment_id or payment_id == "123456":
            logger.info("Payment ID de prueba detectado — ignorado")
            return {"status": "ok", "motivo": "test payment ignorado"}

        sucursal_datos = SUCURSALES.get(sucursal_key)
        if not sucursal_datos:
            logger.error(f"Sucursal {sucursal_key} no encontrada")
            raise HTTPException(status_code=404, detail="Sucursal no encontrada")

        # Verificar que la sucursal tenga token de MP
        access_token = sucursal_datos.get("mp_access_token")
        if not access_token:
            logger.warning(f"Sucursal {sucursal_key} no tiene access token de MP")
            return {"status": "ignorado", "motivo": "sin access token"}

        # Consultar detalle del pago a la API de MP
        pago = await _obtener_detalle_pago(payment_id, access_token)

        if not pago:
            logger.warning(f"No se pudo obtener el pago {payment_id} de MP")
            return {"status": "ok", "motivo": "pago no encontrado en MP"}

        # Solo notificar pagos aprobados
        if pago.get("status") != "approved":
            logger.info(f"Pago {payment_id} con estado '{pago.get('status')}' — no se notifica")
            return {"status": "ignorado", "motivo": f"estado: {pago.get('status')}"}

        monto = float(pago.get("transaction_amount", 0))

        if monto < MONTO_MINIMO:
            logger.info(f"Pago de ${monto} menor al mínimo — no se notifica")
            return {"status": "ignorado", "motivo": "monto menor al mínimo"}

        hora = datetime.now().strftime("%H:%M")
        mensaje = formatear_cobro(sucursal_datos["nombre"], monto, "Mercado Pago", hora)

        await enviar_alerta(sucursal_datos["chat_id"], mensaje)

        logger.info(f"✅ Pago notificado: ${monto} - {sucursal_datos['nombre']}")

        return {"status": "ok", "payment_id": payment_id, "monto": monto}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error procesando webhook MP: {e}")
        return {"status": "error", "detalle": str(e)}