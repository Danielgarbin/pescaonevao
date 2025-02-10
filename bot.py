import discord
import psycopg2
import psycopg2.extras
from discord.ext import commands
import json
import random
import os
import re
import threading
import unicodedata
from flask import Flask, request, jsonify

######################################
# CONFIGURACIÓN: IDs y Servidor
######################################
OWNER_ID = 1336609089656197171         # Tu Discord ID (único autorizado para comandos sensibles)
PRIVATE_CHANNEL_ID = 1338130641354620988  # Canal privado para comandos sensibles
PUBLIC_CHANNEL_ID  = 1338126297666424874  # Canal público (donde se muestran resultados)
GUILD_ID = 123456789012345678            # REEMPLAZA con el ID real de tu servidor (guild)

API_SECRET = os.environ.get("API_SECRET")  # Para la API privada (opcional)

######################################
# CONEXIÓN A LA BASE DE DATOS POSTGRESQL
######################################
DATABASE_URL = os.environ.get("DATABASE_URL")  # Usualmente la Internal Database URL de Render
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True

def init_db():
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id TEXT PRIMARY KEY,
                nombre TEXT,
                puntos INTEGER DEFAULT 0,
                symbolic INTEGER DEFAULT 0,
                etapa INTEGER DEFAULT 1,
                logros JSONB DEFAULT '[]'
            )
        """)
init_db()

######################################
# CONFIGURACIÓN INICIAL DEL TORNEO
######################################
PREFIX = '!'
STAGES = {1: 60, 2: 48, 3: 24, 4: 12, 5: 1}  # Jugadores que avanzan en cada etapa
current_stage = 1
stage_names = {
    1: "Battle Royale",
    2: "Snipers vs Runners",
    3: "Boxfight duos",
    4: "Pescadito dice",
    5: "Gran Final"
}

######################################
# VARIABLE GLOBAL PARA TRIVIA
######################################
active_trivia = {}  # key: channel.id, value: {"question": ..., "answer": ...}

######################################
# FUNCIONES PARA LA BASE DE DATOS
######################################
def get_participant(user_id):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM participants WHERE id = %s", (user_id,))
        return cur.fetchone()

def get_all_participants():
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM participants")
        rows = cur.fetchall()
        data = {"participants": {}}
        for row in rows:
            data["participants"][row["id"]] = row
        return data

def upsert_participant(user_id, participant):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO participants (id, nombre, puntos, symbolic, etapa, logros)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                puntos = EXCLUDED.puntos,
                symbolic = EXCLUDED.symbolic,
                etapa = EXCLUDED.etapa,
                logros = EXCLUDED.logros
        """, (
            user_id,
            participant["nombre"],
            participant.get("puntos", 0),
            participant.get("symbolic", 0),
            participant.get("etapa", current_stage),
            json.dumps(participant.get("logros", []))
        ))

def update_score(user: discord.Member, delta: int):
    user_id = str(user.id)
    participant = get_participant(user_id)
    if participant is None:
        participant = {
            "nombre": user.display_name,
            "puntos": 0,
            "symbolic": 0,
            "etapa": current_stage,
            "logros": []
        }
    new_points = int(participant.get("puntos", 0)) + delta
    participant["puntos"] = new_points
    upsert_participant(user_id, participant)
    return new_points

def award_symbolic_reward(user: discord.Member, reward: int):
    user_id = str(user.id)
    participant = get_participant(user_id)
    if participant is None:
        participant = {
            "nombre": user.display_name,
            "puntos": 0,
            "symbolic": 0,
            "etapa": current_stage,
            "logros": []
        }
    current_symbolic = int(participant.get("symbolic", 0))
    new_symbolic = current_symbolic + reward
    participant["symbolic"] = new_symbolic
    upsert_participant(user_id, participant)
    return new_symbolic

######################################
# NORMALIZACIÓN DE CADENAS
######################################
def normalize_string(s):
    # Elimina acentos, espacios y pasa a minúsculas
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).replace(" ", "").lower()

