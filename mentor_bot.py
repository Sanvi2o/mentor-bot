"""
MENTOR — Bot de Telegram personalizado
Padre / Jefe / Coach / Asesor integrado en un solo personaje
Filosofía Brian Tracy | Rioplatense | 24/7
Con integración Asana
"""

import os, logging, json, httpx
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
ASANA_TOKEN    = os.environ["ASANA_TOKEN"]
ASANA_WS       = "1211469237499109"
TIMEZONE       = os.environ.get("TIMEZONE", "America/Argentina/Buenos_Aires")
MEMORY_FILE    = Path("mentor_memory.json")

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
groq_client = Groq(api_key=GROQ_KEY)

ASANA_HEADERS = {
    "Authorization": f"Bearer {ASANA_TOKEN}",
    "Content-Type": "application/json"
}

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

# ─── ASANA ────────────────────────────────────────────────────
async def asana_get_tasks() -> list:
    """Obtiene tareas pendientes del workspace."""
    url = f"https://app.asana.com/api/1.0/tasks"
    params = {
        "workspace": ASANA_WS,
        "assignee": "me",
        "completed_since": "now",
        "opt_fields": "name,due_on,projects.name,notes,permalink_url"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=ASANA_HEADERS, params=params)
        data = resp.json()
        return data.get("data", [])

async def asana_create_task(name: str, notes: str = "", due_on: str = None) -> dict:
    """Crea una tarea en Asana."""
    url = "https://app.asana.com/api/1.0/tasks"
    payload = {
        "data": {
            "name": name,
            "workspace": ASANA_WS,
            "assignee": "me",
            "notes": notes,
        }
    }
    if due_on:
        payload["data"]["due_on"] = due_on
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=ASANA_HEADERS, json=payload)
        return resp.json().get("data", {})

async def asana_complete_task(task_gid: str) -> bool:
    """Marca una tarea como completada."""
    url = f"https://app.asana.com/api/1.0/tasks/{task_gid}"
    async with httpx.AsyncClient() as client:
        resp = await client.put(url, headers=ASANA_HEADERS, json={"data": {"completed": True}})
        return resp.status_code == 200

# ─── BOTONES ──────────────────────────────────────────────────
def botones_proactivo():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Arrancando", callback_data="resp_arrancando"),
            InlineKeyboardButton("😅 Todavía no", callback_data="resp_no_arranque"),
        ],
        [
            InlineKeyboardButton("🔥 Contarle más", callback_data="resp_contar"),
            InlineKeyboardButton("📋 Ver Asana", callback_data="resp_asana"),
        ]
    ])

def botones_conversacion():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➡️ Siguiente paso", callback_data="resp_siguiente"),
            InlineKeyboardButton("📋 Ver Asana", callback_data="resp_asana"),
        ],
        [
            InlineKeyboardButton("🆘 Estoy trabado", callback_data="resp_trabado"),
        ]
    ])

# ─── SYSTEM PROMPT ────────────────────────────────────────────
def build_system(modo: str = "conversacion") -> str:
    ctx = ""
    if memory["metas"]:
        ctx += f"\nMETAS ACTIVAS: {', '.join(memory['metas'])}"
    if memory["tareas_pendientes"]:
        ctx += f"\nTAREAS LOCALES PENDIENTES: {', '.join(memory['tareas_pendientes'][-5:])}"
    if memory["finanzas"]["deudas"]:
        deudas_activas = [d for d in memory["finanzas"]["deudas"] if not d.get("pagado")]
        if deudas_activas:
            deudas_str = ', '.join(d['nombre'] + ' $' + str(d['monto']) for d in deudas_activas)
    ctx += f'\nDEUDAS: {deudas_str}'

    largo = "Máximo 2 oraciones. Corto y con punch." if modo == "proactivo" else "Hasta 4 oraciones. Más si el usuario pide plan o análisis."

    return f"""Sos MENTOR — padre sabio, jefe exigente, coach de vida y asesor financiero en una sola voz masculina, cálida y directa.

PERFIL DEL USUARIO:
- Emprendedor/freelancer buscando estabilidad económica
- Enemigo central: resistencia al hacer, dispersión, procrastinación
- Filosofía Brian Tracy: Eat That Frog, metas escritas, disciplina como músculo
- Responde bien a: calidez + exigencia según el momento
- Arranca el día entre 7-9 AM, Buenos Aires

TU COMPORTAMIENTO:
- Cuando el usuario está mal → contenés primero, después guiás
- Cuando da excusas → las nombrás: "Eso es resistencia, no un obstáculo"
- Cuando logra algo → celebrás genuinamente
- Cuando está cómodo → subís la exigencia
- Siempre terminás con UNA pregunta o micro-acción concreta
- Usá emojis naturalmente: 🎯💰🔥✅💪📖⚡

LARGO: {largo}

ESTILO: Rioplatense. "vos", "laburás", "dale", "che", "metele".
Nunca hablás como chatbot corporativo.

FRASES TUYAS:
- "Comé el sapo primero. 🐸"
- "Hecho es mejor que perfecto. ✅"
- "¿Qué haría la mejor versión de vos ahora? 💪"
- "Las metas no escritas son sueños. 🎯"
{ctx}"""

