"""
MENTOR — Bot de Telegram personalizado
Padre / Jefe / Coach / Asesor integrado en un solo personaje
Filosofía Brian Tracy | Rioplatense | 24/7
"""

import os, logging, json
from datetime import datetime
from pathlib import Path

from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

# ─── CONFIG ───────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_KEY       = os.environ["GROQ_API_KEY"]
CHAT_ID        = int(os.environ["CHAT_ID"])
TIMEZONE       = os.environ.get("TIMEZONE", "America/Argentina/Buenos_Aires")
MEMORY_FILE    = Path("mentor_memory.json")

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
groq_client = Groq(api_key=GROQ_KEY)

# ─── MEMORIA ──────────────────────────────────────────────────
def load_memory() -> dict:
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text())
    return {
        "history": [],
        "metas": [],
        "compromisos": [],
        "tareas_pendientes": [],
        "tareas_completadas": [],
        "lecturas": [],
        "finanzas": {
            "ingresos_meta": 0,
            "deudas": [],
            "ahorros_meta": 0,
            "registros": []
        },
        "prospectos": [],
        "logros": [],
    }

def save_memory(mem: dict):
    MEMORY_FILE.write_text(json.dumps(mem, ensure_ascii=False, indent=2))

memory = load_memory()

# ─── BOTONES RÁPIDOS ──────────────────────────────────────────
def botones_proactivo():
    """Botones que aparecen en mensajes que MENTOR inicia."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Arrancando", callback_data="resp_arrancando"),
            InlineKeyboardButton("😅 Todavía no", callback_data="resp_no_arranque"),
        ],
        [
            InlineKeyboardButton("🔥 Contarle más", callback_data="resp_contar"),
            InlineKeyboardButton("💬 Hablar ahora", callback_data="resp_hablar"),
        ]
    ])

def botones_conversacion():
    """Botones para respuesta rápida en conversación."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➡️ Siguiente paso", callback_data="resp_siguiente"),
            InlineKeyboardButton("🆘 Necesito ayuda", callback_data="resp_ayuda"),
        ]
    ])

# ─── SYSTEM PROMPT ────────────────────────────────────────────
def build_system(modo: str = "conversacion") -> str:
    ctx = ""
    if memory["metas"]:
        ctx += f"\nMETAS ACTIVAS: {', '.join(memory['metas'])}"
    if memory["compromisos"]:
        pendientes = [c for c in memory["compromisos"] if not c.get("cumplido")]
        if pendientes:
            ctx += f"\nCOMPROMISOS PENDIENTES: {', '.join(c['texto'] for c in pendientes[-5:])}"
    if memory["tareas_pendientes"]:
        ctx += f"\nTAREAS PENDIENTES: {', '.join(memory['tareas_pendientes'][-5:])}"
    if memory["lecturas"]:
        en_curso = [l for l in memory["lecturas"] if not l.get("terminado")]
        if en_curso:
            ctx += f"\nLECTURAS EN CURSO: {', '.join(l['libro'] for l in en_curso)}"
    if memory["finanzas"]["deudas"]:
        deudas_activas = [d for d in memory["finanzas"]["deudas"] if not d.get("pagado")]
        if deudas_activas:
            resumen = ", ".join(f"{d['nombre']} ${d['monto']}" for d in deudas_activas)
            ctx += f"\nDEUDAS ACTIVAS: {resumen}"

    if modo == "proactivo":
        largo = "Máximo 2 oraciones. Mensaje corto, directo, con punch. Terminá siempre con UNA pregunta o acción concreta."
    else:
        largo = "Podés extenderte si la situación lo requiere. Máximo 4 oraciones en conversación normal, más si el usuario pide análisis o plan."

    return f"""Sos MENTOR — padre sabio, jefe exigente, coach de vida y asesor financiero en una sola voz.

PERFIL DEL USUARIO:
- Emprendedor/freelancer buscando estabilidad económica
- Estancado en: finanzas/deudas, ingresos inestables, hábitos, foco, salud
- Filosofía Brian Tracy: Eat That Frog, Si lo crees lo creas, Seminario Fénix
- Responde bien a: calidez primero, exigencia cuando está cómodo o excusándose
- Arranca el día entre 7-9 AM

TU CARÁCTER:
- Padre sabio: contenés sin juzgar, pero no sobreprotegés
- Jefe mentor: pedís resultados, explicás el porqué
- Coach Tracy: sapo primero, metas escritas, disciplina como músculo
- Asesor financiero: números reales, bola de nieve para deudas
- Voz: masculina, cálida, directa, rioplatense

EMOJIS: Usá emojis con naturalidad en cada mensaje. Uno o dos por mensaje, donde tenga sentido. Ejemplos: 🎯 para metas, 💰 para finanzas, 🔥 para motivación, ✅ para logros, 💪 para desafíos, 📖 para lecturas, ⚡ para urgencia.

LARGO DE RESPUESTA: {largo}

ESTILO:
- Español rioplatense: "vos", "laburás", "dale", "che", "metele"
- SIEMPRE terminás con una pregunta concreta o micro-acción
- Nunca hablás como chatbot corporativo

FRASES TUYAS:
- "Comé el sapo. Lo más difícil, primero. 🐸"
- "Las metas no escritas son sueños. ¿La escribiste? 🎯"
- "Hecho es mejor que perfecto. Siempre. ✅"
- "¿Qué haría la mejor versión de vos ahora mismo? 💪"
- "Cada peso que ordenás es libertad recuperada. 💰"
{ctx}"""