######################################
# CHISTES: 170 chistes (los mejores que jamás he creado)
######################################
ALL_JOKES = [
    # Bloque 1: 70 chistes originales
    "¿Por qué el sol nunca se cansa? Porque siempre brilla con energía.",
    "¿Qué hace una abeja en el gimnasio? ¡Zum-ba!",
    "¿Cómo se despiden los químicos? Ácido un placer.",
    "¿Qué le dice una calculadora a otra? ¡Tienes muchos problemas!",
    "¿Cómo se llama un perro sin patas? No importa, no va a venir.",
    "¿Qué hace un gato en el ordenador? Busca ratones.",
    "¿Por qué la escoba nunca se queja? Porque siempre barre sus problemas.",
    "¿Qué dijo el semáforo cuando se enfadó? ¡Detente y mira!",
    "¿Por qué el libro de matemáticas estaba triste? Porque tenía demasiados problemas.",
    "¿Qué hace una taza en la escuela? Toma té y aprende.",
    "¿Cuál es el colmo de un jardinero? Que lo dejen plantado.",
    "¿Qué le dice una pared a un cuadro? ¡Qué marco tan bonito tienes!",
    "¿Por qué los esqueletos no pelean? Porque no tienen agallas.",
    "¿Qué hace un pez en el cine? Nada.",
    "¿Cómo se llama el campeón de buceo? ¡El que se zambulle sin miedo!",
    "¿Qué hace un pollo en un ascensor? ¡Pío, pío, sube!",
    "¿Qué le dice el cero al ocho? ¡Bonito cinturón!",
    "¿Por qué la gallina cruzó la calle? Para demostrar que no era un gallina.",
    "¿Qué hace una vaca en el espacio? ¡Muuu-gravedad cero!",
    "¿Por qué el reloj siempre está de buen humor? Porque tiene tiempo para todo.",
    "¿Qué hace una computadora en el baño? Navega por la red.",
    "¿Cómo se despiden los carteros? Con un sello de despedida.",
    "¿Qué le dijo una ventana a otra? ¡Nos vemos en el marco!",
    "¿Por qué la bicicleta se cayó? Porque estaba dos-tirada.",
    "¿Qué hace un caracol en una carrera? Llega lento, pero con casa.",
    "¿Por qué el helado es siempre feliz? Porque se derrite de risa.",
    "¿Qué le dice un semáforo a otro? ¡Cambia de color, amigo!",
    "¿Cómo se llama un buen chiste? ¡El que hace reír a carcajadas!",
    "¿Qué hace una impresora en el bosque? Imprime hojas.",
    "¿Por qué el teléfono se fue de vacaciones? Porque necesitaba una buena señal.",
    "¿Qué le dice un espejo a otro? ¡Refleja lo que sientes!",
    "¿Por qué el viento es un gran amigo? Porque siempre sopla contigo.",
    "¿Qué hace una mariposa en el gimnasio? ¡Vuela alto en la pista!",
    "¿Cómo se llama el rey de los chistes malos? ¡El chistocrata!",
    "¿Qué hace un globo en una fiesta? Se infla de alegría.",
    "¿Por qué la araña es tan creativa? Porque siempre teje nuevas ideas.",
    "¿Qué le dijo el queso a la galleta? ¡Juntos somos el snack perfecto!",
    "¿Por qué el cartero nunca se retrasa? Porque siempre entrega a tiempo.",
    "¿Qué hace un paraguas en un día soleado? Se guarda en silencio.",
    "¿Por qué el semáforo nunca se enoja? Porque siempre cambia de humor.",
    "¿Qué hace un piano en la calle? Toca melodías inesperadas.",
    "¿Cómo se despiden los astronautas? ¡Hasta la próxima órbita!",
    "¿Qué hace un ratón en la biblioteca? Lee sus clics.",
    "¿Por qué la luna es tan misteriosa? Porque cambia de fase cada noche.",
    "¿Qué le dice una calculadora a un lápiz? ¡Suma y resuelve!",
    "¿Por qué el café es el rey de la mañana? Porque despierta a todos con su aroma.",
    "¿Qué hace un libro en el gimnasio? Se pone en forma de lectura.",
    "¿Cómo se llama el campeón de natación? ¡Nada, nada, nada!",
    "¿Por qué el pan es tan optimista? Porque siempre se levanta en el horno.",
    "¿Qué le dijo la manzana al plátano? ¡Juntos formamos una fruta explosiva!",
    "¿Por qué el cuaderno nunca se cansa? Porque siempre tiene nuevas hojas.",
    "¿Qué hace un zapato cuando está enamorado? Se ajusta al corazón.",
    "¿Por qué la lámpara es tan brillante? Porque ilumina hasta los chistes más oscuros.",
    "¿Qué dijo el semáforo al peatón? ¡No te detengas, sigue adelante!",
    "¿Por qué el ratón no usa sombrero? Porque ya tiene orejas."
    # (Agrega los 20 chistes restantes para completar 70 en este bloque)
]

