"""
MENTOR — Sistema Operativo de Ejecución Personal
GTD + Brian Tracy + Anti-procrastinación + Memoria + Escalamiento
"""

import os, logging, json, httpx
from datetime import datetime, timedelta
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
        "rana_hoy": "",
        "rana_ayer": "",
        "estado_dia": {},
        "ultimo_mensaje": "",        # timestamp del último mensaje del usuario
        "silencio_escalado": 0,      # cuántas veces escalamos sin respuesta
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
        "registro_semanal": {        # para resumen cuantitativo
            "ranas_hechas": 0,
            "ranas_totales": 0,
            "dias_con_cierre": 0,
            "dias_con_arranque": 0,
            "semana_inicio": "",
        }
    }

def save_memory(mem: dict):
    MEMORY_FILE.write_text(json.dumps(mem, ensure_ascii=False, indent=2))

def registrar_actividad():
    """Actualiza el timestamp del último mensaje del usuario."""
    tz = pytz.timezone(TIMEZONE)
    memory["ultimo_mensaje"] = datetime.now(tz).isoformat()
    memory["silencio_escalado"] = 0
    save_memory(memory)

memory = load_memory()

# ─── ASANA ────────────────────────────────────────────────────
async def asana_get_tasks() -> list:
    params = {
        "workspace": ASANA_WS,
        "assignee": "me",
        "completed_since": "now",
        "opt_fields": "name,due_on,projects.name"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://app.asana.com/api/1.0/tasks", headers=ASANA_HEADERS, params=params)
        return resp.json().get("data", [])

async def asana_create_task(name: str, due_on: str = None) -> dict:
    payload = {"data": {"name": name, "workspace": ASANA_WS, "assignee": "me"}}
    if due_on:
        payload["data"]["due_on"] = due_on
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://app.asana.com/api/1.0/tasks", headers=ASANA_HEADERS, json=payload)
        return resp.json().get("data", {})

# ─── BOTONES ──────────────────────────────────────────────────
def btn_rana():
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
        [InlineKeyboardButton("⏱️ 5 minutos", callback_data="bloque_5"),
         InlineKeyboardButton("⏱️ 25 minutos", callback_data="bloque_25")],
    ])

def btn_rana_continua():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Sí, sigue siendo mi rana", callback_data="rana_misma"),
         InlineKeyboardButton("🔄 No, cambió", callback_data="rana_nueva")],
    ])