# ─── LLAMADA A GROQ ───────────────────────────────────────────
async def mentor_reply(user_msg: str = "", trigger_prompt: str = None, modo: str = "conversacion") -> str:
    hist = memory["history"][-40:]

    if trigger_prompt:
        messages = hist + [{"role": "user", "content": f"[SISTEMA]: {trigger_prompt}"}]
    else:
        messages = hist + [{"role": "user", "content": user_msg}]

    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=500,
            messages=[{"role": "system", "content": build_system(modo)}] + messages,
        )
        reply = resp.choices[0].message.content

        if user_msg:
            memory["history"].append({"role": "user", "content": user_msg})
        memory["history"].append({"role": "assistant", "content": reply})
        memory["history"] = memory["history"][-60:]
        save_memory(memory)
        return reply

    except Exception as e:
        log.error(f"Error Groq: {e}")
        return "⚙️ Tuve un problema técnico. Seguí adelante, ya vuelvo."


# ─── PROACTIVOS ───────────────────────────────────────────────
PROACTIVOS = {
    "buenos_dias": (
        "Son las 8 AM. Mandá el mensaje de arranque del día. "
        "Recordale el sapo de Tracy. Preguntá cuál es la UNA tarea más importante de hoy. "
        "Energético, muy corto, con emoji."
    ),
    "check_manana": (
        "Son las 10:30. Checkeo rápido: ¿arrancó con el sapo? "
        "Muy corto, tono de colega que pasa a ver. Con emoji."
    ),
    "check_mediodia": (
        "Son las 13h. Checkeo de mediodía. Preguntá qué logró en la mañana. "
        "Muy corto. Con emoji."
    ),
    "empuje_tarde": (
        "Son las 17h. Empuje de tarde, el día no terminó. "
        "Preguntá qué le falta cerrar. Muy corto, con punch. Con emoji."
    ),
    "cierre": (
        "Son las 21h. Cierre del día. Pedí 1 logro del día y 1 compromiso para mañana. "
        "Tono cálido de padre. Corto. Con emoji."
    ),
    "push_random": (
        "Mandá un mensaje inesperado. Una frase Tracy, pregunta poderosa, o recordatorio de meta. "
        "Muy corto, con punch. Con emoji."
    ),
    "check_lecturas": (
        "Checkeo dominical de lecturas. Preguntá cómo va el libro. "
        "Tracy: líderes son lectores. Corto. Con emoji."
    ),
}


# ─── CALLBACK DE BOTONES ──────────────────────────────────────
CALLBACKS = {
    "resp_arrancando": "El usuario dijo que ya arrancó con sus tareas. Celebralo brevemente y preguntá cómo va. Con emoji. Muy corto.",
    "resp_no_arranque": "El usuario todavía no arrancó. No lo juzgues, pero empujalo con una micro-acción para arrancar ahora mismo. Con emoji. Muy corto.",
    "resp_contar": "El usuario quiere contarte más sobre su situación. Invitalo a hablar, escuchá con interés genuino. Con emoji. Muy corto.",
    "resp_hablar": "El usuario quiere hablar. Abrí la conversación con una pregunta abierta y cálida. Con emoji.",
    "resp_siguiente": "El usuario quiere saber el siguiente paso concreto. Dáselo directo, sin vueltas. Con emoji.",
    "resp_ayuda": "El usuario necesita ayuda. Preguntá qué está pasando con calidez y sin juzgar. Con emoji.",
}

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != CHAT_ID:
        return
    prompt = CALLBACKS.get(query.data, "Respondé naturalmente al contexto.")
    reply = await mentor_reply(trigger_prompt=prompt, modo="proactivo")
    await query.message.reply_text(reply, reply_markup=botones_conversacion())