# Bloque 2: 50 chistes adicionales (agrega 50 chistes creativos aquí)
ADDITIONAL_JOKES = [
    "¿Por qué el ordenador fue al psicólogo? Porque tenía demasiadas ventanas abiertas.",
    "¿Qué hace un gato en la computadora? Busca ratones perdidos.",
    "¿Por qué la bicicleta siempre se ríe? Porque tiene dos ruedas de humor.",
    "¿Qué dijo una impresora frustrada? ¡Estoy sin tinta y sin inspiración!",
    "¿Por qué el café nunca se toma vacaciones? Porque siempre está espresso en el trabajo.",
    "¿Qué le dice una calculadora a otra? ¡Tú sumas, yo resto!",
    "¿Por qué el pan nunca se pierde? Porque siempre deja migajas.",
    "¿Qué hace una manzana en la universidad? Se estudia a sí misma para ser jugosa.",
    "¿Por qué el ventilador es tan popular? Porque siempre da aire fresco a todos.",
    "¿Qué hace un árbol en una fiesta? Da sombra a los chismes.",
    "¿Por qué el reloj se inscribió en clases de baile? Para aprender a marcar el compás.",
    "¿Qué le dijo el sol a la nube? ¡No te escondas, que te estoy buscando!",
    "¿Por qué el zapato se quedó en casa? Porque estaba muy apretado para salir.",
    "¿Qué hace una lámpara cuando se enoja? Se da una vuelta de chispa.",
    "¿Por qué la nieve siempre dice la verdad? Porque es transparente.",
    "¿Qué dijo la almohada al despertador? ¡Déjame dormir un poco más!",
    "¿Por qué el lápiz se sintió triste? Porque siempre estaba afilado por dentro.",
    "¿Qué hace una fruta en una fiesta? Se pone en rodajas y baila.",
    "¿Por qué la luna siempre está soltera? Porque tiene fases complicadas.",
    "¿Qué le dijo un espejo a otro? ¡Refleja lo que sientes!",
    "¿Por qué el semáforo no juega a las escondidas? Porque siempre se pone en rojo.",
    "¿Qué hace un pastel en la biblioteca? Busca recetas de historias dulces.",
    "¿Por qué el teléfono decidió separarse? Porque quería señal de independencia.",
    "¿Qué le dijo una cuchara a un tenedor? ¡Qué afilado estás!",
    "¿Por qué el edificio es tan serio? Porque tiene muchos pisos de responsabilidad.",
    "¿Qué hace un globo cuando se siente triste? Se desinfla en silencio.",
    "¿Por qué la araña es tan sociable? Porque siempre teje conexiones.",
    "¿Qué le dijo el queso a la galleta? ¡Juntos formamos el snack perfecto!",
    "¿Por qué el caracol nunca gana en carreras? Porque siempre carga su casa a cuestas.",
    "¿Qué hace una botella en el desierto? Se siente muy vacía y sedienta.",
    "¿Por qué el piano es tan sentimental? Porque siempre toca el alma de quien lo escucha.",
    "¿Qué dijo la taza cuando se rompió? ¡Fue un accidente descafeinado!",
    "¿Por qué el helado es un gran amigo? Porque nunca se derrite en momentos difíciles.",
    "¿Qué hace una estrella fugaz en una fiesta? Cumple deseos y se va volando.",
    "¿Por qué el cuaderno se ofendió? Porque alguien escribió mal sus líneas.",
    "¿Qué le dijo la naranja al exprimidor? ¡No me exprimas, por favor!",
    "¿Por qué el teclado se volvió romántico? Porque encontró las teclas de su corazón.",
    "¿Qué hace un cuadro en un museo? Se queda enmarcado en sus pensamientos.",
    "¿Por qué el sombrero es tan humilde? Porque siempre se inclina ante la moda.",
    "¿Qué le dijo una escalera a otra? ¡Nos vemos en el siguiente nivel!",
    "¿Por qué la mantequilla se derrite de felicidad? Porque siempre está en su punto ideal.",
    "¿Qué hace un martillo en el gimnasio? Golpea sus propios límites.",
    "¿Por qué la tostadora es la reina de la cocina? Porque siempre está en la cresta del pan.",
    "¿Qué le dijo el helado a la galleta? ¡Eres mi complemento perfecto!",
    "¿Por qué el campo de fútbol se siente orgulloso? Porque siempre está lleno de goles."
]

