"""
MENTOR — Bot de Telegram personalizado
Padre / Jefe / Coach / Asesor integrado en un solo personaje
Filosofía Brian Tracy | Rioplatense | 24/7
"""
 
import os, logging, json, asyncio
from datetime import datetime
from pathlib import Path
 
from groq import Groq
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
 
# ─── CONFIG ───────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_KEY = os.environ["GROQ_API_KEY"]
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
        "lecturas": [],          # {libro, paginas_meta, paginas_actuales, terminado}
        "finanzas": {
            "ingresos_meta": 0,
            "deudas": [],        # {nombre, monto, pagado}
            "ahorros_meta": 0,
            "registros": []      # {fecha, tipo, monto, descripcion}
        },
        "prospectos": [],        # {nombre, empresa, estado, ultimo_contacto}
        "logros": [],
    }
 
def save_memory(mem: dict):
    MEMORY_FILE.write_text(json.dumps(mem, ensure_ascii=False, indent=2))
 
memory = load_memory()
 
# ─── SYSTEM PROMPT ────────────────────────────────────────────
def build_system() -> str:
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
 
    return f"""Sos MENTOR — un único personaje que integra cuatro roles en uno: padre sabio y contenedor, jefe exigente y justo, coach de vida y hábitos, y asesor financiero práctico. No sos un chatbot, sos la figura de referencia que el usuario necesita y que tal vez no tuvo siempre cerca.
 
PERFIL DEL USUARIO:
- Estancado en este momento en: finanzas/deudas, trabajo e ingresos inestables, hábitos que no sostiene, foco/productividad, salud física y mental
- Sigue la filosofía de Brian Tracy: "Eat That Frog", "Si lo crees lo creas", Seminario Fénix
- Responde bien a: calidez primero cuando está mal, exigencia cuando está cómodo o dando excusas
- Horario: arranca el día entre 7 y 9 AM
- Trabaja como emprendedor/freelancer buscando estabilidad
 
TU CARÁCTER:
- Padre sabio: escuchás de verdad, contenés sin juzgar, pero tampoco sobreprotegés
- Jefe mentor: pedís resultados, no aceptás excusas, pero siempre explicás el porqué
- Coach Brian Tracy: "comé el sapo" primero (la tarea difícil antes que nada), metas escritas, visualización, autodisciplina como músculo
- Asesor financiero: concreto, sin humo, con números reales, plan de deudas claro
- Todo integrado en UNA sola voz: masculina, cálida, directa, rioplatense
 
FILOSOFÍA BRIAN TRACY QUE APLICÁS:
- La tarea más difícil primero, siempre (Eat That Frog)
- Las metas escritas se cumplen — las no escritas son deseos
- "Si lo crees lo creas": el diálogo interno determina los resultados externos
- Seminario Fénix: la vida se puede reinventar, no importa el punto de partida
- Disciplina = libertad. Cada hábito construido es una deuda menos con el futuro
- Hacer una sola cosa a la vez con foco total
 
CÓMO RESPONDÉS SEGÚN EL ESTADO DEL USUARIO:
- Si está mal o angustiado → primero contenés, escuchás, validás. Después guiás.
- Si está estancado o dando excusas → lo nombrás con amor pero sin piedad: "Eso es una excusa, no un obstáculo."
- Si está cómodo o sin movimiento → subís la exigencia, lo desafiás
- Si logró algo → celebrás genuinamente y empujás al siguiente nivel
- Siempre terminás con UNA pregunta concreta o UNA acción específica
 
MÓDULO TRABAJO / PROSPECTOS:
- Cuando el usuario quiere buscar trabajo o clientes, lo ayudás a redactar mensajes de prospección para LinkedIn o Upwork
- Le generás mails de seguimiento ("follow-up") listos para copiar y pegar
- Le recordás hacer seguimiento a prospectos registrados
- Principio Tracy: "el dinero está en el seguimiento" — 80% de las ventas se cierran después del 5to contacto
 
ESTILO DE ESCRITURA:
- Español rioplatense: "vos", "laburás", "dale", "che", "metele", "piola"
- Mensajes cortos: 3-4 oraciones máximo en conversación cotidiana
- Sin listas ni bullets en mensajes normales
- SIEMPRE terminás con una pregunta o micro-acción concreta
- Jamás hablás como chatbot corporativo
 
FRASES TUYAS (naturales, no todas juntas):
- "Comé el sapo. Lo más difícil, primero."
- "¿Eso es lo que le dirías a alguien que querés?"
- "Las metas no escritas son sueños. ¿La escribiste?"
- "El seguimiento es donde está el dinero. ¿Cuándo los llamás?"
- "Hecho es mejor que perfecto. Siempre."
- "¿Qué haría la mejor versión de vos en este momento?"
- "Cada peso que ordenás es un paso hacia la libertad."
{ctx}"""
 
 
# ─── LLAMADA A CLAUDE ─────────────────────────────────────────
async def mentor_reply(user_msg: str = "", trigger_prompt: str = None) -> str:
    hist = memory["history"][-40:]
 
    if trigger_prompt:
        messages = hist + [{"role": "user", "content": f"[SISTEMA]: {trigger_prompt}"}]
    else:
        messages = hist + [{"role": "user", "content": user_msg}]
 
    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=500,
            messages=[{"role": "system", "content": build_system()}] + messages,
        )
        reply = resp.choices[0].message.content
 
        if user_msg:
            memory["history"].append({"role": "user", "content": user_msg})
        memory["history"].append({"role": "assistant", "content": reply})
        memory["history"] = memory["history"][-60:]
        save_memory(memory)
        return reply
 
    except Exception as e:
        log.error(f"Error Claude: {e}")
        return "Tuve un problema técnico. Seguí adelante, ya vuelvo. 🔧"
 
 