# ─── SYSTEM PROMPT ────────────────────────────────────────────
def build_system(modo: str = "conversacion") -> str:
    ctx = ""
    if memory.get("rana_hoy"):
        ctx += f"\nRANA DE HOY: {memory['rana_hoy']}"
    if memory.get("rana_ayer"):
        ctx += f"\nRANA DE AYER: {memory['rana_ayer']}"
    if memory.get("metas"):
        ctx += f"\nMETAS: {', '.join(memory['metas'])}"
    if memory.get("estado_dia"):
        e = memory["estado_dia"]
        ctx += f"\nESTADO: energía {e.get('energia','?')}/10, foco {e.get('foco','?')}/10, ansiedad {e.get('ansiedad','?')}/10"
    if memory.get("tareas_pendientes"):
        ctx += f"\nPENDIENTES: {', '.join(memory['tareas_pendientes'][-3:])}"

    rs = memory.get("registro_semanal", {})
    if rs.get("ranas_totales", 0) > 0:
        ctx += f"\nESTA SEMANA: {rs.get('ranas_hechas',0)}/{rs.get('ranas_totales',0)} ranas completadas"

    if modo == "proactivo":
        largo = "Máximo 2 oraciones. Corto, directo, con punch. Una acción o pregunta."
    elif modo == "silencio":
        largo = "Máximo 2 oraciones. Detectá resistencia. Reducí a la acción mínima posible."
    elif modo == "checkeo":
        largo = "Máximo 3 oraciones. Pregunta concreta sobre el estado."
    else:
        largo = "Hasta 5 oraciones si el usuario pide plan o está mal."

    return f"""Sos MENTOR — sistema operativo de ejecución personal. No sos motivacional. Sos un entrenador ejecutivo que detecta el estado, baja a acción física, hace seguimiento y corrige.

PERFIL:
- Emprendedor/freelancer buscando estabilidad
- Problema central: resistencia, dispersión, procrastinación, todo-o-nada
- Tracy: rana primero, metas escritas, disciplina como músculo
- Responde a: calidez cuando está mal, presión cuando da excusas

LÓGICA DE INTERVENCIÓN:
1. Detectar estado (confusión/resistencia/ansiedad/dispersión/cansancio)
2. Decidir siguiente paso físico: no "avanzar proyecto" sino "abrir archivo X, escribir 3 bullets"
3. Seguimiento: ¿lo hizo? ¿qué pasó?
4. Corregir rápido

RESPUESTAS SEGÚN ESTADO:
- Confusión → "¿Cuál es el primer entregable concreto?"
- Resistencia → "La versión ridícula. 3 minutos."
- Ansiedad → "Agua, caminar 2 min, volvés."
- Dispersión → "Una pestaña. Un bloque."
- Perfeccionismo → "Borrador feo > perfecto imaginario."
- Excusas → "Eso es resistencia, no un obstáculo."
- Silencio → reducís la tarea al mínimo absurdo
- Logro → celebrás genuinamente, empujás al siguiente

FRASES TUYAS:
- "Comé el sapo primero. 🐸"
- "No pienses el proyecto, tocá el proyecto."
- "Hecho feo > perfecto imaginario. ✅"
- "¿Qué haría la mejor versión de vos ahora? 💪"
- "No estás bloqueado, estás negociando con la incomodidad."

EMOJIS: uno o dos por mensaje. 🎯💰🔥✅💪📋⚡🐸
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

    registrar_actividad()
    data = query.data

    if data == "ver_asana":
        await _mostrar_asana(query.message)
        return

    if data == "ver_rana":
        rana = memory.get("rana_hoy", "")
        if rana:
            reply = await mentor_reply(trigger_prompt=f"Rana del día: '{rana}'. Recordásela con energía. ¿En qué estado está?", modo="checkeo")
            await query.message.reply_text(reply, reply_markup=btn_rana())
        else:
            await query.message.reply_text("🐸 No definiste tu rana. Usá /rana [tarea más importante].")
        return

    if data == "rana_misma":
        reply = await mentor_reply(trigger_prompt=f"Confirmó que su rana sigue siendo '{memory.get('rana_hoy','')}'. Bien. ¿Ya la atacó hoy? Con emoji.", modo="proactivo")
        await query.message.reply_text(reply, reply_markup=btn_rana())
        return

    if data == "rana_nueva":
        await query.message.reply_text("🐸 Dale, definí la nueva rana:\n\nUsá: /rana [tu tarea más importante de hoy]")
        return

    estados_rana = {
        "rana_hecho": f"Completó su rana '{memory.get('rana_hoy','')}'. Celebralo y preguntá el siguiente paso importante. Con emoji.",
        "rana_progreso": f"Está en progreso con '{memory.get('rana_hoy','')}'. Alentalo. ¿Qué falta para terminarla? Con emoji.",
        "rana_bloqueado": f"Bloqueado con '{memory.get('rana_hoy','')}'. ¿Es resistencia o problema real? Acción mínima posible. Con emoji.",
        "rana_no_empezo": f"No empezó '{memory.get('rana_hoy','')}'. Sin juicio. Micro-acción para los próximos 2 minutos. Con emoji.",
    }

    if data in estados_rana:
        if data == "rana_hecho":
            memory["registro_semanal"]["ranas_hechas"] = memory["registro_semanal"].get("ranas_hechas", 0) + 1
            save_memory(memory)
        reply = await mentor_reply(trigger_prompt=estados_rana[data], modo="checkeo")
        markup = btn_rescate() if data in ["rana_bloqueado", "rana_no_empezo"] else btn_accion()
        await query.message.reply_text(reply, reply_markup=markup)
        return

    if data == "siguiente_paso":
        reply = await mentor_reply(trigger_prompt="Siguiente paso físico y concreto. Una acción, menos de 5 minutos. Sin vueltas. Con emoji.", modo="proactivo")
        await query.message.reply_text(reply, reply_markup=btn_accion())
        return

    if data == "trabado":
        reply = await mentor_reply(trigger_prompt="Trabado. Reducí al mínimo absurdo. 3 minutos. Detectá patrón. Con emoji.", modo="proactivo")
        await query.message.reply_text(reply, reply_markup=btn_rescate())
        return

    if data == "rescate_fisico":
        await query.message.reply_text(
            "💧 *Rescate físico:*\n\n1. Levantate ahora\n2. Tomá agua\n3. Caminá 2 minutos\n4. Cara con agua fría\n5. Volvés y hacés 5 minutos de rana\n\n¿Listo?",
            parse_mode="Markdown", reply_markup=btn_accion()
        )
        return

    if data == "rescate_mental":
        reply = await mentor_reply(trigger_prompt="Rescate mental: identificá QUÉ lo traba exactamente (¿tamaño? ¿perfeccionismo? ¿miedo? ¿confusión?) y bajá a UN paso físico. Con emoji.")
        await query.message.reply_text(reply, reply_markup=btn_accion())
        return

    if data in ["bloque_5", "bloque_25"]:
        mins = "5" if data == "bloque_5" else "25"
        rana = memory.get("rana_hoy", "tu tarea principal")
        await query.message.reply_text(
            f"⏱️ *Bloque de {mins} minutos. Arrancá ahora.*\n\n"
            f"Tarea: {rana}\n\n"
            f"• Solo esta tarea\n• Sin notificaciones\n• Sin perfección\n\n"
            f"Al terminar me contás. 🔥",
            parse_mode="Markdown"
        )
        return

# ─── DETECCIÓN DE SILENCIO ────────────────────────────────────
async def check_silencio(app: Application):
    """Detecta si el usuario no respondió y escala el seguimiento."""
    if not memory.get("ultimo_mensaje"):
        return

    tz = pytz.timezone(TIMEZONE)
    ahora = datetime.now(tz)
    hora = ahora.hour

    # Solo actuar en horario activo (9-21h)
    if hora < 9 or hora > 21:
        return

    ultimo = datetime.fromisoformat(memory["ultimo_mensaje"])
    if ultimo.tzinfo is None:
        ultimo = tz.localize(ultimo)

    minutos_silencio = (ahora - ultimo).total_seconds() / 60
    escalado = memory.get("silencio_escalado", 0)

    # Primer escalamiento: 90 minutos sin respuesta
    if minutos_silencio >= 90 and escalado == 0:
        rana = memory.get("rana_hoy", "tu tarea principal")
        reply = await mentor_reply(
            trigger_prompt=f"El usuario lleva 90 minutos sin responder. Su rana es: '{rana}'. Intervención suave: preguntá qué está pasando. Corto. Con emoji.",
            modo="silencio"
        )
        await app.bot.send_message(chat_id=CHAT_ID, text=reply, reply_markup=btn_accion())
        memory["silencio_escalado"] = 1
        save_memory(memory)
        return

    # Segundo escalamiento: 3 horas
    if minutos_silencio >= 180 and escalado == 1:
        rana = memory.get("rana_hoy", "tu tarea principal")
        reply = await mentor_reply(
            trigger_prompt=f"3 horas sin respuesta. Rana: '{rana}'. Intervención directa: reducí la tarea al mínimo absurdo. Versión de 2 minutos. Sin piedad pero con respeto. Con emoji.",
            modo="silencio"
        )
        await app.bot.send_message(chat_id=CHAT_ID, text=reply, reply_markup=btn_rescate())
        memory["silencio_escalado"] = 2
        save_memory(memory)
        return

# ─── RESUMEN SEMANAL ──────────────────────────────────────────
async def resumen_semanal(app: Application):
    """Resumen cuantitativo del domingo."""
    rs = memory.get("registro_semanal", {})
    ranas_hechas = rs.get("ranas_hechas", 0)
    ranas_totales = rs.get("ranas_totales", 0)
    dias_cierre = rs.get("dias_con_cierre", 0)
    dias_arranque = rs.get("dias_con_arranque", 0)
    logros = len(memory.get("logros", []))

    pct_ranas = int((ranas_hechas / ranas_totales * 100)) if ranas_totales > 0 else 0

    txt = (
        f"📊 *Resumen semanal — evidencia real*\n\n"
        f"🐸 Ranas completadas: {ranas_hechas}/{ranas_totales} ({pct_ranas}%)\n"
        f"🌅 Días con arranque: {dias_arranque}/7\n"
        f"🌙 Días con cierre: {dias_cierre}/7\n"
        f"🏆 Logros registrados: {logros}\n\n"
    )

    if pct_ranas >= 80:
        txt += "Semana fuerte. Esos números no mienten. ¿Qué patrón repetís la semana que viene? 🔥"
    elif pct_ranas >= 50:
        txt += "Semana a medias. ¿Qué te frenó en los días que no completaste la rana? Nombralo."
    else:
        txt += "Semana difícil. No para juzgar — para entender. ¿Cuál fue el obstáculo real esta semana?"

    # Resetear contadores para la semana nueva
    tz = pytz.timezone(TIMEZONE)
    memory["registro_semanal"] = {
        "ranas_hechas": 0,
        "ranas_totales": 0,
        "dias_con_cierre": 0,
        "dias_con_arranque": 0,
        "semana_inicio": datetime.now(tz).strftime("%d/%m/%Y"),
    }
    save_memory(memory)

    await app.bot.send_message(chat_id=CHAT_ID, text=txt, parse_mode="Markdown", reply_markup=btn_accion())

# ─── VERIFICAR RANA DE AYER ───────────────────────────────────
async def check_rana_ayer(app: Application):
    """A las 8 AM verifica si la rana de ayer sigue vigente."""
    rana_ayer = memory.get("rana_hoy", "")
    if not rana_ayer:
        reply = await mentor_reply(
            trigger_prompt="Buenos días. No hay rana definida de ayer. Arrancá el día con /dia. Energético, corto. Con emoji.",
            modo="proactivo"
        )
        await app.bot.send_message(chat_id=CHAT_ID, text=reply, reply_markup=btn_accion())
        return

    # Guardar rana de ayer y preguntar si sigue
    memory["rana_ayer"] = rana_ayer
    memory["registro_semanal"]["ranas_totales"] = memory["registro_semanal"].get("ranas_totales", 0) + 1
    memory["registro_semanal"]["dias_con_arranque"] = memory["registro_semanal"].get("dias_con_arranque", 0) + 1
    save_memory(memory)

    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=f"🌅 Buenos días. Ayer tu rana era:\n\n*{rana_ayer}*\n\n¿Sigue siendo lo más importante hoy?",
        parse_mode="Markdown",
        reply_markup=btn_rana_continua()
    )

# ─── ASANA DISPLAY ────────────────────────────────────────────
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

# ─── HANDLERS ─────────────────────────────────────────────────
async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    registrar_actividad()
    await ctx.bot.send_chat_action(chat_id=CHAT_ID, action="typing")
    texto = update.message.text.lower()
    if any(p in texto for p in ["no puedo", "no arranco", "no sé", "estoy perdido", "me trabo", "estoy trabado"]):
        reply = await mentor_reply(user_msg=update.message.text, modo="conversacion")
        await update.message.reply_text(reply, reply_markup=btn_rescate())
        return
    reply = await mentor_reply(user_msg=update.message.text, modo="conversacion")
    await update.message.reply_text(reply, reply_markup=btn_accion())

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    registrar_actividad()
    reply = await mentor_reply(trigger_prompt=(
        "Primera activación. Presentate como MENTOR — sistema de ejecución personal. "
        "Mencioná los 3 comandos clave: /dia arrancar, /rana tarea más importante, /trabado cuando te bloqueás. "
        "Preguntá cuál es la situación más urgente ahora. Con emoji. Memorable."
    ))
    await update.message.reply_text(reply, reply_markup=btn_accion())

async def cmd_dia(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    registrar_actividad()
    memory["registro_semanal"]["dias_con_arranque"] = memory["registro_semanal"].get("dias_con_arranque", 0) + 1
    save_memory(memory)
    reply = await mentor_reply(
        trigger_prompt=(
            "Ritual de inicio del día. Arrancá con estas preguntas de a una:\n"
            "1. ¿Cómo dormiste y cuántas horas?\n"
            "2. Energía, foco, ansiedad del 1 al 10\n"
            "3. ¿Cuál es tu objetivo más importante de hoy?\n"
            "4. ¿Cuál es tu RANA — la tarea más difícil que vas a hacer PRIMERO?\n"
            "5. ¿Qué incomodidad tolerás hoy para avanzar?\n\n"
            "Arrancá con la pregunta 1. Corto, con emoji."
        ), modo="proactivo"
    )
    await update.message.reply_text(reply, reply_markup=btn_accion())

async def cmd_rana(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    registrar_actividad()
    args = " ".join(ctx.args).strip()
    if args:
        memory["rana_hoy"] = args
        memory["registro_semanal"]["ranas_totales"] = memory["registro_semanal"].get("ranas_totales", 0) + 1
        save_memory(memory)
        reply = await mentor_reply(
            trigger_prompt=f"Definió rana: '{args}'. Va PRIMERO antes que todo. ¿Cuándo la ataca hoy? Con emoji.",
            modo="proactivo"
        )
        await update.message.reply_text(reply, reply_markup=btn_rana())
    else:
        rana = memory.get("rana_hoy", "")
        if rana:
            reply = await mentor_reply(trigger_prompt=f"Rana actual: '{rana}'. ¿En qué estado está? Con emoji.", modo="checkeo")
            await update.message.reply_text(reply, reply_markup=btn_rana())
        else:
            await update.message.reply_text("🐸 Sin rana definida.\n\nUsá: /rana [tu tarea más importante]\nEjemplo: /rana Mandar 5 propuestas en Upwork")

async def cmd_cierre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    registrar_actividad()
    memory["registro_semanal"]["dias_con_cierre"] = memory["registro_semanal"].get("dias_con_cierre", 0) + 1
    save_memory(memory)
    rana = memory.get("rana_hoy", "tu tarea principal")
    reply = await mentor_reply(
        trigger_prompt=(
            f"Ritual de cierre. Rana fue: '{rana}'. Hacé estas 4 preguntas de a una:\n"
            "1. ¿La rana se hizo?\n"
            "2. ¿Dónde mejoraste 1% hoy?\n"
            "3. ¿Dónde te mentiste o saboteaste?\n"
            "4. ¿Cuál va a ser la rana de mañana?\n\n"
            "Pregunta 1 primero. Sin culpa, con exigencia reflexiva. Con emoji."
        ), modo="checkeo"
    )
    await update.message.reply_text(reply, reply_markup=btn_accion())

async def cmd_trabado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    registrar_actividad()
    args = " ".join(ctx.args).strip()
    prompt = f"Trabado con: '{args}'. " if args else "Trabado. "
    reply = await mentor_reply(
        trigger_prompt=prompt + "Detectá patrón (perfeccionismo/miedo/tamaño/saturación). Acción de 3 minutos. Con emoji.",
        modo="proactivo"
    )
    await update.message.reply_text(reply, reply_markup=btn_rescate())

async def cmd_capturar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    registrar_actividad()
    args = " ".join(ctx.args).strip()
    if not args:
        await update.message.reply_text("Usá: /capturar [lo que tenés en la cabeza]")
        return
    memory["tareas_pendientes"].append(args)
    save_memory(memory)
    reply = await mentor_reply(
        trigger_prompt=f"Capturó: '{args}'. Confirmá y preguntá: ¿va a hoy, esta semana o al parking? Con emoji.",
        modo="proactivo"
    )
    await update.message.reply_text(reply, reply_markup=btn_accion())

async def cmd_asana(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    registrar_actividad()
    await _mostrar_asana(update.message)

async def cmd_nueva(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    registrar_actividad()
    args = " ".join(ctx.args).strip()
    if not args:
        await update.message.reply_text("Usá: /nueva [tarea]\nEjemplo: /nueva Mandar propuesta a cliente X")
        return
    try:
        await asana_create_task(args)
        await update.message.reply_text(f"✅ Creada en Asana: *{args}*", parse_mode="Markdown", reply_markup=btn_accion())
    except Exception as e:
        log.error(f"Error crear tarea: {e}")
        await update.message.reply_text("⚙️ No pude crear la tarea en Asana.")

async def cmd_meta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    registrar_actividad()
    args = " ".join(ctx.args).strip()
    if args:
        memory["metas"].append(args)
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Meta registrada: '{args}'. Tracy: meta escrita = meta cumplida. Primer paso. Con emoji.")
    else:
        if memory["metas"]:
            lista = "\n".join(f"• {m}" for m in memory["metas"])
            reply = await mentor_reply(trigger_prompt=f"Metas:\n{lista}\nReflexión breve y desafío concreto. Con emoji.")
        else:
            reply = "🎯 Sin metas registradas.\n\nUsá: /meta [tu meta]"
    await update.message.reply_text(reply, reply_markup=btn_accion())

async def cmd_logro(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    registrar_actividad()
    args = " ".join(ctx.args).strip()
    if args:
        memory["logros"].append({"logro": args, "fecha": datetime.now().strftime("%d/%m/%Y")})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Logró: '{args}'. Celebralo genuinamente y empujá al siguiente. Con emoji.")
        await update.message.reply_text(reply, reply_markup=btn_accion())
    else:
        await update.message.reply_text("Usá: /logro [lo que lograste]")

async def cmd_finanzas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    registrar_actividad()
    args = " ".join(ctx.args).strip()
    if not args:
        fin = memory["finanzas"]
        deudas_activas = [d for d in fin["deudas"] if not d.get("pagado")]
        total = sum(d["monto"] for d in deudas_activas)
        txt = "💰 *FINANZAS*\n\n"
        if deudas_activas:
            txt += "Deudas: $" + str(int(total)) + "\n"
            for d in deudas_activas:
                txt += "  • " + d["nombre"] + ": $" + str(int(d["monto"])) + "\n"
        else:
            txt += "Sin deudas ✅\n"
        registros = fin["registros"][-5:]
        if registros:
            txt += "\nMovimientos:\n"
            for r in registros:
                txt += "  • " + r["tipo"] + " $" + str(int(r["monto"])) + " — " + r["descripcion"] + "\n"
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
        reply = await mentor_reply(trigger_prompt=f"Deuda: {nombre} ${monto}. Bola de nieve. Sin juicio. Con emoji.")
        await update.message.reply_text(reply)
    elif cmd in ["ingreso", "gasto"] and len(partes) >= 3:
        monto = float(partes[1])
        desc = " ".join(partes[2:])
        memory["finanzas"]["registros"].append({"fecha": datetime.now().strftime("%d/%m/%Y"), "tipo": cmd, "monto": monto, "descripcion": desc})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró {cmd} ${monto} ({desc}). Hábito de registrar. Con emoji.")
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text("💰 /finanzas deuda [nombre] [monto]\n/finanzas ingreso [monto] [desc]\n/finanzas gasto [monto] [desc]")

async def cmd_semana(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ver estadísticas de la semana."""
    if update.effective_chat.id != CHAT_ID: return
    rs = memory.get("registro_semanal", {})
    ranas_hechas = rs.get("ranas_hechas", 0)
    ranas_totales = rs.get("ranas_totales", 0)
    dias_cierre = rs.get("dias_con_cierre", 0)
    dias_arranque = rs.get("dias_con_arranque", 0)
    logros = len(memory.get("logros", []))
    pct = int((ranas_hechas / ranas_totales * 100)) if ranas_totales > 0 else 0
    await update.message.reply_text(
        f"📊 *Semana en curso*\n\n"
        f"🐸 Ranas: {ranas_hechas}/{ranas_totales} ({pct}%)\n"
        f"🌅 Días con arranque: {dias_arranque}\n"
        f"🌙 Días con cierre: {dias_cierre}\n"
        f"🏆 Logros: {logros}\n\n"
        f"Datos reales. Sin humo.",
        parse_mode="Markdown",
        reply_markup=btn_accion()
    )