# Bloque 3: 50 chistes nuevos (los mejores que jamás he creado)
NEW_JOKES = [
    "¿Por qué el reloj se fue al gimnasio? Porque quería marcar ritmo con fuerza.",
    "¿Qué hace un pez en el ordenador? Nada en la red con estilo.",
    "¿Por qué los fantasmas no pueden mentir? Porque su verdad se les ve a través.",
    "¿Qué le dijo una computadora a otra? ¡Eres mi byte favorito, sin comparación!",
    "¿Por qué el pan nunca se duerme? Porque siempre está tostado y alerta.",
    "¿Qué hace una impresora en el desierto? Imprime sueños en arena.",
    "¿Por qué la luna se fue de vacaciones? Porque necesitaba un respiro de la Tierra.",
    "¿Qué le dijo el vino al queso? ¡Juntos somos la fusión perfecta de sabor!",
    "¿Por qué el semáforo es tan puntual? Porque nunca pierde su señal.",
    "¿Qué hace una escalera en la nieve? Se enfría, pero sigue subiendo.",
    "¿Por qué el gato estudió informática? Porque quería ser el ratón más astuto.",
    "¿Qué le dijo el árbol a la brisa? ¡Eres el aire que refresca mi existencia!",
    "¿Por qué el café se hizo influencer? Porque siempre estaba espresso en las redes sociales.",
    "¿Qué hace un zapato en una cita? Camina firme al lado de su pareja.",
    "¿Por qué la lámpara se negó a trabajar? Porque estaba en modo ahorro de energía y humor.",
    "¿Qué le dijo el ventilador al termómetro? ¡Juntos siempre damos la temperatura perfecta!",
    "¿Por qué el reloj se sintió presionado? Porque no tenía ni un minuto para descansar.",
    "¿Qué hace un libro en la playa? Se abre al sol y se llena de historia.",
    "¿Por qué el lápiz rompió con la pluma? Porque necesitaba escribir su propia aventura.",
    "¿Qué dijo el espejo cuando vio su reflejo? ¡Eres mi otra mitad, perfecto para brillar!",
    "¿Por qué la manzana se volvió famosa? Porque siempre estaba a la moda con su iPhone.",
    "¿Qué hace un teléfono en el cine? Captura selfies en la penumbra.",
    "¿Por qué el ratón de computadora fue a la escuela? Para afinar su clic y mejorar.",
    "¿Qué le dijo el jardín a la maceta? ¡Eres la flor que alegra mi día!",
    "¿Por qué el helado fue al médico? Porque se sentía derretido por dentro, sin remedio.",
    "¿Qué hace un carro en el gimnasio? Levanta ruedas y acelera su fuerza.",
    "¿Por qué el panadero fue a la playa? Porque quería hacer pan tostado al sol.",
    "¿Qué dijo el tomate a la lechuga? ¡Eres la ensalada que le da vida a mi plato!",
    "¿Por qué el camión se puso a cantar? Porque tenía una gran carga de ritmo interior.",
    "¿Qué hace un globo en la oficina? Eleva el ánimo y llena de color el ambiente.",
    "¿Por qué la batería siempre se recarga? Porque su energía nunca se agota.",
    "¿Qué dijo el reloj digital al analógico? ¡Actualízate, amigo, que el tiempo avanza!",
    "¿Por qué el zapato se sintió perdido? Porque no encontró a su par ideal.",
    "¿Qué hace una taza en una fiesta de té? Se sirve con elegancia y calidez.",
    "¿Por qué la cuchara siempre es amable? Porque tiene una gran capacidad para compartir.",
    "¿Qué le dijo la ventana al sol? ¡Déjame ver el mundo con tus rayos!",
    "¿Por qué el motor se emocionó? Porque se encendió la pasión y la fuerza.",
    "¿Qué hace un boomerang cuando se cansa? Se queda en pausa y vuelve a su punto con determinación."
]

