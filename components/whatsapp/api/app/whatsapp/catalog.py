"""Spanish bot texts and option lists (OPW-011..022).

Every message is a plain dict understood by ``app.whatsapp.adapter``. Options
always also accept their number ("1", "2", ...) and "No sé" where offered
(OPW-012 numbered fallback). Staff names are never used; the bot speaks as the
campaign's display identity (OPW-020).
"""
from __future__ import annotations

from app.whatsapp.parsing import Option

NOTICE_VERSION_FALLBACK = "notice-2026-11"

DONT_KNOW = Option("dk", "No sé", synonyms=("no se", "nose", "ns"))
YES = Option("yes", "Sí", synonyms=("si", "s", "claro", "ok"))
NO = Option("no", "No", synonyms=("n",))

SERVICE_STATUS = [
    Option("available", "Sí hay", synonyms=("si", "hay", "tengo", "con luz", "con agua")),
    Option("unavailable", "No hay", synonyms=("no", "sin luz", "sin agua", "se fue")),
    Option("intermittent", "Va y viene", synonyms=("intermitente", "a ratos", "se va y viene")),
    DONT_KNOW,
]
SINCE = [
    Option("0", "Desde hoy", synonyms=("hoy",)),
    Option("1", "Desde ayer", synonyms=("ayer",)),
    Option("2", "Hace 2 o 3 días", synonyms=("anteayer", "2 dias", "3 dias")),
    Option("4", "Más de 3 días", synonyms=("mas de 3 dias", "una semana", "semanas")),
    DONT_KNOW,
]
SUPPLY = [
    Option("none", "Nada", synonyms=("ninguna", "no queda", "nada")),
    Option("little", "Poca", synonyms=("poco", "poquita")),
    Option("some", "Algo", synonyms=("suficiente", "bastante", "algo")),
    DONT_KNOW,
]
DEVICES = [
    Option("phone", "Teléfono", synonyms=("telefono", "celular", "telefonos", "celulares")),
    Option("medical_device", "Equipo médico", synonyms=("equipo medico", "nebulizador",
                                                       "concentrador", "oxigeno")),
    Option("lamp", "Lámpara", synonyms=("lampara", "linterna")),
    Option("power_bank", "Batería externa", synonyms=("power bank", "bateria")),
    Option("laptop", "Computadora", synonyms=("laptop", "computadora", "portatil")),
    Option("other", "Otro"),
]
YES_NO = [YES, NO]
YES_NO_DK = [YES, NO, DONT_KNOW]

SECTIONS = [
    Option("area", "Zona"),
    Option("services", "Luz y agua"),
    Option("needs", "Necesidades"),
    Option("urgent", "Urgencia"),
    Option("permissions", "Permisos"),
]

MENU = [
    Option("new", "Nuevo reporte", "Reportar luz, agua o necesidades",
           synonyms=("reportar", "reporte", "nuevo")),
    Option("continue", "Continuar", "Seguir con el reporte empezado", synonyms=("seguir",)),
    Option("update", "Actualizar", "¿Sigue el problema?"),
    Option("correct", "Corregir", "Arreglar tu último reporte"),
    Option("where", "Dónde hay ayuda", "Actividades cerca de tu zona", synonyms=("donde",)),
    Option("permissions", "Permisos", "Ver o retirar permisos"),
    Option("help", "Hablar con persona", synonyms=("ayuda", "persona")),
    Option("optout", "Dejar de recibir", "No más mensajes (BAJA)", synonyms=("baja",)),
]

COMMANDS_HINT = "Escribe MENÚ para ver opciones o AYUDA para hablar con una persona."


def text(body: str) -> dict:
    return {"kind": "text", "body": body}


def ask(body: str, options: list[Option], button: str = "Elegir") -> dict:
    """Buttons for up to 3 options, a list for up to 10, numbered text beyond."""
    if len(options) <= 3:
        return {"kind": "buttons", "body": body,
                "buttons": [{"id": o.id, "title": o.title} for o in options]}
    if len(options) <= 10:
        rows = []
        for o in options:
            row = {"id": o.id, "title": o.title}
            if o.description:
                row["description"] = o.description
            rows.append(row)
        return {"kind": "list", "body": body, "button": button, "rows": rows}
    lines = "\n".join(f"{i}. {o.title}" for i, o in enumerate(options, 1))
    return text(f"{body}\n\n{lines}\n\nResponde con el número.")


# --- Notice (OPW-011) ---


def notice(identity: str, org_name: str) -> dict:
    return ask(
        f"Hola, soy {identity}. {org_name} es la organización responsable de estos datos.\n\n"
        "Recogemos información sobre luz, agua y necesidades (agua, carga de equipos) para "
        "mostrar qué zonas necesitan ayuda a organizaciones que pueden actuar.\n\n"
        f"{identity} no entrega ayuda y reportar no garantiza recibirla. "
        "Puedes pedir hablar con una persona cuando quieras (escribe AYUDA) y dejar de "
        "recibir mensajes con BAJA.\n\n¿Quieres continuar?",
        [Option("ack", "Continuar", synonyms=("si", "continuar", "ok", "acepto")),
         Option("help", "Hablar con persona", synonyms=("persona", "ayuda")),
         Option("decline", "No, gracias", synonyms=("no",))],
    )


