import discord
import psycopg2
import psycopg2.extras
from discord.ext import commands
import json
import random
import os
import re
import threading
from flask import Flask

######################################
# CONFIGURACIÓN: IDs y Servidor
######################################
OWNER_ID = 1336609089656197171         # Tu Discord ID (único autorizado para comandos sensibles)
CHANNEL_ID = 1338126297666424874         # Canal donde se publican los resultados y se ejecutan los comandos
GUILD_ID = 1337387112403697694            # ID de tu servidor (guild)

######################################
# CONEXIÓN A LA BASE DE DATOS POSTGRESQL
######################################
DATABASE_URL = os.environ.get("DATABASE_URL")  # Configurada en Render
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
                eliminado BOOLEAN DEFAULT FALSE,
                logros JSONB DEFAULT '[]'
            )
        """)
init_db()

######################################
# CONFIGURACIÓN DEL TORNEO: Etapas y Nombres
######################################
STAGES = {1: 60, 2: 48, 3: 32, 4: 24, 5: 14}  # Máximo de jugadores que avanzan en cada etapa
stage_names = {
    1: "Battle Royale",
    2: "Snipers vs Runners",
    3: "Boxfight duos",
    4: "Pescadito dice",
    5: "Gran Final"
}
current_stage = 1  # Etapa inicial

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
            INSERT INTO participants (id, nombre, puntos, symbolic, etapa, eliminado, logros)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                puntos = EXCLUDED.puntos,
                symbolic = EXCLUDED.symbolic,
                etapa = EXCLUDED.etapa,
                eliminado = EXCLUDED.eliminado,
                logros = EXCLUDED.logros
        """, (
            user_id,
            participant["nombre"],
            participant.get("puntos", 0),
            participant.get("symbolic", 0),
            participant.get("etapa", current_stage),
            participant.get("eliminado", False),
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
            "eliminado": False,
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
            "eliminado": False,
            "logros": []
        }
    current_symbolic = int(participant.get("symbolic", 0))
    new_symbolic = current_symbolic + reward
    participant["symbolic"] = new_symbolic
    upsert_participant(user_id, participant)
    return new_symbolic

######################################
# CHISTES (170 chistes)
######################################
# Generamos la lista de 170 chistes (puedes reemplazar estos con tus chistes reales)
ALL_JOKES = [f"Chiste {i}" for i in range(1, 171)]
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
    {"question": "¿Cuál es el río más largo del mundo?", "answer": "amazonas"},
    {"question": "¿En qué año llegó el hombre a la Luna?", "answer": "1969"},
    {"question": "¿Cuál es el planeta más cercano al Sol?", "answer": "mercurio"},
    {"question": "¿Quién escribió 'Cien Años de Soledad'?", "answer": "gabriel garcía márquez"},
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
intents.members = True   # Para acceder a todos los miembros del servidor
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def send_public_message(message: str):
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(message)
    else:
        print("No se pudo encontrar el canal público.")

######################################
# COMANDOS SENSIBLES (Con "!" – Solo el propietario, en cualquier canal)
######################################
@bot.command(name="mas_puntos")
async def mas_puntos(ctx, jugador: str, puntos: int):
    if ctx.author.id != OWNER_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    match = re.search(r'\d+', jugador)
    if not match:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    member_id = int(match.group())
    guild = ctx.guild or bot.get_guild(GUILD_ID)
    if guild is None:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    try:
        member = guild.get_member(member_id)
        if member is None:
            member = await guild.fetch_member(member_id)
    except Exception:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    try:
        puntos = int(puntos)
    except ValueError:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    new_points = update_score(member, puntos)
    await send_public_message(f"✅ {member.display_name} ahora tiene {new_points} puntos")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command(name="menos_puntos")
