# database.py
import aiosqlite
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

DB_PATH = "cobros.db"


async def init_db():
    """Inicializa la base de datos y crea las tablas si no existen."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cobros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sucursal_key TEXT NOT NULL,
                sucursal_nombre TEXT NOT NULL,
                monto REAL NOT NULL,
                fuente TEXT NOT NULL,
                payment_id TEXT,
                fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
    logger.info("Base de datos inicializada")


async def registrar_cobro(sucursal_key: str, sucursal_nombre: str, 
                          monto: float, fuente: str, payment_id: str = None):
    """Registra un cobro en la base de datos."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO cobros (sucursal_key, sucursal_nombre, monto, fuente, payment_id)
            VALUES (?, ?, ?, ?, ?)
        """, (sucursal_key, sucursal_nombre, monto, fuente, payment_id))
        await db.commit()
    logger.info(f"Cobro registrado: {sucursal_nombre} - ${monto} - {fuente}")


async def obtener_cobros_semanales() -> dict:
    """Obtiene el total cobrado por sucursal en los últimos 7 días."""
    fecha_limite = datetime.now() - timedelta(days=7)
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT sucursal_key, sucursal_nombre, SUM(monto) as total, COUNT(*) as cantidad
            FROM cobros
            WHERE fecha_hora >= ?
            GROUP BY sucursal_key
        """, (fecha_limite.isoformat(),))
        resultados = await cursor.fetchall()
    
    return {row["sucursal_key"]: {
        "nombre": row["sucursal_nombre"],
        "total": row["total"] or 0,
        "cantidad": row["cantidad"] or 0
    } for row in resultados}


# ── NUEVAS FUNCIONES PARA EL BOT DE TELEGRAM ──────────────────

async def obtener_ultimo_cobro() -> dict | None:
    """Obtiene el último cobro registrado."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT sucursal_nombre, monto, fuente, fecha_hora
            FROM cobros
            ORDER BY fecha_hora DESC
            LIMIT 1
        """)
        resultado = await cursor.fetchone()
    
    if resultado:
        return {
            "sucursal_nombre": resultado["sucursal_nombre"],
            "monto": resultado["monto"],
            "fuente": resultado["fuente"],
            "fecha_hora": resultado["fecha_hora"]
        }
    return None


async def buscar_cobro_por_monto(monto: float, minutos: int = 30) -> dict | None:
    """Busca un cobro por monto en los últimos X minutos."""
    fecha_limite = datetime.now() - timedelta(minutes=minutos)
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT sucursal_nombre, monto, fuente, fecha_hora
            FROM cobros
            WHERE monto = ? AND fecha_hora >= ?
            ORDER BY fecha_hora DESC
            LIMIT 1
        """, (monto, fecha_limite.isoformat()))
        resultado = await cursor.fetchone()
    
    if resultado:
        return {
            "sucursal_nombre": resultado["sucursal_nombre"],
            "monto": resultado["monto"],
            "fuente": resultado["fuente"],
            "fecha_hora": resultado["fecha_hora"]
        }
    return None


async def obtener_total_dia() -> dict:
    """Obtiene el total cobrado en el día actual."""
    hoy = datetime.now().date()
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT SUM(monto) as monto, COUNT(*) as cantidad
            FROM cobros
            WHERE DATE(fecha_hora) = ?
        """, (hoy.isoformat(),))
        resultado = await cursor.fetchone()
    
    return {
        "monto": resultado["monto"] or 0,
        "cantidad": resultado["cantidad"] or 0,
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M")
    }
