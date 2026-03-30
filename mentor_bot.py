"""
MENTOR — Sistema Operativo de Ejecución Personal
Lógica GTD + Brian Tracy + Anti-procrastinación
Con Asana integrado | 24/7
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
        "rana_hoy": "",               # tarea más importante del día
        "estado_dia": {},             # energia, foco, ansiedad del check-in
        "compromisos": [],
        "tareas_pendientes": [],
        "tareas_completadas": [],
        "lecturas": [],
        "finanzas": {
            "deudas": [],
            "registros": []
        },
        "prospectos": [],
        "logros": [],
        "patrones": {                 # para detección de patrones
            "dias_sin_rana": 0,
            "excusas_frecuentes": [],
            "mejor_horario": "",
        }
    }

def save_memory(mem: dict):
    MEMORY_FILE.write_text(json.dumps(mem, ensure_ascii=False, indent=2))

memory = load_memory()

# ─── ASANA ────────────────────────────────────────────────────
async def asana_get_tasks() -> list:
    params = {
        "workspace": ASANA_WS,
        "assignee": "me",
        "completed_since": "now",
        "opt_fields": "name,due_on,projects.name,notes,permalink_url"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://app.asana.com/api/1.0/tasks", headers=ASANA_HEADERS, params=params)
        return resp.json().get("data", [])

async def asana_create_task(name: str, notes: str = "", due_on: str = None) -> dict:
    payload = {"data": {"name": name, "workspace": ASANA_WS, "assignee": "me", "notes": notes}}
    if due_on:
        payload["data"]["due_on"] = due_on
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://app.asana.com/api/1.0/tasks", headers=ASANA_HEADERS, json=payload)
        return resp.json().get("data", {})

# ─── BOTONES ──────────────────────────────────────────────────
def btn_dia():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Hecho", callback_data="rana_hecho"),
         InlineKeyboardButton("⚡ En progreso", callback_data="rana_progreso")],
        [InlineKeyboardButton("🚧 Bloqueado", callback_data="rana_bloqueado"),
         InlineKeyboardButton("😶 No empecé", callback_data="rana_no_empezo")],
    ])

def btn_accion():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➡️ Siguiente paso", callback_data="siguiente_paso"),
         InlineKeyboardButton("🆘 Estoy trabado", callback_data="trabado")],
        [InlineKeyboardButton("📋 Ver Asana", callback_data="ver_asana"),
         InlineKeyboardButton("🐸 Mi rana", callback_data="ver_rana")],
    ])

def btn_rescate():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💧 Rescate físico", callback_data="rescate_fisico"),
         InlineKeyboardButton("🧠 Rescate mental", callback_data="rescate_mental")],
        [InlineKeyboardButton("⏱️ Bloque 5 min", callback_data="bloque_5"),
         InlineKeyboardButton("⏱️ Bloque 25 min", callback_data="bloque_25")],
    ])

# ─── SYSTEM PROMPT ────────────────────────────────────────────
def build_system(modo: str = "conversacion") -> str:
    ctx = ""
    if memory.get("rana_hoy"):
        ctx += f"\nRANA DEL DIA (tarea más importante): {memory['rana_hoy']}"
    if memory.get("metas"):
        ctx += f"\nMETAS ACTIVAS: {', '.join(memory['metas'])}"
    if memory.get("estado_dia"):
        e = memory["estado_dia"]
        ctx += f"\nESTADO HOY: energía {e.get('energia','?')}/10, foco {e.get('foco','?')}/10, ansiedad {e.get('ansiedad','?')}/10"
    if memory.get("tareas_pendientes"):
        ctx += f"\nTAREAS PENDIENTES: {', '.join(memory['tareas_pendientes'][-3:])}"

    if modo == "proactivo":
        largo = "Máximo 2 oraciones. Corto, directo, con punch. Una sola acción o pregunta."
    elif modo == "checkeo":
        largo = "Máximo 3 oraciones. Pregunta concreta sobre el estado de la rana o las tareas."
    else:
        largo = "Hasta 5 oraciones. Podés extenderte si el usuario pide plan, análisis o está mal."

    return f"""Sos MENTOR — sistema operativo de ejecución personal. No sos un bot motivacional. Sos un entrenador ejecutivo que detecta el estado del usuario, baja todo a la siguiente acción física posible, hace seguimiento duro y corrige rápido.