async def menos_puntos(ctx, jugador: str, puntos: int):
    await mas_puntos(ctx, jugador, -puntos)
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def avanzar_etapa(ctx):
    if ctx.author.id != OWNER_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage
    new_stage = current_stage + 1
    required = STAGES.get(new_stage)
    if not required:
        await send_public_message("No existe una etapa siguiente definida.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    data = get_all_participants()
    active_players = []
    for uid, player in data["participants"].items():
        if (player.get("etapa", 1) == current_stage) and (not player.get("eliminado", False)):
            active_players.append((uid, player))
    sorted_players = sorted(active_players, key=lambda x: int(x[1].get("puntos", 0)), reverse=True)
    advancing = sorted_players[:required]
    eliminated = sorted_players[required:]
    for uid, player in advancing:
        player["etapa"] = new_stage
        player["eliminado"] = False
        upsert_participant(uid, player)
        try:
            member = ctx.guild.get_member(int(uid)) or await ctx.guild.fetch_member(int(uid))
            await member.send(f"🎉 ¡Felicitaciones! Has avanzado a {stage_names[new_stage]}!")
        except Exception as e:
            print(f"Error enviando DM a {uid}: {e}")
    for uid, player in eliminated:
        player["eliminado"] = True
        upsert_participant(uid, player)
        try:
            member = ctx.guild.get_member(int(uid)) or await ctx.guild.fetch_member(int(uid))
            await member.send(f"😢 Lo siento, has sido eliminado del torneo en {stage_names[new_stage]}.")
        except Exception as e:
            print(f"Error enviando DM a {uid}: {e}")
    current_stage = new_stage
    await send_public_message(f"✅ Ahora estamos en {stage_names[new_stage]}.")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def regresar_etapa(ctx):
    if ctx.author.id != OWNER_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage
    if current_stage == 1:
        await send_public_message("Ya estás en la etapa 1. No se puede retroceder más.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    new_stage = current_stage - 1
    data = get_all_participants()
    for uid, player in data["participants"].items():
        if player.get("etapa", 1) > new_stage:
            player["etapa"] = new_stage
            player["eliminado"] = False
            upsert_participant(uid, player)
    current_stage = new_stage
    await send_public_message(f"✅ Se ha retrocedido a {stage_names[new_stage]}.")
    try:
        await ctx.message.delete()
    except:
        pass

######################################
# EVENTO ON_MESSAGE: Procesa comandos de lenguaje natural
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
    # Si el mensaje comienza con "!" y es del propietario, lo dejamos que se procese como comando
    if message.content.startswith("!") and message.author.id == OWNER_ID:
        await bot.process_commands(message)
        return

    # Procesa mensajes que NO comienzan con "!" (comandos de lenguaje natural)
    if message.author.bot:
        return
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
    if content in ["comandos", "lista de comandos"]:
        help_text = (
            "**Resumen de Comandos (Lenguaje Natural):**\n\n"
            "   - **ranking:** Muestra tu posición y puntaje individual (y si has sido eliminado).\n"
            "   - **topmejores:** Muestra el Top 10 Mejores de la etapa actual.\n"
            "   - **chiste** o **cuéntame un chiste:** Devuelve un chiste aleatorio.\n"
            "   - **quiero jugar trivia / jugar trivia / trivia:** Inicia una partida de trivia.\n"
            "   - **oráculo** o **predicción:** Recibe una predicción divertida.\n"
            "   - **meme** o **muéstrame un meme:** Muestra un meme aleatorio.\n"
            "   - **juguemos piedra papel tijeras, yo elijo [tu elección]:** Juega a Piedra, Papel o Tijeras.\n"
            "   - **duelo de chistes contra @usuario:** Inicia un duelo de chistes.\n"
        )
        await message.channel.send(help_text)
        return
    # Eliminamos el comando "chiste" duplicado: lo manejamos aquí en lenguaje natural
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
        if message.content.strip().lower() == trivia['answer'].lower():
            symbolic = award_symbolic_reward(message.author, 1)
            response = f"🎉 ¡Correcto, {message.author.display_name}! Has ganado 1 estrella simbólica. Ahora tienes {symbolic} estrellas."
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
            result += f" Ahora tienes {symbolic} estrellas."
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
            duel_text += f"🎉 ¡El ganador es {winner.display_name}! Ahora tiene {symbolic} estrellas."
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
# SERVIDOR WEB MÍNIMO (para que Render detecte un puerto abierto)
######################################
app = Flask(__name__)

@app.route("/")
def home():
    return "El bot está funcionando!"

def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# Inicia el servidor Flask en un hilo separado.
threading.Thread(target=run_webserver).start()

######################################
# INICIAR EL BOT
######################################
bot.run(os.getenv('DISCORD_TOKEN'))