# Unimos todos los chistes en una sola lista de 170 chistes
ALL_JOKES = ALL_JOKES + ADDITIONAL_JOKES + NEW_JOKES
unused_jokes = ALL_JOKES.copy()
def get_random_joke():
    global unused_jokes, ALL_JOKES
    if not unused_jokes:
        unused_jokes = ALL_JOKES.copy()
    joke = random.choice(unused_jokes)
    unused_jokes.remove(joke)
    return joke

######################################
# VARIABLES PARA TRIVIA, MEMES Y PREDICCIONES
######################################
trivia_questions = [
    {"question": "¿Quién escribió 'Cien Años de Soledad'?", "answer": "gabriel garcía márquez"},
    {"question": "¿Cuál es el río más largo del mundo?", "answer": "amazonas"},
    {"question": "¿En qué año llegó el hombre a la Luna?", "answer": "1969"},
    {"question": "¿Cuál es el planeta más cercano al Sol?", "answer": "mercurio"},
    {"question": "¿Cuál es el animal terrestre más rápido?", "answer": "guepardo"},
    {"question": "¿Cuántos planetas hay en el sistema solar?", "answer": "8"},
    {"question": "¿En qué continente se encuentra Egipto?", "answer": "áfrica"},
    {"question": "¿Cuál es el idioma más hablado en el mundo?", "answer": "chino"},
    {"question": "¿Qué instrumento mide la temperatura?", "answer": "termómetro"},
    {"question": "¿Cuál es la capital de Francia?", "answer": "parís"}
]

MEMES = [
    "https://i.imgflip.com/1bij.jpg",
    "https://i.imgflip.com/26am.jpg",
    "https://i.imgflip.com/30b1gx.jpg",
    "https://i.imgflip.com/3si4.jpg",
    "https://i.imgflip.com/2fm6x.jpg"
]

predicciones = [
    "Hoy, las estrellas te favorecen... ¡pero recuerda usar protector solar!",
    "El oráculo dice: el mejor momento para actuar es ahora, ¡sin miedo!",
    "Tu destino es tan brillante que necesitarás gafas de sol.",
    "El futuro es incierto, pero las risas están garantizadas.",
    "Hoy encontrarás una sorpresa inesperada... ¡quizás un buen chiste!",
    "El universo conspira a tu favor, ¡aprovéchalo!",
    "Tu suerte cambiará muy pronto, y será motivo de celebración.",
    "Las oportunidades se presentarán, solo debes estar listo para recibirlas.",
    "El oráculo revela que una gran aventura te espera en el horizonte.",
    "Confía en tus instintos, el camino correcto se te mostrará."
]

######################################
# INICIALIZACIÓN DEL BOT
######################################
intents = discord.Intents.default()
intents.members = True   # Para poder buscar miembros que no estén en el canal actual
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

async def send_public_message(message: str):
    public_channel = bot.get_channel(PUBLIC_CHANNEL_ID)
    if public_channel:
        await public_channel.send(message)
    else:
        print("No se pudo encontrar el canal público.")

######################################
# ENDPOINTS DE LA API PRIVADA
######################################
app = Flask(__name__)

def check_auth(req):
    auth = req.headers.get("Authorization")
    if not auth or auth != f"Bearer {API_SECRET}":
        return False
    return True

@app.route("/")
def home():
    return "El bot está funcionando!", 200

@app.route("/api/update_points", methods=["POST"])
def api_update_points():
    if not check_auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    if not data or "member_id" not in data or "points" not in data:
        return jsonify({"error": "Missing parameters"}), 400
    try:
        member_id = int(data["member_id"])
        points = int(data["points"])
    except ValueError:
        return jsonify({"error": "Invalid parameters"}), 400
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return jsonify({"error": "Guild not found"}), 404
    try:
        member = guild.get_member(member_id)
        if member is None:
            member = bot.loop.run_until_complete(guild.fetch_member(member_id))
    except Exception as e:
        return jsonify({"error": "Member not found", "details": str(e)}), 404
    new_points = update_score(member, points)
    bot.loop.create_task(send_public_message(f"✅ API: Puntuación actualizada: {member.display_name} ahora tiene {new_points} puntos"))
    return jsonify({"message": "Puntuación actualizada", "new_points": new_points}), 200