PERFIL DEL USUARIO:
- Emprendedor/freelancer buscando estabilidad económica
- Problema central: resistencia al hacer, dispersión, procrastinación, todo-o-nada
- Filosofía Brian Tracy: Eat That Frog (rana = tarea más importante primero), metas escritas, disciplina como músculo
- Responde bien a: calidez cuando está mal, presión directa cuando da excusas, preguntas que bajan a acción
- Arranca entre 7-9 AM, Buenos Aires

TU LÓGICA DE INTERVENCIÓN (aplicala siempre):
1. DETECTAR estado: ¿confusión, resistencia, ansiedad, dispersión, cansancio real?
2. DECIDIR siguiente paso físico: no "avanzar el proyecto", sino "abrir archivo X y escribir 3 bullets"
3. HACER seguimiento: ¿lo hizo? ¿qué pasó?
4. CORREGIR rápido si se trabó

RESPUESTAS SEGÚN ESTADO:
- Confusión → "No te falta disciplina, te falta definición. ¿Cuál es el primer entregable?"
- Resistencia → "No hagas todo. Hacé la versión ridícula. 3 minutos."
- Ansiedad → "Salí del pensamiento. Agua, caminar 2 min, volvés."
- Dispersión → "Cerrá 3 estímulos. Una sola pestaña. Un bloque."
- Perfeccionismo → "Borrador feo > perfecto imaginario. Arrancá."
- Excusas → "Eso es resistencia, no un obstáculo real."
- Logro → celebrás genuinamente, empujás al siguiente

FRASES TUYAS (usarlas naturalmente):
- "No pienses el proyecto, tocá el proyecto."
- "Comé el sapo. Lo más difícil, primero. 🐸"
- "Hecho feo > perfecto imaginario. ✅"
- "¿Qué haría la mejor versión de vos ahora? 💪"
- "Dos minutos, animal. Arrancá."
- "No estás bloqueado, estás negociando con la incomodidad."

EMOJIS: uno o dos por mensaje, donde tenga sentido. 🎯💰🔥✅💪📋⚡🐸
ESTILO: Rioplatense. "vos", "laburás", "dale", "che", "metele". Nunca chatbot corporativo.
LARGO: {largo}
SIEMPRE terminás con UNA pregunta o micro-acción concreta.
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
        return "⚙️ Problema técnico. Seguí adelante."