WELCOME_BACK = "Hola de nuevo. Vamos con un reporte nuevo."
NOTICE_DECLINED = ("Entendido, no guardamos ningún reporte. Si cambias de opinión, escribe "
                   "MENÚ.")

# --- Questions (OPW-013..015) ---

Q_PARISH = "¿En qué parroquia estás? Elige de la lista o escribe el nombre."
Q_SECTOR = "¿En qué sector de {parish}? Elige o escribe el nombre."
Q_AREA_PICK = "Encontré varias opciones. ¿Cuál es?"
Q_MEETING_POINT = "¿Cuál punto de encuentro te queda más cerca?"
Q_ADDRESS = ("Escribe una dirección o un punto de referencia cercano, o comparte tu "
             "ubicación. Si prefieres no darla, responde OMITIR.")
Q_ELECTRICITY = "¿Hay luz (electricidad) ahora donde estás?"
Q_ELECTRICITY_SINCE = "¿Desde cuándo no hay luz?"
Q_WATER = "¿Llega agua por tubería ahora?"
Q_WATER_SINCE = "¿Desde cuándo no llega el agua?"
Q_NEED_DRINKING = "¿Necesitan agua para beber?"
Q_DRINKING_PEOPLE = "¿Para cuántas personas? Responde con un número."
Q_DRINKING_LITERS = "¿Cuántos litros aproximadamente necesitan? Responde con un número."
Q_DRINKING_SUPPLY = "¿Cuánta agua para beber les queda?"
Q_NEED_OTHER = "¿Necesitan agua para otros usos (cocinar, lavar, limpieza)?"
Q_OTHER_PEOPLE = "¿Para cuántas personas? Responde con un número."
Q_NEED_CHARGING = "¿Necesitan un lugar para cargar teléfonos u otros equipos?"
Q_CHARGING_DEVICE = "¿Qué equipo necesitan cargar principalmente?"
Q_CHARGING_COUNT = "¿Cuántos equipos? Responde con un número."
Q_URGENT = ("¿Alguien está en riesgo hoy? Por ejemplo, sin agua para beber o con un equipo "
            "médico sin carga.")
Q_PERM_REFRESH = "¿Podemos escribirte cada pocos días para saber si sigue el problema?"
Q_PERM_AREA = "¿Quieres recibir avisos de ayuda disponible en tu zona?"
Q_PERM_CONTACT = ("¿Aceptas que organizaciones verificadas que ayudan en tu zona vean tu "
                  "número para contactarte?")

NONE_NEARBY = Option("none_nearby", "Ninguno cerca", synonyms=("ninguno", "ninguno cerca"))
SKIP = Option("skip", "Omitir", synonyms=("omitir", "saltar", "prefiero no"))

REASK_PREFIX = "No entendí tu respuesta. "
FREE_TEXT_STORED = ("Guardé tu comentario para que el equipo lo revise. Sigamos con la "
                    "siguiente pregunta.")
AREA_UNRESOLVED = ("No encontré esa zona. Guardé lo que escribiste para que el equipo la "
                   "revise. Sigamos.")
GPS_REDUCED = "Gracias. Usamos solo tu zona; no guardamos el punto exacto."
GPS_STORED = "Gracias, ubicación recibida."

# --- Urgent path (OPW-021) ---


def urgent_referral(referral: str) -> dict:
    return text(
        "Gracias por avisar. Este no es un servicio de emergencias. "
        f"{referral}\n\nUna persona del equipo revisará tu caso en horario de atención."
    )


# --- Media (OPW-022) ---

MEDIA_NOT_SUPPORTED = ("No podemos abrir notas de voz, fotos ni archivos. Por favor responde "
                       "con los botones o escribe. Escribe AYUDA para hablar con una persona.")

# --- Summary and confirmation (OPW-016) ---

CONFIRM = Option("confirm", "Confirmar", synonyms=("confirmar", "si", "correcto", "ok"))
FIX = Option("fix", "Corregir", synonyms=("corregir", "cambiar", "no"))
Q_FIX_SECTION = "¿Qué quieres corregir?"

_STATUS_ES = {"available": "sí hay", "unavailable": "no hay", "intermittent": "va y viene",
              "unknown": "no sabe"}
_SINCE_ES = {0: "desde hoy", 1: "desde ayer", 2: "hace 2-3 días", 4: "más de 3 días"}
_SUPPLY_ES = {"none": "nada", "little": "poca", "some": "algo", "unknown": "no sabe"}
_DEVICE_ES = {o.id: o.title.lower() for o in DEVICES}


def _since(days) -> str:
    if days is None:
        return ""
    return f" ({_SINCE_ES.get(days, f'hace {days} días')})"


def _yn(v) -> str:
    return {True: "sí", False: "no"}.get(v, "no sabe")