# ─── GROQ ─────────────────────────────────────────────────────
async def mentor_reply(user_msg: str = "", trigger_prompt: str = None, modo: str = "conversacion") -> str:
    hist = memory["history"][-30:]
    if trigger_prompt:
        messages = hist + [{"role": "user", "content": f"[SISTEMA]: {trigger_prompt}"}]
    else:
        messages = hist + [{"role": "user", "content": user_msg}]
    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=400,
            messages=[{"role": "system", "content": build_system(modo)}] + messages,
        )
        reply = resp.choices[0].message.content
        if user_msg:
            memory["history"].append({"role": "user", "content": user_msg})
        memory["history"].append({"role": "assistant", "content": reply})
        memory["history"] = memory["history"][-50:]
        save_memory(memory)
        return reply
    except Exception as e:
        log.error(f"Error Groq: {e}")
        return "⚙️ Problema técnico. Seguí adelante, ya vuelvo."

# ─── CALLBACKS ────────────────────────────────────────────────
CALLBACKS = {
    "resp_arrancando": "El usuario arrancó. Celebralo en 1 oración y preguntá cómo va. Con emoji.",
    "resp_no_arranque": "El usuario no arrancó. Dále una micro-acción para empezar en 2 minutos. Con emoji.",
    "resp_contar": "El usuario quiere contarte algo. Invitalo con calidez. Con emoji.",
    "resp_siguiente": "Dame el siguiente paso concreto y físico. Sin vueltas. Con emoji.",
    "resp_trabado": "El usuario está trabado. Reducí la tarea al mínimo posible. Acción de 3 minutos. Con emoji.",
}

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != CHAT_ID:
        return

    if query.data == "resp_asana":
        await mostrar_asana(query.message, ctx, edit=False)
        return

    prompt = CALLBACKS.get(query.data, "Respondé naturalmente.")
    reply = await mentor_reply(trigger_prompt=prompt, modo="proactivo")
    await query.message.reply_text(reply, reply_markup=botones_conversacion())

# ─── ASANA DISPLAY ────────────────────────────────────────────
async def mostrar_asana(message, ctx, edit=False):
    try:
        tareas = await asana_get_tasks()
        if not tareas:
            txt = "📋 No tenés tareas pendientes en Asana. ¡Zona libre! 🎉"
        else:
            txt = "📋 *Tus tareas en Asana:*\n\n"
            for i, t in enumerate(tareas[:10], 1):
                nombre = t.get("name", "Sin nombre")
                vence = t.get("due_on", "")
                proyecto = ""
                if t.get("projects"):
                    proyecto = f" _[{t['projects'][0]['name']}]_"
                fecha = f" — 📅 {vence}" if vence else ""
                txt += f"{i}. {nombre}{proyecto}{fecha}\n"
            if len(tareas) > 10:
                txt += f"\n_...y {len(tareas)-10} más_"
        await message.reply_text(txt, parse_mode="Markdown", reply_markup=botones_conversacion())
    except Exception as e:
        log.error(f"Error Asana: {e}")
        await message.reply_text("⚙️ No pude conectar con Asana ahora. Revisá el token.")