# ─── CALLBACKS ────────────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != CHAT_ID:
        return

    data = query.data

    if data == "ver_asana":
        await _mostrar_asana(query.message)
        return

    if data == "ver_rana":
        rana = memory.get("rana_hoy", "")
        if rana:
            reply = await mentor_reply(trigger_prompt=f"El usuario pregunta por su rana del día: '{rana}'. Recordásela con energía y preguntá en qué estado está.", modo="checkeo")
        else:
            reply = "🐸 No definiste tu rana de hoy todavía. Usá /dia para arrancar el día."
        await query.message.reply_text(reply, reply_markup=btn_dia())
        return

    if data in ["rana_hecho", "rana_progreso", "rana_bloqueado", "rana_no_empezo"]:
        estados = {
            "rana_hecho": f"El usuario completó su rana: '{memory.get('rana_hoy', 'tarea principal')}'. Celebralo genuinamente y preguntá cuál es el siguiente paso importante. Con emoji.",
            "rana_progreso": f"El usuario está en progreso con su rana: '{memory.get('rana_hoy', '')}'. Alentalo a seguir y preguntá qué le falta para terminarla. Con emoji.",
            "rana_bloqueado": f"El usuario está bloqueado con su rana: '{memory.get('rana_hoy', '')}'. Detectá si es resistencia o problema real. Bajá a la acción más pequeña posible. Con emoji.",
            "rana_no_empezo": f"El usuario no empezó su rana: '{memory.get('rana_hoy', '')}'. No juzgues. Dále una micro-acción para arrancar en 2 minutos ahora mismo. Con emoji.",
        }
        reply = await mentor_reply(trigger_prompt=estados[data], modo="checkeo")
        markup = btn_rescate() if data in ["rana_bloqueado", "rana_no_empezo"] else btn_accion()
        await query.message.reply_text(reply, reply_markup=markup)
        return

    if data == "siguiente_paso":
        reply = await mentor_reply(trigger_prompt="Dame el siguiente paso físico y concreto. Una sola acción, ejecutable en menos de 5 minutos. Sin vueltas. Con emoji.", modo="proactivo")
        await query.message.reply_text(reply, reply_markup=btn_accion())
        return

    if data == "trabado":
        reply = await mentor_reply(trigger_prompt="El usuario está trabado. Reducí la tarea al mínimo absurdo. Acción de 3 minutos. Detectá si es perfeccionismo, miedo o tamaño. Con emoji.", modo="proactivo")
        await query.message.reply_text(reply, reply_markup=btn_rescate())
        return

    if data == "rescate_fisico":
        await query.message.reply_text(
            "💧 *Rescate físico:*\n\n1. Levantate ahora\n2. Tomá agua\n3. Caminá 2 minutos\n4. Cara con agua fría\n5. Volvés y hacés UN bloque de 5 min\n\n¿Listo para el bloque?",
            parse_mode="Markdown", reply_markup=btn_accion()
        )
        return

    if data == "rescate_mental":
        reply = await mentor_reply(trigger_prompt="Protocolo rescate mental: el usuario está atascado mentalmente. Ayudalo a identificar QUÉ lo traba exactamente (¿tamaño? ¿perfeccionismo? ¿miedo? ¿confusión?) y bajalo a UN paso físico.", modo="proactivo")
        await query.message.reply_text(reply, reply_markup=btn_accion())
        return

    if data in ["bloque_5", "bloque_25"]:
        mins = "5" if data == "bloque_5" else "25"
        rana = memory.get("rana_hoy", "tu tarea principal")
        await query.message.reply_text(
            f"⏱️ *Bloque de {mins} minutos arrancando ahora.*\n\n"
            f"Tarea: {rana}\n\n"
            f"Reglas:\n"
            f"• Solo esta tarea\n"
            f"• Sin notificaciones\n"
            f"• Sin perfección\n"
            f"• Al terminar me contás cómo quedó\n\n"
            f"¡Dale! 🔥",
            parse_mode="Markdown"
        )
        return