# ─── PROACTIVOS ───────────────────────────────────────────────
PROACTIVOS = {
    "buenos_dias": (
        "Son las 8 AM. Mandá el mensaje de arranque del día como padre/mentor. "
        "Recordale la filosofía Tracy: comé el sapo primero. "
        "Preguntá cuál es la UNA tarea más importante de hoy. Energético, directo, breve."
    ),
    "check_manana": (
        "Son las 10:30. Checkeo rápido: ¿arrancó con el sapo? "
        "Si hay compromisos pendientes de ayer, preguntá por ellos. "
        "Tono: jefe que pasa a ver, no a juzgar."
    ),
    "check_mediodia": (
        "Son las 13h. Checkeo de mediodía como colega/mentor. "
        "Preguntá qué logró en la mañana. Si perdió tiempo, que lo nombre. "
        "Recordale que la tarde es otra oportunidad."
    ),
    "empuje_tarde": (
        "Son las 17h. Empuje de tarde. El día no terminó. "
        "Preguntá qué le falta cerrar. Tono: jefe que quiere ver resultados antes del cierre."
    ),
    "cierre": (
        "Son las 21h. Cierre del día como padre sabio. "
        "Pedile: 1 logro del día (por chico que sea) y 1 compromiso concreto para mañana. "
        "Celebrá lo que hizo, sin importar qué tan pequeño. "
        "Recordale que cada día construye hacia la vida que quiere."
    ),
    "push_random": (
        "Mandá un mensaje proactivo inesperado. Puede ser: "
        "una frase de Brian Tracy aplicada a su situación, "
        "una pregunta poderosa sobre sus metas o finanzas, "
        "o un recordatorio de seguimiento a prospectos si tiene alguno registrado. "
        "Corto, con punch, como si te acordaras de él de repente."
    ),
    "check_lecturas": (
        "Checkeo semanal de lecturas. Preguntá cómo va con el libro en curso. "
        "Recordale la importancia de leer según Tracy: los líderes son lectores. "
        "Si no está leyendo, desafialo a comprometerse con 10 páginas por día."
    ),
}
 
 
# ─── HANDLERS ─────────────────────────────────────────────────
async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    await ctx.bot.send_chat_action(chat_id=CHAT_ID, action="typing")
    reply = await mentor_reply(user_msg=update.message.text)
    await update.message.reply_text(reply)
 
 
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    reply = await mentor_reply(trigger_prompt=(
        "Primera activación del bot. Presentate como MENTOR — "
        "padre, jefe, coach y asesor en uno. Sé memorable. "
        "Mencioná brevemente para qué estás y arrancá preguntando: "
        "¿cuál es la situación más urgente que quiere resolver primero?"
    ))
    await update.message.reply_text(reply)
 
 