# ─── HANDLERS ─────────────────────────────────────────────────
async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    await ctx.bot.send_chat_action(chat_id=CHAT_ID, action="typing")
    reply = await mentor_reply(user_msg=update.message.text, modo="conversacion")
    await update.message.reply_text(reply, reply_markup=botones_conversacion())


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    reply = await mentor_reply(trigger_prompt=(
        "Primera activación. Presentate como MENTOR — padre, jefe, coach y asesor. "
        "Sé memorable, con emojis. Preguntá cuál es la situación más urgente a resolver."
    ), modo="conversacion")
    await update.message.reply_text(reply, reply_markup=botones_conversacion())


async def cmd_meta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if args:
        memory["metas"].append(args)
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró esta meta: '{args}'. Reconocela con Tracy, hacé una pregunta sobre el primer paso. Con emoji.")
    else:
        if memory["metas"]:
            lista = "\n".join(f"• {m}" for m in memory["metas"])
            reply = await mentor_reply(trigger_prompt=f"El usuario ve sus metas:\n{lista}\nReflexión breve y desafío. Con emoji.")
        else:
            reply = "🎯 Todavía no registraste metas.\n\nUsá: /meta [tu meta]\nEjemplo: /meta Generar $500 este mes"
    await update.message.reply_text(reply, reply_markup=botones_conversacion())