# ─── COMANDO /dia — INICIO DEL DÍA ────────────────────────────
async def cmd_dia(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ritual de inicio del día."""
    if update.effective_chat.id != CHAT_ID: return
    reply = await mentor_reply(
        trigger_prompt=(
            "Es el inicio del día. Arrancá el ritual de arranque con estas preguntas en orden, "
            "de a una (no todas juntas):\n"
            "1. ¿Cómo dormiste y cuántas horas?\n"
            "2. Energía, foco y ansiedad del 1 al 10\n"
            "3. ¿Cuál es tu objetivo más importante de hoy?\n"
            "4. ¿Cuál es tu RANA — la tarea más difícil e importante que vas a hacer PRIMERO?\n"
            "5. ¿Qué incomodidad estás dispuesto a tolerar hoy para avanzar?\n\n"
            "Arrancá con la pregunta 1. Corto, directo, con emoji."
        ), modo="proactivo"
    )
    await update.message.reply_text(reply, reply_markup=btn_accion())

# ─── COMANDO /rana ─────────────────────────────────────────────
async def cmd_rana(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Definir o ver la rana del día."""
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if args:
        memory["rana_hoy"] = args
        save_memory(memory)
        reply = await mentor_reply(
            trigger_prompt=f"El usuario definió su rana del día: '{args}'. Confirmala, recordale que va PRIMERO antes que todo, y preguntá cuándo la va a atacar. Con emoji.",
            modo="proactivo"
        )
        await update.message.reply_text(reply, reply_markup=btn_dia())
    else:
        rana = memory.get("rana_hoy", "")
        if rana:
            reply = await mentor_reply(
                trigger_prompt=f"Rana actual: '{rana}'. Preguntá en qué estado está. Con emoji.",
                modo="checkeo"
            )
            await update.message.reply_text(reply, reply_markup=btn_dia())
        else:
            await update.message.reply_text(
                "🐸 No definiste tu rana todavía.\n\nUsá: /rana [tu tarea más importante]\nEjemplo: /rana Mandar 5 propuestas en Upwork"
            )

# ─── COMANDO /trabado ──────────────────────────────────────────
async def cmd_trabado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Protocolo anti-procrastinación."""
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    prompt = f"El usuario está trabado con: '{args}'. " if args else "El usuario está trabado. "
    reply = await mentor_reply(
        trigger_prompt=prompt + (
            "Detectá el patrón: ¿perfeccionismo, miedo, tarea demasiado grande, saturación, distracción? "
            "Reducí al mínimo absurdo. Dá una acción de 3 minutos. Con emoji."
        ), modo="proactivo"
    )
    await update.message.reply_text(reply, reply_markup=btn_rescate())

# ─── COMANDO /cierre ───────────────────────────────────────────
async def cmd_cierre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ritual de cierre del día."""
    if update.effective_chat.id != CHAT_ID: return
    rana = memory.get("rana_hoy", "tu tarea principal")
    reply = await mentor_reply(
        trigger_prompt=(
            f"Es el cierre del día. La rana era: '{rana}'. "
            "Hacé estas 4 preguntas de cierre, de a una:\n"
            "1. ¿La rana se hizo?\n"
            "2. ¿Dónde mejoraste 1% hoy?\n"
            "3. ¿Dónde te mentiste o te saboteaste hoy?\n"
            "4. ¿Qué dejás listo para mañana? ¿Cuál va a ser la rana de mañana?\n\n"
            "Arrancá con la pregunta 1. Sin culpa, con exigencia reflexiva. Con emoji."
        ), modo="checkeo"
    )
    await update.message.reply_text(reply, reply_markup=btn_accion())

# ─── COMANDO /capturar ─────────────────────────────────────────
async def cmd_capturar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Captura rápida de idea o tarea."""
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if not args:
        await update.message.reply_text("Usá: /capturar [lo que tenés en la cabeza]\nEjemplo: /capturar llamar al contador esta semana")
        return
    memory["tareas_pendientes"].append(args)
    save_memory(memory)
    reply = await mentor_reply(
        trigger_prompt=f"Capturó: '{args}'. Confirmá que quedó registrado y preguntá si va a hoy, esta semana o al parking (algún día). Con emoji.",
        modo="proactivo"
    )
    await update.message.reply_text(reply, reply_markup=btn_accion())

# ─── COMANDO /asana ────────────────────────────────────────────
async def cmd_asana(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    await _mostrar_asana(update.message)

async def _mostrar_asana(message):
    try:
        tareas = await asana_get_tasks()
        if not tareas:
            await message.reply_text("📋 No tenés tareas pendientes en Asana. 🎉", reply_markup=btn_accion())
            return
        txt = "📋 *Tus tareas en Asana:*\n\n"
        for i, t in enumerate(tareas[:10], 1):
            nombre = t.get("name", "Sin nombre")
            vence = t.get("due_on", "")
            fecha = f" — 📅 {vence}" if vence else ""
            txt += f"{i}. {nombre}{fecha}\n"
        if len(tareas) > 10:
            txt += f"\n_...y {len(tareas)-10} más_"
        await message.reply_text(txt, parse_mode="Markdown", reply_markup=btn_accion())
    except Exception as e:
        log.error(f"Error Asana: {e}")
        await message.reply_text("⚙️ No pude conectar con Asana.")

# ─── COMANDO /nueva ────────────────────────────────────────────
async def cmd_nueva(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if not args:
        await update.message.reply_text("Usá: /nueva [tarea]\nEjemplo: /nueva Mandar propuesta a cliente X")
        return
    try:
        tarea = await asana_create_task(args)
        await update.message.reply_text(f"✅ Creada en Asana: *{args}*", parse_mode="Markdown", reply_markup=btn_accion())
    except Exception as e:
        log.error(f"Error crear tarea: {e}")
        await update.message.reply_text("⚙️ No pude crear la tarea en Asana.")

# ─── COMANDO /meta ─────────────────────────────────────────────
async def cmd_meta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if args:
        memory["metas"].append(args)
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró meta: '{args}'. Tracy: meta escrita = meta cumplida. Con emoji.", modo="proactivo")
    else:
        if memory["metas"]:
            lista = "\n".join(f"• {m}" for m in memory["metas"])
            reply = await mentor_reply(trigger_prompt=f"Ve sus metas:\n{lista}\nReflexión breve, desafío concreto. Con emoji.")
        else:
            reply = "🎯 Sin metas registradas.\n\nUsá: /meta [tu meta]\nEjemplo: /meta Conseguir 3 clientes este mes"
    await update.message.reply_text(reply, reply_markup=btn_accion())

# ─── COMANDO /logro ────────────────────────────────────────────
async def cmd_logro(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if args:
        memory["logros"].append({"logro": args, "fecha": datetime.now().strftime("%d/%m/%Y")})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Logró: '{args}'. Celebralo genuinamente y empujá al siguiente. Con emoji.")
        await update.message.reply_text(reply, reply_markup=btn_accion())
    else:
        await update.message.reply_text("Usá: /logro [lo que lograste]")

# ─── COMANDO /finanzas ─────────────────────────────────────────
async def cmd_finanzas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if not args:
        fin = memory["finanzas"]
        deudas_activas = [d for d in fin["deudas"] if not d.get("pagado")]
        total = sum(d["monto"] for d in deudas_activas)
        txt = "💰 *FINANZAS*\n\n"
        if deudas_activas:
            txt += f"Deudas: ${total:,.0f}\n"
            for d in deudas_activas:
                monto_str = str(d['monto'])
                txt += "  • " + d['nombre'] + ": $" + monto_str + "\n"
        else:
            txt += "Sin deudas ✅\n"
        registros = fin["registros"][-5:]
        if registros:
            txt += "\nMovimientos recientes:\n"
            for r in registros:
                txt += "  • " + r['tipo'] + " $" + str(r['monto']) + " — " + r['descripcion'] + "\n"
        txt += "\n/finanzas deuda [nombre] [monto]\n/finanzas ingreso [monto] [desc]\n/finanzas gasto [monto] [desc]"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return
    partes = args.split()
    cmd = partes[0].lower()
    if cmd == "deuda" and len(partes) >= 3:
        nombre = " ".join(partes[1:-1])
        monto = float(partes[-1])
        memory["finanzas"]["deudas"].append({"nombre": nombre, "monto": monto, "pagado": False})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró deuda: {nombre} ${monto}. Método bola de nieve. No juzgues. Con emoji.")
        await update.message.reply_text(reply)
    elif cmd in ["ingreso", "gasto"] and len(partes) >= 3:
        monto = float(partes[1])
        desc = " ".join(partes[2:])
        memory["finanzas"]["registros"].append({"fecha": datetime.now().strftime("%d/%m/%Y"), "tipo": cmd, "monto": monto, "descripcion": desc})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró {cmd} ${monto} ({desc}). Reforzá el hábito de registrar. Con emoji.")
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text("💰 /finanzas deuda [nombre] [monto]\n/finanzas ingreso [monto] [desc]\n/finanzas gasto [monto] [desc]")

# ─── COMANDO /estado ───────────────────────────────────────────
async def cmd_estado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    tz = pytz.timezone(TIMEZONE)
    ahora = datetime.now(tz).strftime("%H:%M — %d/%m/%Y")
    rana = memory.get("rana_hoy", "No definida")
    deudas = [d for d in memory["finanzas"]["deudas"] if not d.get("pagado")]
    await update.message.reply_text(
        f"⚡ *MENTOR ACTIVO*\n"
        f"🕐 {ahora}\n\n"
        f"🐸 Rana de hoy: {rana}\n"
        f"🎯 Metas: {len(memory['metas'])}\n"
        f"📋 Pendientes: {len(memory['tareas_pendientes'])}\n"
        f"💰 Deudas: {len(deudas)}\n"
        f"🏆 Logros: {len(memory['logros'])}\n\n"
        f"*Comandos:*\n"
        f"/dia — iniciar el día\n"
        f"/rana [tarea] — definir rana\n"
        f"/cierre — cerrar el día\n"
        f"/trabado — protocolo anti-procrastinación\n"
        f"/capturar [idea] — captura rápida\n"
        f"/asana — ver tareas\n"
        f"/nueva [tarea] — crear en Asana\n"
        f"/meta /logro /finanzas /reset",
        parse_mode="Markdown"
    )

# ─── COMANDO /reset ────────────────────────────────────────────
async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    memory["history"] = []
    memory["rana_hoy"] = ""
    memory["estado_dia"] = {}
    save_memory(memory)
    await update.message.reply_text("🔄 Historial y rana limpiados. Metas y datos se mantienen.\n\nUsá /dia para arrancar de nuevo.")

# ─── HANDLER PRINCIPAL ─────────────────────────────────────────
async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    await ctx.bot.send_chat_action(chat_id=CHAT_ID, action="typing")
    texto = update.message.text.lower()

    # Detección automática de estados
    if any(p in texto for p in ["no puedo", "no arranco", "no sé", "estoy perdido", "me trabo", "no sé por dónde"]):
        reply = await mentor_reply(user_msg=update.message.text, modo="conversacion")
        await update.message.reply_text(reply, reply_markup=btn_rescate())
        return

    reply = await mentor_reply(user_msg=update.message.text, modo="conversacion")
    await update.message.reply_text(reply, reply_markup=btn_accion())

# ─── START ─────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    reply = await mentor_reply(trigger_prompt=(
        "Primera activación. Presentate como MENTOR — sistema operativo de ejecución personal. "
        "No sos un bot de frases. Sos el que baja todo a acción concreta, hace seguimiento y corrige. "
        "Mencioná los comandos clave: /dia para arrancar, /rana para la tarea más importante, /trabado cuando te bloqueás. "
        "Preguntá cuál es la situación más urgente ahora mismo. Con emoji. Memorable."
    ))
    await update.message.reply_text(reply, reply_markup=btn_accion())

# ─── PROACTIVOS ───────────────────────────────────────────────
PROACTIVOS = {
    "buenos_dias": "Son las 8 AM. Recordale que arranque con /dia. Preguntá cuál va a ser su rana de hoy. Energético, muy corto. Con emoji.",
    "check_rana":  "Son las 10:30. Checkeo de la rana. ¿Empezó? Si no, protocolo de arranque mínimo. Con emoji.",
    "mediodia":    "Son las 13h. ¿Cómo va la rana? ¿Qué hizo esta mañana? Corto. Con emoji.",
    "tarde":       "Son las 17h. El día no terminó. ¿Qué falta cerrar? Una sola cosa. Con emoji.",
    "cierre":      "Son las 21h. Hora del cierre. Recordale /cierre para hacer el ritual. Cálido. Con emoji.",
    "push":        "Mensaje inesperado. Una frase de acción, pregunta sobre la rana, o recordatorio de meta. Muy corto. Con emoji.",
}

async def send_proactive(app: Application, trigger: str):
    log.info(f"Proactivo: {trigger}")
    try:
        reply = await mentor_reply(trigger_prompt=PROACTIVOS[trigger], modo="proactivo")
        markup = btn_dia() if trigger in ["check_rana", "mediodia"] else btn_accion()
        await app.bot.send_message(chat_id=CHAT_ID, text=reply, reply_markup=markup)
    except Exception as e:
        log.error(f"Error proactivo: {e}")

def setup_scheduler(app: Application) -> AsyncIOScheduler:
    tz = pytz.timezone(TIMEZONE)
    s = AsyncIOScheduler(timezone=tz)
    s.add_job(send_proactive, "cron", hour=8,  minute=0,  args=[app, "buenos_dias"], id="d1")
    s.add_job(send_proactive, "cron", hour=10, minute=30, args=[app, "check_rana"],  id="d2")
    s.add_job(send_proactive, "cron", hour=13, minute=0,  args=[app, "mediodia"],    id="d3")
    s.add_job(send_proactive, "cron", hour=15, minute=30, args=[app, "push"],        id="d4")
    s.add_job(send_proactive, "cron", hour=17, minute=0,  args=[app, "tarde"],       id="d5")
    s.add_job(send_proactive, "cron", hour=21, minute=0,  args=[app, "cierre"],      id="d6")
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
    app.add_handler(CommandHandler("dia",      cmd_dia))
    app.add_handler(CommandHandler("rana",     cmd_rana))
    app.add_handler(CommandHandler("cierre",   cmd_cierre))
    app.add_handler(CommandHandler("trabado",  cmd_trabado))
    app.add_handler(CommandHandler("capturar", cmd_capturar))
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