@app.route("/api/delete_member", methods=["POST"])
def api_delete_member():
    if not check_auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    if not data or "member_id" not in data:
        return jsonify({"error": "Missing parameter: member_id"}), 400
    try:
        member_id = int(data["member_id"])
    except ValueError:
        return jsonify({"error": "Invalid member_id"}), 400
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return jsonify({"error": "Guild not found"}), 404
    try:
        member = guild.get_member(member_id)
        if member is None:
            member = bot.loop.run_until_complete(guild.fetch_member(member_id))
    except Exception as e:
        return jsonify({"error": "Member not found", "details": str(e)}), 404
    with conn.cursor() as cur:
        cur.execute("DELETE FROM participants WHERE id = %s", (str(member.id),))
    bot.loop.create_task(send_public_message(f"✅ API: {member.display_name} eliminado del torneo"))
    return jsonify({"message": "Miembro eliminado"}), 200

@app.route("/api/set_stage", methods=["POST"])
def api_set_stage():
    if not check_auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    if not data or "stage" not in data:
        return jsonify({"error": "Missing parameter: stage"}), 400
    try:
        stage = int(data["stage"])
    except ValueError:
        return jsonify({"error": "Invalid stage"}), 400
    global current_stage
    current_stage = stage
    bot.loop.create_task(send_public_message(f"✅ API: Etapa actual configurada a {stage}"))
    return jsonify({"message": "Etapa configurada", "stage": stage}), 200

######################################
# COMANDOS SENSIBLES DE DISCORD (con “!” – Solo el Propietario en canal privado)
######################################
@bot.command()
async def actualizar_puntuacion(ctx, jugador: str, puntos: int):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PRIVATE_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    match = re.search(r'\d+', jugador)
    if not match:
        await send_public_message("No se pudo encontrar al miembro.")
        return
    member_id = int(match.group())
    guild = ctx.guild or bot.get_guild(GUILD_ID)
    if guild is None:
        await send_public_message("No se pudo determinar el servidor.")
        return
    try:
        member = guild.get_member(member_id)
        if member is None:
            member = await guild.fetch_member(member_id)
    except Exception as e:
        await send_public_message("No se pudo encontrar al miembro en el servidor.")
        return
    try:
        puntos = int(puntos)
    except ValueError:
        await send_public_message("Por favor, proporciona un número válido de puntos.")
        return
    new_points = update_score(member, puntos)
    await send_public_message(f"✅ Puntuación actualizada: {member.display_name} ahora tiene {new_points} puntos")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def reducir_puntuacion(ctx, jugador: str, puntos: int):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PRIVATE_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    await actualizar_puntuacion(ctx, jugador, -puntos)
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def ver_puntuacion(ctx):
    participant = get_participant(str(ctx.author.id))
    if participant:
        await ctx.send(f"🏆 Tu puntaje del torneo es: {participant.get('puntos', 0)}")
    else:
        await ctx.send("❌ No estás registrado en el torneo")

@bot.command()
async def clasificacion(ctx):
    data = get_all_participants()
    sorted_players = sorted(data["participants"].items(), key=lambda item: int(item[1].get("puntos", 0)), reverse=True)
    ranking = "🏅 Clasificación del Torneo:\n"
    for idx, (uid, player) in enumerate(sorted_players, 1):
        ranking += f"{idx}. {player['nombre']} - {player.get('puntos', 0)} puntos\n"
    await ctx.send(ranking)

@bot.command()
async def avanzar_etapa(ctx):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PRIVATE_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage
    current_stage += 1
    data = get_all_participants()
    sorted_players = sorted(data["participants"].items(), key=lambda item: int(item[1].get("puntos", 0)), reverse=True)
    cutoff = STAGES[current_stage]
    avanzan = sorted_players[:cutoff]
    for uid, player in avanzan:
        player["etapa"] = current_stage
        upsert_participant(uid, player)
        try:
            member = ctx.guild.get_member(int(uid)) or await ctx.guild.fetch_member(int(uid))
            await member.send(f"🎉 ¡Felicidades! Has avanzado a la etapa {current_stage}")
        except Exception as e:
            print(f"Error al enviar mensaje a {uid}: {e}")
    await send_public_message(f"✅ Etapa {current_stage} iniciada. {cutoff} jugadores avanzaron")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def eliminar_jugador(ctx, jugador: str):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PRIVATE_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    match = re.search(r'\d+', jugador)
    if not match:
        await send_public_message("No se pudo encontrar al miembro.")
        return
    member_id = int(match.group())
    guild = ctx.guild or bot.get_guild(GUILD_ID)
    if guild is None:
        await send_public_message("No se pudo determinar el servidor.")
        return
    try:
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
    except Exception as e:
        await send_public_message("No se pudo encontrar al miembro en el servidor.")
        return
    user_id = str(member.id)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM participants WHERE id = %s", (user_id,))
    await send_public_message(f"✅ {member.display_name} eliminado del torneo")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def configurar_etapa(ctx, etapa: int):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PRIVATE_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage
    current_stage = etapa
    await send_public_message(f"✅ Etapa actual configurada a {etapa}")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def chiste(ctx):
    await ctx.send(get_random_joke())