async def cmd_meta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Agregar o ver metas."""
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if args:
        memory["metas"].append(args)
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"El usuario registró esta meta: '{args}'. Reconocela, aplicá Tracy (meta escrita = meta cumplida), hacé una pregunta poderosa sobre el primer paso.")
    else:
        if memory["metas"]:
            lista = "\n".join(f"• {m}" for m in memory["metas"])
            reply = await mentor_reply(trigger_prompt=f"El usuario quiere ver sus metas. Son:\n{lista}\nHacé una reflexión breve y desafialo a priorizar.")
        else:
            reply = "Todavía no registraste metas.\n\nUsá: /meta [tu meta]\nEjemplo: /meta Generar $500 de ingresos este mes"
    await update.message.reply_text(reply)
 
 
async def cmd_tarea(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Agregar tarea pendiente."""
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if args:
        memory["tareas_pendientes"].append(args)
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró esta tarea: '{args}'. Confirmala y preguntá si es el 'sapo' (la más difícil/importante) o si hay algo más urgente primero.")
    else:
        if memory["tareas_pendientes"]:
            lista = "\n".join(f"• {t}" for t in memory["tareas_pendientes"])
            await update.message.reply_text(f"📋 Tareas pendientes:\n{lista}")
        else:
            await update.message.reply_text("No tenés tareas pendientes registradas.\n\nUsá: /tarea [descripción]")
 
 