async def cmd_tarea(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if args:
        memory["tareas_pendientes"].append(args)
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró tarea: '{args}'. ¿Es el sapo? Con emoji.")
    else:
        if memory["tareas_pendientes"]:
            lista = "\n".join(f"• {t}" for t in memory["tareas_pendientes"])
            await update.message.reply_text(f"📋 Tareas pendientes:\n{lista}")
            return
        else:
            await update.message.reply_text("No tenés tareas. Usá: /tarea [descripción]")
            return
    await update.message.reply_text(reply, reply_markup=botones_conversacion())


async def cmd_hecho(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if not args:
        if memory["tareas_pendientes"]:
            lista = "\n".join(f"{i+1}. {t}" for i, t in enumerate(memory["tareas_pendientes"]))
            await update.message.reply_text(f"¿Cuál completaste?\n{lista}\n\nUsá: /hecho [nombre]")
        else:
            await update.message.reply_text("No tenés tareas pendientes. 🎉")
        return
    encontrada = None
    for t in memory["tareas_pendientes"]:
        if args.lower() in t.lower():
            encontrada = t
            break
    if encontrada:
        memory["tareas_pendientes"].remove(encontrada)
        memory["tareas_completadas"].append({"tarea": encontrada, "fecha": datetime.now().isoformat()})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Completó: '{encontrada}'. Celebralo y empujá al siguiente. Con emoji.")
        await update.message.reply_text(reply, reply_markup=botones_conversacion())
    else:
        await update.message.reply_text(f"No encontré '{args}'. Revisá con /tarea.")


async def cmd_lectura(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if not args:
        if memory["lecturas"]:
            en_curso = [l for l in memory["lecturas"] if not l.get("terminado")]
            terminados = [l for l in memory["lecturas"] if l.get("terminado")]
            txt = ""
            if en_curso:
                txt += "📖 En curso:\n" + "\n".join(f"• {l['libro']} — pág {l.get('paginas_actuales',0)}/{l.get('paginas_meta','?')}" for l in en_curso)
            if terminados:
                txt += "\n\n✅ Terminados:\n" + "\n".join(f"• {l['libro']}" for l in terminados)
            await update.message.reply_text(txt or "No hay lecturas.")
        else:
            await update.message.reply_text("📖 Sin lecturas registradas.\n\nUsá: /lectura [título]")
        return
    partes = args.split()
    if partes[0].lower() == "progreso" and len(partes) >= 3:
        paginas = partes[-1]
        titulo = " ".join(partes[1:-1])
        for l in memory["lecturas"]:
            if titulo.lower() in l["libro"].lower():
                l["paginas_actuales"] = int(paginas)
                if l.get("paginas_meta") and int(paginas) >= l["paginas_meta"]:
                    l["terminado"] = True
                save_memory(memory)
                reply = await mentor_reply(trigger_prompt=f"Actualizó '{l['libro']}' a pág {paginas}. Tracy: líderes son lectores. Con emoji.")
                await update.message.reply_text(reply)
                return
        await update.message.reply_text(f"No encontré '{titulo}'.")
    else:
        nuevo = {"libro": args, "paginas_meta": 0, "paginas_actuales": 0, "terminado": False}
        memory["lecturas"].append(nuevo)
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Empezó '{args}'. Preguntá cuántas páginas por día. Tracy: 10 páginas diarias. Con emoji.")
        await update.message.reply_text(reply)


async def cmd_finanzas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if not args:
        fin = memory["finanzas"]
        deudas_activas = [d for d in fin["deudas"] if not d.get("pagado")]
        total_deudas = sum(d["monto"] for d in deudas_activas)
        registros = fin["registros"][-5:]
        txt = "💰 RESUMEN FINANCIERO\n\n"
        if deudas_activas:
            txt += f"Deudas activas: ${total_deudas:,.0f}\n"
            for d in deudas_activas:
                txt += f"  • {d['nombre']}: ${d['monto']:,.0f}\n"
        else:
            txt += "Sin deudas registradas ✅\n"
        if registros:
            txt += "\nÚltimos movimientos:\n"
            for r in registros:
                txt += f"  • {r['tipo']} ${r['monto']:,.0f} — {r['descripcion']}\n"
        txt += "\n/finanzas deuda [nombre] [monto]\n/finanzas ingreso [monto] [desc]\n/finanzas gasto [monto] [desc]\n/finanzas pague [deuda]"
        await update.message.reply_text(txt)
        return
    partes = args.split()
    cmd = partes[0].lower()
    if cmd == "deuda" and len(partes) >= 3:
        nombre = " ".join(partes[1:-1])
        monto = float(partes[-1])
        memory["finanzas"]["deudas"].append({"nombre": nombre, "monto": monto, "pagado": False})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró deuda: {nombre} ${monto}. Bola de nieve Tracy. No juzgues. Con emoji.")
        await update.message.reply_text(reply)
    elif cmd in ["ingreso", "gasto"] and len(partes) >= 3:
        monto = float(partes[1])
        desc = " ".join(partes[2:])
        memory["finanzas"]["registros"].append({"fecha": datetime.now().strftime("%d/%m/%Y"), "tipo": cmd, "monto": monto, "descripcion": desc})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró {cmd} ${monto} ({desc}). Reforzá el hábito. Con emoji.")
        await update.message.reply_text(reply)
    elif cmd == "pague" and len(partes) >= 2:
        nombre = " ".join(partes[1:])
        for d in memory["finanzas"]["deudas"]:
            if nombre.lower() in d["nombre"].lower():
                d["pagado"] = True
                save_memory(memory)
                reply = await mentor_reply(trigger_prompt=f"Pagó deuda '{d['nombre']}' ${d['monto']}. ¡Celebralo! Libertad recuperada. Con emoji.")
                await update.message.reply_text(reply)
                return
        await update.message.reply_text(f"No encontré '{nombre}'.")
    else:
        await update.message.reply_text("💰 Comandos:\n/finanzas deuda [nombre] [monto]\n/finanzas ingreso [monto] [desc]\n/finanzas gasto [monto] [desc]\n/finanzas pague [deuda]")


async def cmd_prospecto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if not args:
        if memory["prospectos"]:
            txt = "👔 PROSPECTOS:\n"
            for p in memory["prospectos"]:
                txt += f"\n• {p['nombre']} ({p.get('empresa','')}) — {p['estado']}\n  Último contacto: {p.get('ultimo_contacto','nunca')}"
            await update.message.reply_text(txt)
        else:
            await update.message.reply_text("Sin prospectos.\n\nUsá: /prospecto [nombre] [empresa]")
        return
    partes = args.split()
    if partes[0].lower() == "followup" and len(partes) >= 2:
        nombre = " ".join(partes[1:])
        prospecto = next((p for p in memory["prospectos"] if nombre.lower() in p["nombre"].lower()), None)
        if prospecto:
            prospecto["ultimo_contacto"] = datetime.now().strftime("%d/%m/%Y")
            prospecto["estado"] = "followup enviado"
            save_memory(memory)
            reply = await mentor_reply(trigger_prompt=f"Generá mail follow-up para '{prospecto['nombre']}' de '{prospecto.get('empresa','')}'. Tracy: 80% ventas después del 5to contacto.")
            await update.message.reply_text(f"📧 FOLLOW-UP listo para copiar:\n\n{reply}")
        else:
            await update.message.reply_text(f"No encontré '{nombre}'.")
    else:
        nombre = partes[0]
        empresa = " ".join(partes[1:]) if len(partes) > 1 else ""
        memory["prospectos"].append({"nombre": nombre, "empresa": empresa, "estado": "contacto inicial", "ultimo_contacto": datetime.now().strftime("%d/%m/%Y")})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Nuevo prospecto: {nombre} de {empresa}. Generá mensaje inicial para LinkedIn/Upwork.")
        await update.message.reply_text(f"✅ Guardado.\n\n📩 MENSAJE INICIAL:\n\n{reply}")


async def cmd_logro(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if args:
        memory["logros"].append({"logro": args, "fecha": datetime.now().strftime("%d/%m/%Y")})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Logró: '{args}'. Celebralo genuinamente. Con emoji.")
        await update.message.reply_text(reply, reply_markup=botones_conversacion())
    else:
        await update.message.reply_text("Usá: /logro [lo que lograste]")


async def cmd_estado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    tz = pytz.timezone(TIMEZONE)
    ahora = datetime.now(tz).strftime("%H:%M — %d/%m/%Y")
    deudas = [d for d in memory["finanzas"]["deudas"] if not d.get("pagado")]
    await update.message.reply_text(
        f"⚡ MENTOR ACTIVO\n"
        f"🕐 {ahora}\n\n"
        f"🎯 Metas: {len(memory['metas'])}\n"
        f"📋 Tareas pendientes: {len(memory['tareas_pendientes'])}\n"
        f"✅ Tareas completadas: {len(memory['tareas_completadas'])}\n"
        f"📖 Libros en curso: {len([l for l in memory['lecturas'] if not l.get('terminado')])}\n"
        f"💰 Deudas activas: {len(deudas)}\n"
        f"👔 Prospectos: {len(memory['prospectos'])}\n"
        f"🏆 Logros: {len(memory['logros'])}\n\n"
        f"/meta /tarea /hecho /lectura\n"
        f"/finanzas /prospecto /logro /reset"
    )


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    memory["history"] = []
    save_memory(memory)
    await update.message.reply_text("🔄 Historial limpiado. Metas y datos se mantienen.\n¿Qué está pasando?")


# ─── SCHEDULER ────────────────────────────────────────────────
async def send_proactive(app: Application, trigger: str):
    log.info(f"Proactivo: {trigger}")
    try:
        reply = await mentor_reply(trigger_prompt=PROACTIVOS[trigger], modo="proactivo")
        await app.bot.send_message(chat_id=CHAT_ID, text=reply, reply_markup=botones_proactivo())
    except Exception as e:
        log.error(f"Error proactivo {trigger}: {e}")


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    tz = pytz.timezone(TIMEZONE)
    s = AsyncIOScheduler(timezone=tz)
    s.add_job(send_proactive, "cron", hour=8,  minute=0,  args=[app, "buenos_dias"],    id="d1")
    s.add_job(send_proactive, "cron", hour=10, minute=30, args=[app, "check_manana"],   id="d2")
    s.add_job(send_proactive, "cron", hour=13, minute=0,  args=[app, "check_mediodia"], id="d3")
    s.add_job(send_proactive, "cron", hour=15, minute=30, args=[app, "push_random"],    id="d4")
    s.add_job(send_proactive, "cron", hour=17, minute=0,  args=[app, "empuje_tarde"],   id="d5")
    s.add_job(send_proactive, "cron", hour=21, minute=0,  args=[app, "cierre"],         id="d6")
    s.add_job(send_proactive, "cron", day_of_week="sun", hour=9, minute=0, args=[app, "check_lecturas"], id="d7")
    return s


# ─── MAIN ─────────────────────────────────────────────────────
async def post_init(app: Application):
    scheduler = setup_scheduler(app)
    scheduler.start()
    log.info("Scheduler activo — 7 mensajes automáticos diarios.")


def main():
    log.info("Iniciando MENTOR Bot...")
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("meta",      cmd_meta))
    app.add_handler(CommandHandler("tarea",     cmd_tarea))
    app.add_handler(CommandHandler("hecho",     cmd_hecho))
    app.add_handler(CommandHandler("lectura",   cmd_lectura))
    app.add_handler(CommandHandler("finanzas",  cmd_finanzas))
    app.add_handler(CommandHandler("prospecto", cmd_prospecto))
    app.add_handler(CommandHandler("logro",     cmd_logro))
    app.add_handler(CommandHandler("estado",    cmd_estado))
    app.add_handler(CommandHandler("reset",     cmd_reset))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("MENTOR online.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
