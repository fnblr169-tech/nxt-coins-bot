import os
import sqlite3
import random
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
ZONA = ZoneInfo("America/Mexico_City")
DB = "nxtcoins.db"

logging.basicConfig(level=logging.INFO)


def conectar():
    return sqlite3.connect(DB)


def iniciar_db():
    with conectar() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY,
            efectivo INTEGER DEFAULT 0,
            banco INTEGER DEFAULT 0,
            categoria TEXT DEFAULT '',
            ultimo_trabajo TEXT DEFAULT '',
            ultimo_diario TEXT DEFAULT '',
            ultimo_sueldo TEXT DEFAULT '',
            categoria_desde TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS salarios (
            categoria TEXT PRIMARY KEY,
            cantidad INTEGER NOT NULL
        );
        """)


def asegurar(uid):
    with conectar() as db:
        db.execute(
            "INSERT OR IGNORE INTO usuarios (id) VALUES (?)",
            (uid,)
        )


def usuario(uid):
    asegurar(uid)
    with conectar() as db:
        return db.execute(
            "SELECT * FROM usuarios WHERE id=?", (uid,)
        ).fetchone()


def cambiar(uid, campo, valor):
    permitidos = {
        "efectivo", "banco", "categoria",
        "ultimo_trabajo", "ultimo_diario",
        "ultimo_sueldo", "categoria_desde"
    }
    if campo not in permitidos:
        return
    asegurar(uid)
    with conectar() as db:
        db.execute(
            f"UPDATE usuarios SET {campo}=? WHERE id=?",
            (valor, uid)
        )


def es_admin(uid):
    return uid in ADMIN_IDS


def ahora():
    return datetime.now(ZONA)


def dinero(n):
    return f"{n:,} NXT Coins"


async def inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Bienvenido a NXT Coins!\n\n"
        "Comandos disponibles:\n"
        "/id - Ver tu ID\n"
        "/saldo - Consultar tu dinero\n"
        "/trabajar - Trabajar cada hora\n"
        "/diario - Recompensa diaria\n"
        "/depositar cantidad - Depositar\n"
        "/retirar cantidad - Retirar\n"
        "/transferir ID cantidad - Transferir\n"
        "/cobrarsueldo - Cobrar sueldo pendiente\n"
        "/top - Ver los usuarios más ricos"
    )


async def mi_id(update, context):
    await update.message.reply_text(
        f"Tu ID de Telegram es: {update.effective_user.id}"
    )


async def saldo(update, context):
    u = usuario(update.effective_user.id)
    await update.message.reply_text(
        f"Tu saldo de NXT Coins:\n\n"
        f"Efectivo: {dinero(u[1])}\n"
        f"Banco: {dinero(u[2])}\n"
        f"Total: {dinero(u[1] + u[2])}\n"
        f"Categoría: {u[3] or 'Sin categoría'}"
    )


async def trabajar(update, context):
    uid = update.effective_user.id
    u = usuario(uid)
    ahora_dt = ahora()

    if u[4]:
        ultima = datetime.fromisoformat(u[4])
        restante = timedelta(hours=1) - (ahora_dt - ultima)
        if restante.total_seconds() > 0:
            minutos = int(restante.total_seconds() // 60) + 1
            await update.message.reply_text(
                f"Ya trabajaste. Vuelve en {minutos} minutos."
            )
            return

    premio = random.randint(100, 500)
    cambiar(uid, "efectivo", u[1] + premio)
    cambiar(uid, "ultimo_trabajo", ahora_dt.isoformat())

    await update.message.reply_text(
        f"¡Terminaste de trabajar!\n"
        f"Ganaste {dinero(premio)}."
    )


async def diario(update, context):
    uid = update.effective_user.id
    u = usuario(uid)
    fecha = ahora().date()

    if u[5] == fecha.isoformat():
        await update.message.reply_text(
            "Ya reclamaste tu recompensa diaria. "
            "Vuelve mañana."
        )
        return

    premio = random.randint(100, 500)
    cambiar(uid, "efectivo", u[1] + premio)
    cambiar(uid, "ultimo_diario", fecha.isoformat())

    await update.message.reply_text(
        f"¡Recompensa diaria recibida!\n"
        f"Ganaste {dinero(premio)}."
    )


async def depositar(update, context):
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(
            "Uso correcto: /depositar cantidad"
        )
        return

    cantidad = int(context.args[0])
    uid = update.effective_user.id
    u = usuario(uid)

    if cantidad <= 0 or cantidad > u[1]:
        await update.message.reply_text(
            "Cantidad inválida o efectivo insuficiente."
        )
        return

    with conectar() as db:
        db.execute(
            "UPDATE usuarios SET efectivo=efectivo-?, "
            "banco=banco+? WHERE id=?",
            (cantidad, cantidad, uid)
        )

    await update.message.reply_text(
        f"Depositaste {dinero(cantidad)}."
    )


async def retirar(update, context):
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(
            "Uso correcto: /retirar cantidad"
        )
        return

    cantidad = int(context.args[0])
    uid = update.effective_user.id
    u = usuario(uid)

    if cantidad <= 0 or cantidad > u[2]:
        await update.message.reply_text(
            "Cantidad inválida o saldo bancario insuficiente."
        )
        return

    with conectar() as db:
        db.execute(
            "UPDATE usuarios SET banco=banco-?, "
            "efectivo=efectivo+? WHERE id=?",
            (cantidad, cantidad, uid)
        )

    await update.message.reply_text(
        f"Retiraste {dinero(cantidad)}."
    )


async def transferir(update, context):
    if len(context.args) != 2:
        await update.message.reply_text(
            "Uso: /transferir ID cantidad"
        )
        return

    try:
        destino = int(context.args[0])
        cantidad = int(context.args[1])
    except ValueError:
        await update.message.reply_text(
            "El ID y la cantidad deben ser números."
        )
        return

    origen = update.effective_user.id

    if destino == origen or cantidad <= 0:
        await update.message.reply_text(
            "Transferencia inválida."
        )
        return

    asegurar(origen)
    asegurar(destino)

    with conectar() as db:
        db.execute("BEGIN IMMEDIATE")
        emisor = db.execute(
            "SELECT efectivo FROM usuarios WHERE id=?",
            (origen,)
        ).fetchone()

        if not emisor or emisor[0] < cantidad:
            db.rollback()
            await update.message.reply_text(
                "No tienes suficiente efectivo."
            )
            return

        db.execute(
            "UPDATE usuarios SET efectivo=efectivo-? WHERE id=?",
            (cantidad, origen)
        )
        db.execute(
            "UPDATE usuarios SET efectivo=efectivo+? WHERE id=?",
            (cantidad, destino)
        )

    await update.message.reply_text(
        f"Transferencia realizada.\n"
        f"Enviaste {dinero(cantidad)} al ID {destino}."
    )


def viernes_actual(fecha):
    return fecha - timedelta(days=(fecha.weekday() - 4) % 7)


async def cobrarsueldo(update, context):
    uid = update.effective_user.id
    u = usuario(uid)
    fecha = ahora().date()

    if not u[3]:
        await update.message.reply_text(
            "No tienes categoría asignada. "
            "Contacta al administrador."
        )
        return

    with conectar() as db:
        fila = db.execute(
            "SELECT cantidad FROM salarios WHERE categoria=?",
            (u[3],)
        ).fetchone()

    if not fila:
        await update.message.reply_text(
            "Tu categoría todavía no tiene un salario configurado."
        )
        return

    desde = datetime.fromisoformat(
        u[7] or ahora().date().isoformat()
    ).date()

    viernes = viernes_actual(fecha)

    if fecha < viernes or viernes < desde:
        await update.message.reply_text(
            "Tu próximo sueldo estará disponible el viernes."
        )
        return

    ultimo = u[6]
    inicio = desde

    if ultimo:
        inicio = datetime.fromisoformat(ultimo).date() + timedelta(days=1)

    primer_viernes = viernes_actual(inicio)
    if primer_viernes < inicio:
        primer_viernes += timedelta(days=7)

    if primer_viernes > viernes:
        await update.message.reply_text(
            "No tienes sueldos pendientes."
        )
        return

    semanas = ((viernes - primer_viernes).days // 7) + 1
    cantidad = fila[0] * semanas

    with conectar() as db:
        db.execute("BEGIN IMMEDIATE")
        actual = db.execute(
            "SELECT ultimo_sueldo FROM usuarios WHERE id=?",
            (uid,)
        ).fetchone()[0]

        if actual != ultimo:
            db.rollback()
            await update.message.reply_text(
                "Vuelve a intentar cobrar tu sueldo."
            )
            return

        db.execute(
            "UPDATE usuarios SET efectivo=efectivo+?, "
            "ultimo_sueldo=? WHERE id=?",
            (cantidad, viernes.isoformat(), uid)
        )

    await update.message.reply_text(
        f"¡Sueldo cobrado!\n"
        f"Semanas pagadas: {semanas}\n"
        f"Total recibido: {dinero(cantidad)}."
    )


async def top(update, context):
    with conectar() as db:
        filas = db.execute(
            "SELECT id, efectivo+banco AS total FROM usuarios "
            "ORDER BY total DESC LIMIT 10"
        ).fetchall()

    texto = "🏆 TOP 10 NXT COINS\n\n"
    for i, (uid, total) in enumerate(filas, 1):
        texto += f"{i}. ID {uid}: {dinero(total)}\n"

    await update.message.reply_text(texto)


async def asignar(update, context):
    if not es_admin(update.effective_user.id):
        return
    if len(context.args) != 2:
        await update.message.reply_text(
            "Uso: /asignar ID categoría"
        )
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID inválido.")
        return

    categoria = context.args[1].strip()
    asegurar(uid)
    cambiar(uid, "categoria", categoria)
    cambiar(uid, "categoria_desde", ahora().date().isoformat())

    await update.message.reply_text(
        f"ID {uid} ahora pertenece a la categoría {categoria}."
    )


async def salario_admin(update, context):
    if not es_admin(update.effective_user.id):
        return
    if len(context.args) != 2:
        await update.message.reply_text(
            "Uso: /salario categoría cantidad"
        )
        return

    categoria = context.args[0].strip()
    try:
        cantidad = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Cantidad inválida.")
        return

    if cantidad < 0:
        await update.message.reply_text(
            "El salario no puede ser negativo."
        )
        return

    with conectar() as db:
        db.execute(
            "INSERT INTO salarios(categoria, cantidad) VALUES(?, ?) "
            "ON CONFLICT(categoria) DO UPDATE SET cantidad=excluded.cantidad",
            (categoria, cantidad)
        )

    await update.message.reply_text(
        f"Salario de {categoria}: {dinero(cantidad)} por semana."
    )


async def quitarcategoria(update, context):
    if not es_admin(update.effective_user.id):
        return
    if len(context.args) != 1:
        await update.message.reply_text(
            "Uso: /quitarcategoria ID"
        )
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID inválido.")
        return

    asegurar(uid)
    cambiar(uid, "categoria", "")
    cambiar(uid, "categoria_desde", "")
    cambiar(uid, "ultimo_sueldo", "")

    await update.message.reply_text(
        f"Se quitó la categoría del ID {uid}."
    )


async def modificar_dinero(update, context, operacion):
    if not es_admin(update.effective_user.id):
        return
    if len(context.args) != 2:
        await update.message.reply_text(
            f"Uso: /{operacion} ID cantidad"
        )
        return

    try:
        uid = int(context.args[0])
        cantidad = int(context.args[1])
    except ValueError:
        await update.message.reply_text("ID o cantidad inválidos.")
        return

    if cantidad <= 0:
        await update.message.reply_text(
            "La cantidad debe ser mayor que cero."
        )
        return

    asegurar(uid)
    u = usuario(uid)
    nuevo = u[1] + cantidad if operacion == "dar" else u[1] - cantidad

    if nuevo < 0:
        await update.message.reply_text(
            "El usuario no tiene suficiente efectivo."
        )
        return

    cambiar(uid, "efectivo", nuevo)
    await update.message.reply_text(
        f"Operación realizada. Efectivo actual: {dinero(nuevo)}."
    )


async def dar(update, context):
    await modificar_dinero(update, context, "dar")


async def quitar(update, context):
    await modificar_dinero(update, context, "quitar")


def main():
    if not TOKEN:
        raise RuntimeError("Falta configurar BOT_TOKEN.")

    iniciar_db()
    app = Application.builder().token(TOKEN).build()

    comandos = {
        "start": inicio,
        "id": mi_id,
        "saldo": saldo,
        "trabajar": trabajar,
        "diario": diario,
        "depositar": depositar,
        "retirar": retirar,
        "transferir": transferir,
        "cobrarsueldo": cobrarsueldo,
        "top": top,
        "asignar": asignar,
        "salario": salario_admin,
        "quitarcategoria": quitarcategoria,
        "dar": dar,
        "quitar": quitar,
    }

    for nombre, funcion in comandos.items():
        app.add_handler(CommandHandler(nombre, funcion))

    app.run_polling()


if __name__ == "__main__":
    main()