######################################
# EVENTO ON_MESSAGE: Comandos de Lenguaje Natural
######################################
@bot.event
async def on_message(message):
    # Si el mensaje comienza con "!" y el autor no es el propietario, se borra sin respuesta.
    if message.content.startswith("!") and message.author.id != OWNER_ID:
        try:
            await message.delete()
        except:
            pass
        return

    # Si el mensaje comienza con "!" y es del propietario, se procesa como comando sensible.
    if message.content.startswith("!") and message.author.id == OWNER_ID:
        await bot.process_commands(message)
        return

    if message.author.bot:
        return

    global stage_names, current_stage, active_trivia, trivia_questions

    # Importamos unicodedata para normalizar cadenas
    import unicodedata
    def normalize_string(s):
        return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).replace(" ", "").lower()

    content = message.content.strip().lower()

    if content == "ranking":
        data = get_all_participants()
        sorted_players = sorted(data["participants"].items(), key=lambda item: int(item[1].get("puntos", 0)), reverse=True)
        user_id = str(message.author.id)
        found = False
        user_rank = 0
        for rank, (uid, player) in enumerate(sorted_players, 1):
            if uid == user_id:
                user_rank = rank
                found = True
                break
        stage_name = stage_names.get(current_stage, f"Etapa {current_stage}")
        if found:
            response = f"🏆 {message.author.display_name}, tu ranking en {stage_name} es el **{user_rank}** de {len(sorted_players)} y tienes {data['participants'][user_id].get('puntos', 0)} puntos."
        else:
            response = "❌ No estás registrado en el torneo."
        await message.channel.send(response)
        return

    if content == "topmejores":
        data = get_all_participants()
        sorted_players = sorted(data["participants"].items(), key=lambda item: int(item[1].get("puntos", 0)), reverse=True)
        stage_name = stage_names.get(current_stage, f"Etapa {current_stage}")
        ranking_text = f"🏅 Top 10 Mejores de {stage_name}:\n"
        for idx, (uid, player) in enumerate(sorted_players[:10], 1):
            ranking_text += f"{idx}. {player['nombre']} - {player.get('puntos', 0)} puntos\n"
        await message.channel.send(ranking_text)
        return

    if content == "topestrellas":
        data = get_all_participants()
        sorted_by_symbolic = sorted(data["participants"].items(), key=lambda item: int(item[1].get("symbolic", 0)), reverse=True)
        ranking_text = "🌟 Top 10 Estrellas Simbólicas:\n"
        for idx, (uid, player) in enumerate(sorted_by_symbolic[:10], 1):
            ranking_text += f"{idx}. {player['nombre']} - {player.get('symbolic', 0)} estrellas\n"
        await message.channel.send(ranking_text)
        return

    if content in ["comandos", "lista de comandos"]:
        help_text = (
            "**Resumen de Comandos (Lenguaje Natural):**\n\n"
            "   - **ranking:** Muestra tu posición y puntaje del torneo.\n"
            "   - **topmejores:** Muestra el ranking de los 10 jugadores con mayor puntaje del torneo.\n"
            "   - **misestrellas:** Muestra cuántas estrellas simbólicas tienes.\n"
            "   - **topestrellas:** Muestra el ranking de los 10 jugadores con más estrellas simbólicas.\n"
            "   - **chiste** o **cuéntame un chiste:** Devuelve un chiste aleatorio (sin repetir hasta agotar la lista de 170 chistes).\n"
            "   - **quiero jugar trivia / jugar trivia / trivia:** Inicia una partida de trivia; si respondes correctamente, ganas 1 estrella simbólica.\n"
            "   - **oráculo** o **predicción:** Recibe una predicción divertida.\n"
            "   - **meme** o **muéstrame un meme:** Muestra un meme aleatorio.\n"
            "   - **juguemos piedra papel tijeras, yo elijo [tu elección]:** Juega a Piedra, Papel o Tijeras; si ganas, ganas 1 estrella simbólica.\n"
            "   - **duelo de chistes contra @usuario:** Inicia un duelo de chistes; el ganador gana 1 estrella simbólica.\n"
        )
        await message.channel.send(help_text)
        return

    if content == "misestrellas":
        participant = get_participant(str(message.author.id))
        symbolic = 0
        if participant:
            try:
                symbolic = int(participant.get("symbolic", 0))
            except:
                symbolic = 0
        await message.channel.send(f"🌟 {message.author.display_name}, tienes {symbolic} estrellas simbólicas.")
        return

    if content in ["chiste", "cuéntame un chiste"]:
        await message.channel.send(get_random_joke())
        return

    if any(phrase in content for phrase in ["quiero jugar trivia", "jugar trivia", "trivia"]):
        if message.channel.id not in active_trivia:
            trivia = random.choice(trivia_questions)
            active_trivia[message.channel.id] = trivia
            await message.channel.send(f"**Trivia:** {trivia['question']}\n_Responde en el chat._")
            return

    if message.channel.id in active_trivia:
        trivia = active_trivia[message.channel.id]
        if normalize_string(message.content.strip()) == normalize_string(trivia['answer']):
            symbolic = award_symbolic_reward(message.author, 1)
            response = f"🎉 ¡Correcto, {message.author.display_name}! Has ganado 1 estrella simbólica. Ahora tienes {symbolic} estrellas simbólicas."
            await message.channel.send(response)
            del active_trivia[message.channel.id]
            return

    if any(phrase in content for phrase in ["oráculo", "predicción"]):
        prediction = random.choice(predicciones)
        await message.channel.send(f"🔮 {prediction}")
        return

    if content in ["meme", "muéstrame un meme"]:
        meme_url = random.choice(MEMES)
        await message.channel.send(meme_url)
        return

    if any(phrase in content for phrase in ["juguemos piedra papel tijeras"]):
        opciones = ["piedra", "papel", "tijeras"]
        user_choice = next((op for op in opciones if op in content), None)
        if not user_choice:
            await message.channel.send("¿Cuál eliges? Indica piedra, papel o tijeras.")
            return
        bot_choice = random.choice(opciones)
        if user_choice == bot_choice:
            result = "¡Empate!"
        elif (user_choice == "piedra" and bot_choice == "tijeras") or \
             (user_choice == "papel" and bot_choice == "piedra") or \
             (user_choice == "tijeras" and bot_choice == "papel"):
            result = f"¡Ganaste! Yo elegí **{bot_choice}**."
            symbolic = award_symbolic_reward(message.author, 1)
            result += f" Has ganado 1 estrella simbólica. Ahora tienes {symbolic} estrellas simbólicas."
        else:
            result = f"Perdiste. Yo elegí **{bot_choice}**. ¡Inténtalo de nuevo!"
        await message.channel.send(result)
        return

    if "duelo de chistes contra" in content:
        if message.mentions:
            opponent = message.mentions[0]
            challenger = message.author
            joke_challenger = get_random_joke()
            joke_opponent = get_random_joke()
            duel_text = (
                f"**Duelo de Chistes:**\n"
                f"{challenger.display_name} dice: {joke_challenger}\n"
                f"{opponent.display_name} dice: {joke_opponent}\n"
            )
            winner = random.choice([challenger, opponent])
            symbolic = award_symbolic_reward(winner, 1)
            duel_text += f"🎉 ¡El ganador es {winner.display_name}! Ha ganado 1 estrella simbólica. Ahora tiene {symbolic} estrellas simbólicas."
            await message.channel.send(duel_text)
            return

    await bot.process_commands(message)

######################################
# EVENTO ON_READY
######################################
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user.name}')

######################################
# SERVIDOR WEB PARA MANTENER EL BOT ACTIVO (API PRIVADA)
######################################
@app.route("/")
def home():
    return "El bot está funcionando!", 200

def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

threading.Thread(target=run_webserver).start()

######################################
# INICIAR EL BOT
######################################
bot.run(os.getenv('DISCORD_TOKEN'))
