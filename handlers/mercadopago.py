# handlers/mercadopago.py
import logging
import hashlib
import hmac
from datetime import datetime
import httpx
import os
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


def _validar_firma(request_body: bytes, firma_header: str) -> bool:
    """Valida que el webhook realmente proviene de Mercado Pago."""
    if not MP_WEBHOOK_SECRET or MP_WEBHOOK_SECRET == "TU_SECRET_AQUI":
        logger.warning("Webhook secret no configurado — saltando validación de firma")
        return True

    expected = hmac.new(
        MP_WEBHOOK_SECRET.encode(),
        request_body,
        hashlib.sha256
    ).hexdigest()
    
    if not firma_header:
        logger.warning("No se recibió firma en el header")
        return False
    
    return hmac.compare_digest(expected, firma_header or "")


async def procesar_webhook_mp(request: Request, sucursal_key: str):
    """
    Endpoint principal del webhook de Mercado Pago.
    """
    try:
        body = await request.body()
        firma = request.headers.get("x-signature", "")
        
        # DEBUG: Loguear headers y body para ver qué llega
        logger.info(f"🔍 Headers recibidos: {dict(request.headers)}")
        logger.info(f"🔍 Body recibido: {body}")
        logger.info(f"🔍 Firma del header: {firma}")
        logger.info(f"🔍 Secret configurado: {MP_WEBHOOK_SECRET[:10]}..." if MP_WEBHOOK_SECRET else "No configurado")

        if not _validar_firma(body, firma):
            logger.warning("Firma inválida en webhook MP")
            raise HTTPException(status_code=401, detail="Firma inválida")
        
        # ... resto del código

        datos = await request.json()
        logger.info(f"Webhook MP recibido para {sucursal_key}: {datos}")

        # MP puede enviar "type" o "action" dependiendo del evento
        evento_type = datos.get("type") or datos.get("action", "")
        
        # Solo procesar eventos de payment
        if "payment" not in evento_type.lower():
            logger.info(f"Evento '{evento_type}' no es de pago — ignorado")
            return {"status": "ignorado", "motivo": f"evento: {evento_type}"}

        payment_id = str(datos.get("data", {}).get("id", ""))
        if not payment_id or payment_id == "123456":
            # ID de prueba de MP, no es un pago real
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
            # No retornamos error 502, solo ignoramos
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
        
        logger.info(f"Pago notificado: ${monto} - {sucursal_datos['nombre']}")

        return {"status": "ok", "payment_id": payment_id, "monto": monto}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error procesando webhook MP: {e}")
        # Retornamos 200 OK para que MP no reintente constantemente
        return {"status": "error", "detalle": str(e)}
