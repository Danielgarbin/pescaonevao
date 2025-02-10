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
import asyncio  # Para usar asyncio.sleep
import datetime  # Para gestionar fechas y tiempos
from flask import Flask, request, jsonify

######################################
# CONFIGURACIÓN: IDs y Servidor
######################################
OWNER_ID = 1336609089656197171         # Tu Discord ID (único autorizado para comandos sensibles)
PRIVATE_CHANNEL_ID = 1338130641354620988  # Canal privado para comandos sensibles (no se utiliza en la versión final)
PUBLIC_CHANNEL_ID  = 1338126297666424874  # Canal público donde se muestran resultados sensibles
SPECIAL_HELP_CHANNEL = 1338608387197243422  # Canal especial para que el owner reciba la lista extendida de comandos
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jokes (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trivias (
                id SERIAL PRIMARY KEY,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                hint TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memes (
                id SERIAL PRIMARY KEY,
                url TEXT NOT NULL
            )
        """)
init_db()

######################################
# CONFIGURACIÓN INICIAL DEL TORNEO
######################################
PREFIX = '!'
# Configuración de etapas: cada etapa tiene un número determinado de jugadores.
# Se agregan las etapas 7 y 8. (Recordá: ahora la etapa 7 se llamará "FALTA ESCOGER OBJETOS" y la etapa 8 "FIN")
STAGES = {1: 60, 2: 48, 3: 32, 4: 24, 5: 14, 6: 1, 7: 1, 8: 1}
current_stage = 1
stage_names = {
    1: "Battle Royale",
    2: "Snipers vs Runners",
    3: "Boxfight duos",
    4: "Pescadito dice",
    5: "Gran Final",
    6: "CAMPEON",
    7: "FALTA ESCOGER OBJETOS",
    8: "FIN"
}

# Variables para gestionar el reenvío de mensajes del campeón
champion_id = None
forwarding_enabled = False
forwarding_end_time = None

######################################
# VARIABLE GLOBAL PARA TRIVIA
######################################
active_trivia = {}  # key: channel.id, value: {"question": ..., "answer": ..., "hint": ...}

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
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).replace(" ", "").lower()

######################################
# FUNCIONES PARA CHISTES, TRIVIAS Y MEMES (USANDO LA BASE DE DATOS)
######################################
def get_random_joke():
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT content FROM jokes ORDER BY random() LIMIT 1")
        result = cur.fetchone()
        if result:
            return result["content"]
        else:
            return "No hay chistes disponibles en este momento."

def get_random_trivia():
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT question, answer, hint FROM trivias ORDER BY random() LIMIT 1")
        result = cur.fetchone()
        if result:
            return result
        else:
            return {"question": "No hay trivias disponibles en este momento.", "answer": "", "hint": ""}

def get_random_meme():
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT url FROM memes ORDER BY random() LIMIT 1")
        result = cur.fetchone()
        if result:
            return result["url"]
        else:
            return "No hay memes disponibles en este momento."

######################################
# INICIALIZACIÓN DEL BOT
######################################
intents = discord.Intents.default()
intents.members = True
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

@app.route("/", methods=["GET"])
def home_page():
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
    global current_stage, champion_id, forwarding_enabled, forwarding_end_time
    current_stage = stage
    # Si la nueva etapa no es 6, 7 ni 8 se desactivan los reenvíos
    if current_stage not in [6,7,8]:
        champion_id = None
        forwarding_enabled = False
        forwarding_end_time = None
    bot.loop.create_task(send_public_message(f"✅ API: Etapa actual configurada a {stage}"))
    return jsonify({"message": "Etapa configurada", "stage": stage}), 200

######################################
# COMANDOS SENSIBLES DE DISCORD (con “!” – Solo el Propietario en el canal autorizado)
######################################
@bot.command()
async def actualizar_puntuacion(ctx, jugador: str, puntos: int):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    match = re.search(r'\d+', jugador)
    if not match:
        await send_public_message("No se pudo encontrar al miembro.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    member_id = int(match.group())
    guild = ctx.guild or bot.get_guild(GUILD_ID)
    if guild is None:
        await send_public_message("No se pudo determinar el servidor.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    try:
        member = guild.get_member(member_id)
        if member is None:
            member = await guild.fetch_member(member_id)
    except Exception as e:
        await send_public_message("No se pudo encontrar al miembro en el servidor.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    try:
        puntos = int(puntos)
    except ValueError:
        await send_public_message("Por favor, proporciona un número válido de puntos.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    new_points = update_score(member, puntos)
    await send_public_message(f"✅ Puntuación actualizada: {member.display_name} ahora tiene {new_points} puntos")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def reducir_puntuacion(ctx, jugador: str, puntos: int):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
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
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage, champion_id, forwarding_enabled, forwarding_end_time
    current_stage += 1
    data = get_all_participants()
    sorted_players = sorted(data["participants"].items(), key=lambda item: int(item[1].get("puntos", 0)), reverse=True)
    cutoff = STAGES.get(current_stage)
    if cutoff is None:
        await send_public_message("No hay configuración para esta etapa.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    avanzan = sorted_players[:cutoff]
    eliminados = sorted_players[cutoff:]
    for uid, player in avanzan:
        player["etapa"] = current_stage
        upsert_participant(uid, player)
        try:
            member = ctx.guild.get_member(int(uid)) or await ctx.guild.fetch_member(int(uid))
            if current_stage == 6:
                msg = (f"🏆 ¡Enhorabuena {member.display_name}! Has sido coronado como el CAMPEON del torneo. "
                       f"Además, has ganado 2800 paVos, que serán entregados en forma de regalos de la tienda de objetos de Fortnite. "
                       f"Puedes escoger los objetos que desees de la tienda, siempre que el valor total de ellos sume 2800. "
                       f"Por favor, escribe en este chat el nombre de los objetos que has escogido (tal como aparecen en la tienda de objetos de Fortnite).")
                champion_id = member.id
                forwarding_enabled = True
                forwarding_end_time = None
            elif current_stage == 7:
                msg = f"❗ Aún te faltan escoger objetos. Por favor, escribe tus objetos escogidos. 😕"
                champion_id = member.id
                forwarding_enabled = True
                forwarding_end_time = None
            elif current_stage == 8:
                msg = f"✅ Tus objetos han sido entregados, muchas gracias por participar, nos vemos pronto. 🙌"
                champion_id = member.id
                forwarding_enabled = True
                forwarding_end_time = datetime.datetime.utcnow() + datetime.timedelta(days=2)
            else:
                msg = f"🎉 ¡Felicidades! Has avanzado a la etapa {current_stage} ({stage_names.get(current_stage, 'Etapa ' + str(current_stage))})."
                champion_id = None
                forwarding_enabled = False
                forwarding_end_time = None
            await member.send(msg)
            await asyncio.sleep(1)  # Pausa para evitar demasiadas solicitudes en poco tiempo
        except Exception as e:
            print(f"Error al enviar mensaje a {uid}: {e}")
    for uid, player in eliminados:
        try:
            member = ctx.guild.get_member(int(uid)) or await ctx.guild.fetch_member(int(uid))
            await member.send(f"❌ Lo siento, has sido eliminado del torneo en la etapa {current_stage - 1}.")
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Error al enviar mensaje a {uid}: {e}")
    await send_public_message(f"✅ Etapa {current_stage} iniciada. {cutoff} jugadores avanzaron y {len(eliminados)} fueron eliminados.")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def retroceder_etapa(ctx):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage, champion_id, forwarding_enabled, forwarding_end_time
    if current_stage <= 1:
        await send_public_message("No se puede retroceder de la etapa 1.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    current_stage -= 1
    data = get_all_participants()
    for uid, player in data["participants"].items():
        player["etapa"] = current_stage
        upsert_participant(uid, player)
    # Si la nueva etapa NO es 6, 7 ni 8, se desactivan los reenvíos
    if current_stage not in [6,7,8]:
        champion_id = None
        forwarding_enabled = False
        forwarding_end_time = None
    await send_public_message(f"✅ Etapa retrocedida. Ahora la etapa es {current_stage} ({stage_names.get(current_stage, 'Etapa ' + str(current_stage))}).")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def eliminar_jugador(ctx, jugador: str):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    match = re.search(r'\d+', jugador)
    if not match:
        await send_public_message("No se pudo encontrar al miembro.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    member_id = int(match.group())
    guild = ctx.guild or bot.get_guild(GUILD_ID)
    if guild is None:
        await send_public_message("No se pudo determinar el servidor.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    try:
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
    except Exception as e:
        await send_public_message("No se pudo encontrar al miembro en el servidor.")
        try:
            await ctx.message.delete()
        except:
            pass
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
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage, champion_id, forwarding_enabled, forwarding_end_time
    current_stage = etapa
    # Si la nueva etapa no es 6, 7 ni 8 se desactivan los reenvíos
    if current_stage not in [6,7,8]:
        champion_id = None
        forwarding_enabled = False
        forwarding_end_time = None
    await send_public_message(f"✅ Etapa actual configurada a {etapa}")
    try:
        await ctx.message.delete()
    except:
        pass

# Nuevo comando para saltar a la etapa deseada
@bot.command()
async def saltar_etapa(ctx, etapa: int):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage, champion_id, forwarding_enabled, forwarding_end_time
    current_stage = etapa
    data = get_all_participants()
    sorted_players = sorted(data["participants"].items(), key=lambda item: int(item[1].get("puntos", 0)), reverse=True)
    if sorted_players:
        champ_uid, champ_player = sorted_players[0]
        try:
            guild = ctx.guild or bot.get_guild(GUILD_ID)
            champion = guild.get_member(int(champ_uid)) or await guild.fetch_member(int(champ_uid))
        except Exception as e:
            champion = None
        if champion:
            if current_stage == 6:
                msg = (f"🏆 ¡Enhorabuena {champion.display_name}! Has sido coronado como el CAMPEON del torneo. "
                       f"Además, has ganado 2800 paVos, que serán entregados en forma de regalos de la tienda de objetos de Fortnite. "
                       f"Puedes escoger los objetos que desees de la tienda, siempre que el valor total de ellos sume 2800. "
                       f"Por favor, escribe en este chat el nombre de los objetos que has escogido (tal como aparecen en la tienda de objetos de Fortnite).")
                champion_id = champion.id
                forwarding_enabled = True
                forwarding_end_time = None
                await champion.send(msg)
            elif current_stage == 7:
                msg = f"❗ Aún te faltan escoger objetos. Por favor, escribe tus objetos escogidos. 😕"
                champion_id = champion.id
                forwarding_enabled = True
                forwarding_end_time = None
                await champion.send(msg)
            elif current_stage == 8:
                msg = f"✅ Tus objetos han sido entregados, muchas gracias por participar, nos vemos pronto. 🙌"
                champion_id = champion.id
                forwarding_enabled = True
                forwarding_end_time = datetime.datetime.utcnow() + datetime.timedelta(days=2)
                await champion.send(msg)
            else:
                champion_id = None
                forwarding_enabled = False
                forwarding_end_time = None
    await send_public_message(f"✅ Etapa saltada. Ahora la etapa es {current_stage} ({stage_names.get(current_stage, 'Etapa ' + str(current_stage))}).")
    try:
        await ctx.message.delete()
    except:
        pass

######################################
# COMANDO !trivia (disponible para el owner; los demás inician trivia por lenguaje natural)
######################################
@bot.command()
async def trivia(ctx):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    if ctx.channel.id in active_trivia:
        del active_trivia[ctx.channel.id]
    trivia_item = get_random_trivia()
    active_trivia[ctx.channel.id] = trivia_item
    await ctx.send(f"**Trivia:** {trivia_item['question']}\n_Responde en el chat._")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def chiste(ctx):
    await ctx.send(get_random_joke())

######################################
# NUEVOS COMANDOS ADMIN PARA GESTIÓN DE CHISTES Y TRIVIAS
######################################
@bot.command()
async def agregar_chiste(ctx, *, chiste_text: str):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    with conn.cursor() as cur:
        cur.execute("INSERT INTO jokes (content) VALUES (%s) RETURNING id", (chiste_text,))
        joke_id = cur.fetchone()[0]
    await send_public_message(f"✅ Chiste agregado con ID {joke_id}.")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def eliminar_chiste(ctx, joke_id: int):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM jokes WHERE id = %s", (joke_id,))
        if cur.rowcount > 0:
            await send_public_message(f"✅ Chiste con ID {joke_id} eliminado.")
        else:
            await send_public_message(f"❌ No se encontró un chiste con ID {joke_id}.")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def agregar_chistes_masivos(ctx, *, chistes_text: str):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    chistes = [line.strip() for line in chistes_text.split("\n") if line.strip()]
    if not chistes:
        await send_public_message("❌ No se encontraron chistes para agregar.")
        return
    with conn.cursor() as cur:
        for chiste in chistes:
            cur.execute("INSERT INTO jokes (content) VALUES (%s)", (chiste,))
    await send_public_message(f"✅ Se agregaron {len(chistes)} chistes.")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def agregar_trivia(ctx, *, trivia_data: str):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    parts = [part.strip() for part in trivia_data.split("|")]
    if len(parts) < 2:
        await send_public_message("❌ Formato incorrecto. Usa: pregunta | respuesta | [pista]")
        return
    question = parts[0]
    answer = parts[1]
    hint = parts[2] if len(parts) >= 3 else ""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO trivias (question, answer, hint) VALUES (%s, %s, %s) RETURNING id", (question, answer, hint))
        trivia_id = cur.fetchone()[0]
    await send_public_message(f"✅ Trivia agregada con ID {trivia_id}.")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def eliminar_trivia(ctx, trivia_id: int):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM trivias WHERE id = %s", (trivia_id,))
        if cur.rowcount > 0:
            await send_public_message(f"✅ Trivia con ID {trivia_id} eliminada.")
        else:
            await send_public_message(f"❌ No se encontró una trivia con ID {trivia_id}.")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def agregar_trivias_masivas(ctx, *, trivias_text: str):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    lines = [line.strip() for line in trivias_text.split("\n") if line.strip()]
    count = 0
    with conn.cursor() as cur:
        for line in lines:
            parts = [part.strip() for part in line.split("|")]
            if len(parts) < 2:
                continue
            question = parts[0]
            answer = parts[1]
            hint = parts[2] if len(parts) >= 3 else ""
            cur.execute("INSERT INTO trivias (question, answer, hint) VALUES (%s, %s, %s)", (question, answer, hint))
            count += 1
    await send_public_message(f"✅ Se agregaron {count} trivias.")
    try:
        await ctx.message.delete()
    except:
        pass

######################################
# EVENTO ON_MESSAGE: Comandos de Lenguaje Natural y reenvío de DMs del campeón
######################################
@bot.event
async def on_message(message):
    # Si el mensaje proviene de un DM y es del campeón y estamos en etapa 6, 7 o 8, se reenvía al canal 1338610365327474690
    if message.guild is None and champion_id is not None and message.author.id == champion_id and forwarding_enabled:
        if forwarding_end_time is not None and datetime.datetime.utcnow() > forwarding_end_time:
            global forwarding_enabled
            forwarding_enabled = False
        else:
            try:
                forward_channel = bot.get_channel(1338610365327474690)
                if forward_channel:
                    await forward_channel.send(f"**Mensaje del Campeón:** {message.content}")
            except Exception as e:
                print(f"Error forwarding message: {e}")
    # Procesa los comandos en mensajes que comiencen con "!" según la lógica existente
    if message.content.startswith("!") and message.author.id != OWNER_ID:
        try:
            await message.delete()
        except:
            pass
        return

    if message.content.startswith("!") and message.author.id == OWNER_ID:
        await bot.process_commands(message)
        return

    if message.author.bot:
        return

    global stage_names, current_stage, active_trivia

    def normalize_string_local(s):
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
            "   - **chiste** o **cuéntame un chiste:** Devuelve un chiste aleatorio.\n"
            "   - **quiero jugar trivia / jugar trivia / trivia:** Inicia una partida de trivia; si respondes correctamente, ganas 1 estrella simbólica.\n"
            "   - **oráculo** o **predicción:** Recibe una predicción divertida.\n"
            "   - **meme** o **muéstrame un meme:** Muestra un meme aleatorio.\n"
            "   - **juguemos piedra papel tijeras, yo elijo [tu elección]:** Juega a Piedra, Papel o Tijeras; si ganas, ganas 1 estrella simbólica.\n"
            "   - **duelo de chistes contra @usuario:** Inicia un duelo de chistes; el ganador gana 1 estrella simbólica.\n"
        )
        # Ahora, si el autor es el OWNER_ID, se agregan también los comandos sensibles.
        if message.author.id == OWNER_ID:
            help_text += "\n**Comandos Sensibles (!):**\n"
            help_text += (
                "   - **!actualizar_puntuacion [jugador] [puntos]:** Actualiza la puntuación de un jugador.\n"
                "   - **!reducir_puntuacion [jugador] [puntos]:** Resta puntos a un jugador.\n"
                "   - **!ver_puntuacion:** Muestra tu puntaje actual del torneo.\n"
                "   - **!clasificacion:** Muestra la clasificación completa del torneo.\n"
                "   - **!avanzar_etapa:** Avanza a la siguiente etapa del torneo y notifica a los jugadores.\n"
                "   - **!retroceder_etapa:** Retrocede a la etapa anterior del torneo.\n"
                "   - **!eliminar_jugador [jugador]:** Elimina a un jugador del torneo.\n"
                "   - **!configurar_etapa [etapa]:** Configura manualmente la etapa actual del torneo.\n"
                "   - **!saltar_etapa [etapa]:** Salta directamente a la etapa indicada.\n"
                "   - **!agregar_chiste [chiste]:** Agrega un chiste a la base de datos.\n"
                "   - **!eliminar_chiste [id]:** Elimina un chiste de la base de datos por su ID.\n"
                "   - **!agregar_chistes_masivos [lista de chistes]:** Agrega múltiples chistes (cada chiste en una nueva línea).\n"
                "   - **!agregar_trivia [pregunta] | [respuesta] | [pista]:** Agrega una trivia a la base de datos. La pista es opcional.\n"
                "   - **!eliminar_trivia [id]:** Elimina una trivia de la base de datos por su ID.\n"
                "   - **!agregar_trivias_masivas [lista de trivias]:** Agrega múltiples trivias (cada línea en formato: pregunta | respuesta | [pista]).\n"
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

    # --- MODIFICACIÓN PARA TRIVIA ---
    if any(phrase in content for phrase in ["quiero jugar trivia", "jugar trivia", "trivia"]):
        trivia_item = get_random_trivia()
        active_trivia[message.channel.id] = trivia_item
        await message.channel.send(f"**Trivia:** {trivia_item['question']}\n_Responde en el chat._")
        return
    # ---------------------------------

    if message.channel.id in active_trivia:
        trivia_item = active_trivia[message.channel.id]
        normalized_msg = normalize_string_local(message.content.strip())
        if normalized_msg in ["nose", "ayuda", "ayudame", "ayudarme", "pista"]:
            await message.channel.send(f"Pista: {trivia_item.get('hint', 'No hay pista disponible.')}")
            return
        if normalized_msg == normalize_string_local(trivia_item['answer']):
            symbolic = award_symbolic_reward(message.author, 1)
            response = f"🎉 ¡Correcto, {message.author.display_name}! Has ganado 1 estrella simbólica. Ahora tienes {symbolic} estrellas simbólicas."
            await message.channel.send(response)
            del active_trivia[message.channel.id]
            return

    if any(phrase in content for phrase in ["oráculo", "predicción"]):
        prediction = random.choice([
            "Hoy, las estrellas te favorecen... ¡pero recuerda usar protector solar!",
            "El oráculo dice: el mejor momento para actuar es ahora, ¡sin miedo!",
        ])
        await message.channel.send(f"🔮 {prediction}")
        return

    if content in ["meme", "muéstrame un meme"]:
        meme_url = get_random_meme()
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
def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    threading.Thread(target=run_webserver).start()
    # Se utiliza Uptimerobot para mantener el sitio activo, por lo que no se añade ninguna función de keep alive adicional.
    bot.run(os.getenv('DISCORD_TOKEN'))