# ─── HANDLERS ─────────────────────────────────────────────────
async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    await ctx.bot.send_chat_action(chat_id=CHAT_ID, action="typing")
    reply = await mentor_reply(user_msg=update.message.text)
    await update.message.reply_text(reply, reply_markup=botones_conversacion())

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    reply = await mentor_reply(trigger_prompt=(
        "Primera activación. Presentate como MENTOR. Sé memorable, con emojis. "
        "Mencioná que ahora estás conectado a Asana. "
        "Preguntá cuál es la situación más urgente a resolver."
    ))
    await update.message.reply_text(reply, reply_markup=botones_conversacion())

async def cmd_asana(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ver tareas de Asana."""
    if update.effective_chat.id != CHAT_ID: return
    await mostrar_asana(update.message, ctx)

async def cmd_nueva(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Crear tarea en Asana: /nueva [tarea] | [fecha opcional yyyy-mm-dd]"""
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if not args:
        await update.message.reply_text("Usá: /nueva [nombre de la tarea]\nEjemplo: /nueva Mandar propuesta a cliente X")
        return
    partes = args.split("|")
    nombre = partes[0].strip()
    due_on = partes[1].strip() if len(partes) > 1 else None
    try:
        tarea = await asana_create_task(nombre, due_on=due_on)
        reply = await mentor_reply(trigger_prompt=f"Creó tarea en Asana: '{nombre}'. ¿Es el sapo del día? Con emoji. Muy corto.")
        await update.message.reply_text(f"✅ Tarea creada en Asana: *{nombre}*\n\n{reply}", parse_mode="Markdown", reply_markup=botones_conversacion())
    except Exception as e:
        log.error(f"Error crear tarea: {e}")
        await update.message.reply_text("⚙️ No pude crear la tarea. Revisá el token de Asana.")

async def cmd_meta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if args:
        memory["metas"].append(args)
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró meta: '{args}'. Tracy: meta escrita = meta cumplida. Con emoji.")
    else:
        if memory["metas"]:
            lista = "\n".join(f"• {m}" for m in memory["metas"])
            reply = await mentor_reply(trigger_prompt=f"Ve sus metas:\n{lista}\nReflexión breve y desafío. Con emoji.")
        else:
            reply = "🎯 Sin metas registradas.\n\nUsá: /meta [tu meta]\nEjemplo: /meta Conseguir 3 clientes este mes"
    await update.message.reply_text(reply, reply_markup=botones_conversacion())

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

async def cmd_finanzas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if not args:
        fin = memory["finanzas"]
        deudas_activas = [d for d in fin["deudas"] if not d.get("pagado")]
        total = sum(d["monto"] for d in deudas_activas)
        txt = "💰 *RESUMEN FINANCIERO*\n\n"
        txt += f"Deudas activas: ${total:,.0f}\n" if deudas_activas else "Sin deudas ✅\n"
        for d in deudas_activas:
            txt += f"  • {d['nombre']}: ${d['monto']:,.0f}\n"
        registros = fin["registros"][-5:]
        if registros:
            txt += "\nÚltimos movimientos:\n"
            for r in registros:
                txt += f"  • {r['tipo']} ${r['monto']:,.0f} — {r['descripcion']}\n"
        txt += "\n/finanzas deuda [nombre] [monto]\n/finanzas ingreso [monto] [desc]\n/finanzas gasto [monto] [desc]\n/finanzas pague [deuda]"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return
    partes = args.split()
    cmd = partes[0].lower()
    if cmd == "deuda" and len(partes) >= 3:
        nombre = " ".join(partes[1:-1])
        monto = float(partes[-1])
        memory["finanzas"]["deudas"].append({"nombre": nombre, "monto": monto, "pagado": False})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró deuda: {nombre} ${monto}. Bola de nieve. No juzgues. Con emoji.")
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
                reply = await mentor_reply(trigger_prompt=f"Pagó deuda '{d['nombre']}' ${d['monto']}. ¡Libertad recuperada! Con emoji.")
                await update.message.reply_text(reply)
                return
        await update.message.reply_text(f"No encontré '{nombre}'.")
    else:
        await update.message.reply_text("💰 /finanzas deuda [nombre] [monto]\n/finanzas ingreso [monto] [desc]\n/finanzas gasto [monto] [desc]\n/finanzas pague [deuda]")

async def cmd_estado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    tz = pytz.timezone(TIMEZONE)
    ahora = datetime.now(tz).strftime("%H:%M — %d/%m/%Y")
    deudas = [d for d in memory["finanzas"]["deudas"] if not d.get("pagado")]
    await update.message.reply_text(
        f"⚡ *MENTOR ACTIVO*\n"
        f"🕐 {ahora}\n\n"
        f"🎯 Metas: {len(memory['metas'])}\n"
        f"💰 Deudas activas: {len(deudas)}\n"
        f"👔 Prospectos: {len(memory['prospectos'])}\n"
        f"🏆 Logros: {len(memory['logros'])}\n\n"
        f"*Comandos:*\n"
        f"/asana — ver tareas\n"
        f"/nueva [tarea] — crear en Asana\n"
        f"/meta /logro /finanzas /reset",
        parse_mode="Markdown"
    )

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    memory["history"] = []
    save_memory(memory)
    await update.message.reply_text("🔄 Historial limpiado. Metas y datos se mantienen.\n¿Qué está pasando?")

# ─── PROACTIVOS ───────────────────────────────────────────────
PROACTIVOS = {
    "buenos_dias": "Son las 8 AM. Arranque del día. Tracy: sapo primero. Preguntá la UNA tarea más importante. Muy corto. Con emoji.",
    "check_manana": "Son las 10:30. ¿Arrancó con el sapo? Corto, colega que pasa a ver. Con emoji.",
    "check_mediodia": "Son las 13h. ¿Qué logró en la mañana? Corto. Con emoji.",
    "empuje_tarde": "Son las 17h. El día no terminó. ¿Qué falta cerrar? Corto. Con emoji.",
    "cierre": "Son las 21h. Cierre del día. 1 logro + 1 compromiso para mañana. Cálido. Con emoji.",
    "push_random": "Mensaje inesperado. Frase Tracy, pregunta poderosa, o recordatorio de meta. Muy corto. Con emoji.",
}

async def send_proactive(app: Application, trigger: str):
    log.info(f"Proactivo: {trigger}")
    try:
        reply = await mentor_reply(trigger_prompt=PROACTIVOS[trigger], modo="proactivo")
        await app.bot.send_message(chat_id=CHAT_ID, text=reply, reply_markup=botones_proactivo())
    except Exception as e:
        log.error(f"Error proactivo: {e}")

def setup_scheduler(app: Application) -> AsyncIOScheduler:
    tz = pytz.timezone(TIMEZONE)
    s = AsyncIOScheduler(timezone=tz)
    s.add_job(send_proactive, "cron", hour=8,  minute=0,  args=[app, "buenos_dias"],    id="d1")
    s.add_job(send_proactive, "cron", hour=10, minute=30, args=[app, "check_manana"],   id="d2")
    s.add_job(send_proactive, "cron", hour=13, minute=0,  args=[app, "check_mediodia"], id="d3")
    s.add_job(send_proactive, "cron", hour=15, minute=30, args=[app, "push_random"],    id="d4")
    s.add_job(send_proactive, "cron", hour=17, minute=0,  args=[app, "empuje_tarde"],   id="d5")
    s.add_job(send_proactive, "cron", hour=21, minute=0,  args=[app, "cierre"],         id="d6")
    return s

# ─── MAIN ─────────────────────────────────────────────────────
async def post_init(app: Application):
    scheduler = setup_scheduler(app)
    scheduler.start()
    log.info("Scheduler activo.")

def main():
    log.info("Iniciando MENTOR Bot...")
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("asana",    cmd_asana))
    app.add_handler(CommandHandler("nueva",    cmd_nueva))
    app.add_handler(CommandHandler("meta",     cmd_meta))
    app.add_handler(CommandHandler("logro",    cmd_logro))
    app.add_handler(CommandHandler("finanzas", cmd_finanzas))
    app.add_handler(CommandHandler("estado",   cmd_estado))
    app.add_handler(CommandHandler("reset",    cmd_reset))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("MENTOR online.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