def summary(a: dict, area_label: str, location_label: str) -> dict:
    lines = [f"Zona: {area_label}"]
    if location_label:
        lines.append(location_label)
    lines.append(f"Luz: {_STATUS_ES.get(a.get('electricity'), 'no sabe')}"
                 f"{_since(a.get('electricity_since'))}")
    lines.append(f"Agua por tubería: {_STATUS_ES.get(a.get('water'), 'no sabe')}"
                 f"{_since(a.get('water_since'))}")
    needs = []
    if a.get("need_drinking"):
        bits = []
        if a.get("drinking_people") is not None:
            bits.append(f"{a['drinking_people']} personas")
        if a.get("drinking_liters") is not None:
            bits.append(f"{a['drinking_liters']:g} litros")
        if a.get("drinking_supply"):
            bits.append(f"queda {_SUPPLY_ES[a['drinking_supply']]}")
        needs.append("agua para beber" + (f" ({', '.join(bits)})" if bits else ""))
    if a.get("need_other"):
        p = a.get("other_people")
        needs.append("agua para otros usos" + (f" ({p} personas)" if p is not None else ""))
    if a.get("need_charging"):
        d = _DEVICE_ES.get(a.get("charging_device"), "equipos")
        n = a.get("charging_count")
        needs.append(f"cargar {d}" + (f" ({n})" if n else ""))
    lines.append("Necesidades: " + (", ".join(needs) if needs else "ninguna"))
    lines.append(f"Riesgo hoy: {_yn(a.get('urgent'))}")
    lines.append(
        f"Permisos: seguimiento {_yn(a.get('perm_refresh'))}, avisos {_yn(a.get('perm_area'))}, "
        f"ver tu número {_yn(a.get('perm_contact'))}"
    )
    body = "Este es tu reporte:\n\n" + "\n".join(f"• {x}" for x in lines) + "\n\n¿Está bien?"
    return ask(body, [CONFIRM, FIX])


def confirmation(a: dict, superseded: bool) -> dict:
    granted = []
    if a.get("perm_refresh"):
        granted.append("escribirte cada pocos días para saber si sigue el problema")
    if a.get("perm_area"):
        granted.append("enviarte avisos de ayuda en tu zona")
    if a.get("perm_contact"):
        granted.append("que organizaciones verificadas de tu zona vean tu número")
    perms = ("Nos diste permiso para: " + "; ".join(granted) + "."
             if granted else "No nos diste permisos de contacto; no te escribiremos.")
    lead = ("Actualizamos tu reporte anterior con este." if superseded
            else "Tu reporte quedó registrado.")
    return text(
        f"¡Gracias! {lead} Ayuda a mostrar dónde se necesita apoyo; no garantiza que llegue "
        f"ayuda.\n\n{perms} Puedes cambiarlo con PERMISOS. {COMMANDS_HINT}"
    )


# --- Commands (OPW-018) ---

HANDOFF = ("Listo, una persona del equipo te escribirá por aquí en horario de atención. "
           "Mientras tanto no enviaremos preguntas automáticas. Escribe MENÚ para volver.")
OPTOUT_CONFIRMATION = ("Listo, no te enviaremos más mensajes. Retiramos todos tus permisos. "
                       "Si quieres volver, escribe MENÚ.")
DELETE_REQUESTED = ("Recibimos tu solicitud para borrar tus datos. El equipo la procesará y te "
                    "confirmará por aquí. Escribe MENÚ para volver.")
NO_REPORT_TO_FIX = "No encontramos un reporte confirmado tuyo. Escribe MENÚ para empezar uno."
NOTHING_TO_GO_BACK = "Estás al inicio; no hay paso anterior."
WHERE_NONE = ("Por ahora no hay actividades públicas registradas cerca de tu zona. "
              "Te avisaremos si diste permiso de avisos.")
WHERE_NO_AREA = "Primero necesitamos tu zona. Escribe MENÚ y elige Nuevo reporte."
Q_MENU = "¿Qué quieres hacer?"
HOLDING = ("Recibimos tu mensaje. Hay muchos mensajes en este momento; te responderemos en "
           "orden en unos minutos.")
IDLE_HINT = "Hola. " + COMMANDS_HINT

PERMISSION_LABELS = {
    "refresh_prompts": "Seguimiento cada pocos días",
    "area_broadcasts": "Avisos de ayuda en tu zona",
    "contact_list": "Organizaciones ven tu número",
}


def permissions_menu(current: dict[str, bool]) -> dict:
    rows = [Option(p, label, "Activo, tocar para retirar" if current.get(p)
                   else "No activo, tocar para dar")
            for p, label in PERMISSION_LABELS.items()]
    rows.append(Option("done", "Listo"))
    lines = "\n".join(f"• {PERMISSION_LABELS[p]}: {'sí' if current.get(p) else 'no'}"
                      for p in PERMISSION_LABELS)
    return ask(f"Tus permisos:\n{lines}\n\nElige uno para cambiarlo.", rows)


def permission_options() -> list[Option]:
    return [*(Option(p, label) for p, label in PERMISSION_LABELS.items()), Option("done", "Listo")]