async def cmd_estado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    tz = pytz.timezone(TIMEZONE)
    ahora = datetime.now(tz).strftime("%H:%M — %d/%m/%Y")
    rana = memory.get("rana_hoy", "No definida")
    deudas = [d for d in memory["finanzas"]["deudas"] if not d.get("pagado")]
    await update.message.reply_text(
        f"⚡ *MENTOR ACTIVO*\n"
        f"🕐 {ahora}\n\n"
        f"🐸 Rana: {rana}\n"
        f"🎯 Metas: {len(memory['metas'])}\n"
        f"💰 Deudas: {len(deudas)}\n"
        f"🏆 Logros: {len(memory['logros'])}\n\n"
        f"*Comandos:*\n"
        f"/dia /rana /cierre /trabado\n"
        f"/capturar /asana /nueva\n"
        f"/meta /logro /finanzas\n"
        f"/semana /reset",
        parse_mode="Markdown"
    )

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    memory["history"] = []
    memory["rana_hoy"] = ""
    memory["estado_dia"] = {}
    memory["silencio_escalado"] = 0
    save_memory(memory)
    await update.message.reply_text("🔄 Historial y rana limpiados. Metas y datos se mantienen.\n\nUsá /dia para arrancar.")

# ─── PROACTIVOS ───────────────────────────────────────────────
PROACTIVOS = {
    "check_rana":  "Son las 10:30. ¿Cómo va la rana? ¿La atacó? Corto, colega que pasa a ver. Con emoji.",
    "mediodia":    "Son las 13h. ¿Qué logró esta mañana? Preguntá concretamente. Corto. Con emoji.",
    "tarde":       "Son las 17h. El día no terminó. ¿Qué falta cerrar? Una cosa. Con emoji.",
    "cierre_auto": "Son las 21h. Hora del /cierre. Recordáselo brevemente. Cálido. Con emoji.",
    "push":        "Mensaje inesperado. Frase de acción, pregunta sobre rana, o dato de la semana. Muy corto. Con emoji.",
}