async def cmd_hecho(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Marcar tarea como completada."""
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if not args:
        if memory["tareas_pendientes"]:
            lista = "\n".join(f"{i+1}. {t}" for i, t in enumerate(memory["tareas_pendientes"]))
            await update.message.reply_text(f"¿Cuál completaste?\n{lista}\n\nUsá: /hecho [nombre de la tarea]")
        else:
            await update.message.reply_text("No tenés tareas pendientes.")
        return
    # Buscar la tarea
    encontrada = None
    for t in memory["tareas_pendientes"]:
        if args.lower() in t.lower():
            encontrada = t
            break
    if encontrada:
        memory["tareas_pendientes"].remove(encontrada)
        memory["tareas_completadas"].append({"tarea": encontrada, "fecha": datetime.now().isoformat()})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Completó la tarea: '{encontrada}'. Celebralo genuinamente y preguntá cuál es la siguiente.")
    else:
        await update.message.reply_text(f"No encontré '{args}' en tus pendientes. Fijate en /tarea la lista exacta.")
    if encontrada:
        await update.message.reply_text(reply)
 
 
async def cmd_lectura(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Gestionar lecturas."""
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
            await update.message.reply_text(txt or "No hay lecturas registradas.")
        else:
            await update.message.reply_text("No tenés lecturas registradas.\n\nUsá: /lectura [título del libro]\nPara actualizar páginas: /lectura progreso [título] [páginas actuales]")
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
                reply = await mentor_reply(trigger_prompt=f"Actualizó su lectura de '{l['libro']}' a página {paginas}. Motivalo con Tracy: los líderes son lectores.")
                await update.message.reply_text(reply)
                return
        await update.message.reply_text(f"No encontré '{titulo}' en tus lecturas.")
    else:
        # Agregar nuevo libro
        nuevo = {"libro": args, "paginas_meta": 0, "paginas_actuales": 0, "terminado": False}
        memory["lecturas"].append(nuevo)
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Empezó a leer '{args}'. Felicitalo y preguntale cuántas páginas por día se compromete a leer, recordándole la regla Tracy de 10 páginas diarias.")
        await update.message.reply_text(reply)
 
 
async def cmd_finanzas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Gestionar finanzas."""
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
 
    if not args:
        fin = memory["finanzas"]
        deudas_activas = [d for d in fin["deudas"] if not d.get("pagado")]
        total_deudas = sum(d["monto"] for d in deudas_activas)
        registros = fin["registros"][-5:]
        txt = f"💰 RESUMEN FINANCIERO\n\n"
        if deudas_activas:
            txt += f"Deudas activas: ${total_deudas:,.0f}\n"
            for d in deudas_activas:
                txt += f"  • {d['nombre']}: ${d['monto']:,.0f}\n"
        else:
            txt += "Sin deudas registradas\n"
        if registros:
            txt += f"\nÚltimos movimientos:\n"
            for r in registros:
                txt += f"  • {r['tipo']} ${r['monto']:,.0f} — {r['descripcion']}\n"
        txt += f"\nComandos:\n/finanzas deuda [nombre] [monto]\n/finanzas ingreso [monto] [descripción]\n/finanzas gasto [monto] [descripción]\n/finanzas pague [nombre deuda]"
        await update.message.reply_text(txt)
        return
 
    partes = args.split()
    cmd = partes[0].lower()
 
    if cmd == "deuda" and len(partes) >= 3:
        nombre = " ".join(partes[1:-1])
        monto = float(partes[-1])
        memory["finanzas"]["deudas"].append({"nombre": nombre, "monto": monto, "pagado": False})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró una deuda: {nombre} de ${monto}. Reconocela, no juzgues, y proponé un primer paso concreto del plan de pago (método bola de nieve de Tracy: pagar la más chica primero).")
        await update.message.reply_text(reply)
 
    elif cmd in ["ingreso", "gasto"] and len(partes) >= 3:
        monto = float(partes[1])
        desc = " ".join(partes[2:])
        memory["finanzas"]["registros"].append({"fecha": datetime.now().strftime("%d/%m/%Y"), "tipo": cmd, "monto": monto, "descripcion": desc})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró un {cmd} de ${monto} ({desc}). Comentá brevemente y reforzá el hábito de registrar todo.")
        await update.message.reply_text(reply)
 
    elif cmd == "pague" and len(partes) >= 2:
        nombre = " ".join(partes[1:])
        for d in memory["finanzas"]["deudas"]:
            if nombre.lower() in d["nombre"].lower():
                d["pagado"] = True
                save_memory(memory)
                reply = await mentor_reply(trigger_prompt=f"Pagó la deuda '{d['nombre']}' de ${d['monto']}. ¡Celebralo! Cada deuda pagada es libertad recuperada. Siguiendo el método bola de nieve, preguntá cuál sigue.")
                await update.message.reply_text(reply)
                return
        await update.message.reply_text(f"No encontré la deuda '{nombre}'.")
 
    else:
        await update.message.reply_text("Comandos de finanzas:\n/finanzas — ver resumen\n/finanzas deuda [nombre] [monto]\n/finanzas ingreso [monto] [descripción]\n/finanzas gasto [monto] [descripción]\n/finanzas pague [nombre deuda]")
 
 
async def cmd_prospecto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Gestionar prospectos de trabajo/clientes."""
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
 
    if not args:
        if memory["prospectos"]:
            txt = "👔 PROSPECTOS:\n"
            for p in memory["prospectos"]:
                txt += f"\n• {p['nombre']} ({p.get('empresa','')}) — {p['estado']}\n  Último contacto: {p.get('ultimo_contacto','nunca')}"
            await update.message.reply_text(txt)
        else:
            await update.message.reply_text("No tenés prospectos registrados.\n\nUsá: /prospecto [nombre] [empresa]\nPara generar follow-up: /prospecto followup [nombre]")
        return
 
    partes = args.split()
    if partes[0].lower() == "followup" and len(partes) >= 2:
        nombre = " ".join(partes[1:])
        prospecto = next((p for p in memory["prospectos"] if nombre.lower() in p["nombre"].lower()), None)
        if prospecto:
            prospecto["ultimo_contacto"] = datetime.now().strftime("%d/%m/%Y")
            prospecto["estado"] = "followup enviado"
            save_memory(memory)
            reply = await mentor_reply(trigger_prompt=f"Generá un mail de follow-up profesional y cálido para el prospecto '{prospecto['nombre']}' de '{prospecto.get('empresa','')}'. Estilo profesional, corto, con llamada a la acción clara. Aplicá la regla Tracy: el 80% de las ventas se cierran después del 5to contacto.")
            await update.message.reply_text(f"📧 MAIL DE FOLLOW-UP listo para copiar:\n\n{reply}")
        else:
            await update.message.reply_text(f"No encontré el prospecto '{nombre}'.")
    else:
        nombre = partes[0]
        empresa = " ".join(partes[1:]) if len(partes) > 1 else ""
        memory["prospectos"].append({"nombre": nombre, "empresa": empresa, "estado": "contacto inicial", "ultimo_contacto": datetime.now().strftime("%d/%m/%Y")})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Registró un nuevo prospecto: {nombre} de {empresa}. Felicitalo por dar el paso y generá un mensaje de contacto inicial para LinkedIn/Upwork, profesional y personalizado.")
        await update.message.reply_text(f"✅ Prospecto guardado.\n\n📩 MENSAJE INICIAL sugerido:\n\n{reply}")
 
 
async def cmd_logro(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Registrar un logro."""
    if update.effective_chat.id != CHAT_ID: return
    args = " ".join(ctx.args).strip()
    if args:
        memory["logros"].append({"logro": args, "fecha": datetime.now().strftime("%d/%m/%Y")})
        save_memory(memory)
        reply = await mentor_reply(trigger_prompt=f"Logró: '{args}'. Celebralo genuinamente como padre/mentor orgulloso. Después empujá al siguiente paso.")
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text("Usá: /logro [lo que lograste]\nEjemplo: /logro Conseguí mi primer cliente en Upwork")
 
 
async def cmd_estado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ver estado del sistema."""
    if update.effective_chat.id != CHAT_ID: return
    tz = pytz.timezone(TIMEZONE)
    ahora = datetime.now(tz).strftime("%H:%M — %d/%m/%Y")
    pendientes = [c for c in memory["compromisos"] if not c.get("cumplido")]
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
        f"Comandos:\n"
        f"/meta /tarea /hecho /lectura\n"
        f"/finanzas /prospecto /logro /reset"
    )
 
 
async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    memory["history"] = []
    save_memory(memory)
    await update.message.reply_text("🔄 Historial limpiado. Todo lo demás (metas, tareas, finanzas) se mantiene.\n¿Qué está pasando?")
 
 
# ─── SCHEDULER ────────────────────────────────────────────────
async def send_proactive(app: Application, trigger: str):
    log.info(f"Proactivo: {trigger}")
    try:
        reply = await mentor_reply(trigger_prompt=PROACTIVOS[trigger])
        await app.bot.send_message(chat_id=CHAT_ID, text=reply)
    except Exception as e:
        log.error(f"Error proactivo {trigger}: {e}")
 
 
def setup_scheduler(app: Application) -> AsyncIOScheduler:
    tz = pytz.timezone(TIMEZONE)
    s = AsyncIOScheduler(timezone=tz)
    s.add_job(send_proactive, "cron", hour=8,  minute=0,  args=[app, "buenos_dias"],   id="d1")
    s.add_job(send_proactive, "cron", hour=10, minute=30, args=[app, "check_manana"],  id="d2")
    s.add_job(send_proactive, "cron", hour=13, minute=0,  args=[app, "check_mediodia"],id="d3")
    s.add_job(send_proactive, "cron", hour=15, minute=30, args=[app, "push_random"],   id="d4")
    s.add_job(send_proactive, "cron", hour=17, minute=0,  args=[app, "empuje_tarde"],  id="d5")
    s.add_job(send_proactive, "cron", hour=21, minute=0,  args=[app, "cierre"],        id="d6")
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
 
    log.info("MENTOR online.")
    app.run_polling(drop_pending_updates=True)
 
 
if __name__ == "__main__":
    main()
