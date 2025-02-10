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
# NORMALIZACIÓN DE CADENAS (para respuestas sin tildes, espacios, etc.)
######################################
def normalize_string(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).replace(" ", "").lower()

######################################
# CHISTES: 170 chistes (70 originales + 50 adicionales + 50 nuevos)
######################################
# (A continuación se muestran ejemplos; reemplaza o amplía para llegar a 170 chistes completos)
ALL_JOKES = [
    # Bloque 1: 70 chistes originales
    "¿Qué hace una abeja en el gimnasio? ¡Zum-ba!",
    "¿Por qué los pájaros no usan Facebook? Porque ya tienen Twitter.",
    "¿Qué le dijo un semáforo a otro? No me mires, me estoy cambiando.",
    "¿Por qué el libro de matemáticas se sentía triste? Porque tenía demasiados problemas.",
    "¿Qué hace una taza en la escuela? Toma té!",
    "¿Cómo se despiden los químicos? Ácido un placer.",
    # ... Agrega 64 chistes más para este bloque ...
    
    # Bloque 2: 50 chistes adicionales
    "¿Por qué el ordenador fue al psicólogo? Porque tenía demasiadas ventanas abiertas.",
    "¿Qué hace un gato en la computadora? Busca ratones.",
    # ... Agrega 48 chistes más para este bloque ...

    # Bloque 3: 50 chistes nuevos (los mejores que jamás he creado)
    "¿Por qué el reloj se fue al gimnasio? Porque quería marcar ritmo.",
    "¿Qué hace un pez en el ordenador? Nada en la red.",
    # ... Agrega 48 chistes más para este bloque ...
]
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

    global stage_names, current_stage, active_trivia

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
        # Normalizamos ambas cadenas para comparar sin acentos ni espacios
        from unicodedata import normalize
        def normalize_string(s):
            return ''.join(c for c in normalize('NFKD', s) if not unicodedata.combining(c)).replace(" ", "").lower()
        # Usamos nuestra función; si no está definida, se define aquí
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

    # No llamamos a bot.process_commands(message) al final para evitar duplicados

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