async def send_proactive(app: Application, trigger: str):
    log.info(f"Proactivo: {trigger}")
    try:
        reply = await mentor_reply(trigger_prompt=PROACTIVOS[trigger], modo="proactivo")
        markup = btn_rana() if trigger == "check_rana" else btn_accion()
        await app.bot.send_message(chat_id=CHAT_ID, text=reply, reply_markup=markup)
    except Exception as e:
        log.error(f"Error proactivo: {e}")

# ─── SCHEDULER ────────────────────────────────────────────────
def setup_scheduler(app: Application) -> AsyncIOScheduler:
    tz = pytz.timezone(TIMEZONE)
    s = AsyncIOScheduler(timezone=tz)

    # Verificar rana de ayer + buenos días a las 8 AM
    s.add_job(check_rana_ayer,  "cron", hour=8,  minute=0,  args=[app], id="d1")
    # Check rana 10:30
    s.add_job(send_proactive,   "cron", hour=10, minute=30, args=[app, "check_rana"],  id="d2")
    # Mediodía 13h
    s.add_job(send_proactive,   "cron", hour=13, minute=0,  args=[app, "mediodia"],    id="d3")
    # Push random 15:30
    s.add_job(send_proactive,   "cron", hour=15, minute=30, args=[app, "push"],        id="d4")
    # Tarde 17h
    s.add_job(send_proactive,   "cron", hour=17, minute=0,  args=[app, "tarde"],       id="d5")
    # Cierre 21h
    s.add_job(send_proactive,   "cron", hour=21, minute=0,  args=[app, "cierre_auto"], id="d6")
    # Check silencio cada 30 minutos
    s.add_job(check_silencio,   "interval", minutes=30, args=[app], id="silencio")
    # Resumen semanal domingos 10 AM
    s.add_job(resumen_semanal,  "cron", day_of_week="sun", hour=10, minute=0, args=[app], id="semana")

    return s

# ─── MAIN ─────────────────────────────────────────────────────
async def post_init(app: Application):
    scheduler = setup_scheduler(app)
    scheduler.start()
    log.info("Scheduler activo — 8 eventos + silencio + resumen semanal.")

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
    app.add_handler(CommandHandler("semana",   cmd_semana))
    app.add_handler(CommandHandler("estado",   cmd_estado))
    app.add_handler(CommandHandler("reset",    cmd_reset))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("MENTOR online.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
