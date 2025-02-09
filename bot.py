import discord
import sqlite3
from discord.ext import commands
import json
import random
from typing import Dict, List
import os
from flask import Flask
import threading

# ***********************
# CONFIGURACIÓN DEL PROPIETARIO Y CANALES
# ***********************
OWNER_ID = 1336609089656197171  # Reemplaza este número con tu propio Discord ID (como entero)
PRIVATE_CHANNEL_ID = 1338130641354620988  # ID del canal privado donde enviarás comandos sensibles
PUBLIC_CHANNEL_ID  = 1338126297666424874  # ID del canal público donde se mostrarán los resultados

# ***********************
# CONEXIÓN A LA BASE DE DATOS SQLITE
# ***********************
conn = sqlite3.connect('tournament.db')
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY,
        score INTEGER DEFAULT 0,
        stage INTEGER DEFAULT 1
    )
''')
conn.commit()

# ***********************
# CONFIGURACIÓN INICIAL
# ***********************
PREFIX = '!'
STAGES = {1: 60, 2: 48, 3: 24, 4: 12, 5: 1}  # Etapa: jugadores que avanzan
current_stage = 1

# ***********************
# SISTEMA DE ALMACENAMIENTO (JSON)
# ***********************
def save_data(data):
    with open('tournament_data.json', 'w') as f:
        json.dump(data, f)

def load_data():
    try:
        with open('tournament_data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"participants": {}}

# ***********************
# CONFIGURACIÓN DE CHISTES
# ***********************
ALL_JOKES = [
    "¿Qué hace una abeja en el gimnasio? ¡Zum-ba!",
    "¿Por qué los pájaros no usan Facebook? Porque ya tienen Twitter.",
    "¿Qué le dijo un semáforo a otro? No me mires, me estoy cambiando.",
    "¿Por qué el libro de matemáticas se sentía triste? Porque tenía demasiados problemas.",
    "¿Qué hace una taza en la escuela? Toma té.",
    "¿Cómo se despiden los químicos? Ácido un placer.",
    "¿Qué le dijo la pared al cuadro? ¡Qué arte tienes!",
    "¿Cuál es el animal más antiguo? La cebra, porque está en blanco y negro.",
    "¿Por qué los esqueletos no pelean entre ellos? Porque no tienen agallas.",
    "¿Qué le dijo un pez a otro? Nada, nada.",
    "¿Cómo se llama el campeón de buceo japonés? Tokofondo. ¿Y el subcampeón? Kasitoko.",
    "¿Qué hace un pollo en un ascensor? ¡Pío, pío, sube!",
    "¿Cuál es el colmo de un jardinero? Que siempre lo dejen plantado.",
    "¿Qué le dice una iguana a su hermana gemela? Somos iguanitas.",
    "¿Qué hace un león con una cuchara? ¡Cuchichea!",
    "¿Por qué la escoba está feliz? Porque está barriendo.",
    "¿Qué le dijo el cero al ocho? ¡Bonito cinturón!",
    "¿Por qué la gallina se sentó en el reloj? Porque quería poner el tiempo en orden.",
    "¿Qué hace un pez payaso? Nada, solo hace chistes.",
    "¿Por qué los programadores confunden Halloween y Navidad? Porque OCT 31 es igual a DEC 25.",
    "¿Cómo se llama un perro sin patas? No importa, no va a venir.",
    "¿Qué hace una oreja en el cine? Escucha la película.",
    "¿Cuál es el colmo de un electricista? No poder cambiar su vida.",
    "¿Qué le dijo una bombilla a otra? ¡Nos vemos en el enchufe!",
    "¿Qué le dice una impresora a otra? ¿Esa hoja es tuya o es una impresión mía?",
    "¿Por qué no se pelean los números? Porque siempre se suman.",
    "¿Qué hace un pez en una biblioteca? Nada, porque se le escapan los libros.",
    "¿Cuál es el colmo de un músico? Que lo dejen en silencio.",
    "¿Qué hace una planta en una fiesta? Se riega de alegría.",
    "¿Cómo se dice 'hospital' en inglés? ¡Hopital, hop, hop!",
    "¿Qué le dijo el tomate a la cebolla? No llores, que te veo venir.",
    "¿Por qué la bicicleta no se para sola? Porque está dos-tirada.",
    "¿Qué le dice un caracol a otro? ¡Vamos despacio!",
    "¿Qué le dijo el sol a la luna? ¡Te veo en la noche!",
    "¿Cuál es el colmo de un panadero? Que siempre se le queme el pan.",
    "¿Por qué el perro lleva reloj? Porque quiere ser puntual.",
    "¿Qué hace una serpiente en un concierto? ¡Sssintonia!",
    "¿Por qué el elefante no usa ordenador? Porque le tiene miedo al ratón.",
    "¿Qué le dice un plátano a una gelatina? ¡No tiemblo por ti!",
    "¿Cómo se dice pelo en francés? 'Cheveu', pero no sé si me lo crees.",
    "¿Qué hace una vaca en un terremoto? ¡Muuuuu-vemento!",
    "¿Por qué el cartero se fue de vacaciones? Porque necesitaba un cambio de dirección.",
    "¿Qué le dijo una calculadora a otra? ¡Tienes muchos números!",
    "¿Por qué el ciego no puede ser DJ? Porque no encuentra el disco.",
    "¿Qué hace un robot en la playa? Recoge arena en sus circuitos.",
    "¿Por qué las focas miran siempre hacia arriba? ¡Porque ahí están los focos!",
    "¿Qué hace una galleta en el hospital? Se desmorona.",
    "¿Por qué los pájaros no usan el ascensor? Porque ya tienen alas.",
    "¿Qué le dijo una taza a otra? ¡Qué té tan bueno!",
    "¿Por qué el helado se derrite? Porque no soporta el calor.",
    "¿Qué hace una vaca en el espacio? ¡Muuuuuu, en gravedad cero!",
    "¿Cuál es el colmo de un astronauta? Que siempre se sienta fuera de este mundo.",
    "¿Qué le dijo una impresora 3D a otra? Te imprimo mi amistad.",
    "¿Por qué los vampiros no pueden jugar al fútbol? Porque siempre pierden la sangre en la cancha.",
    "¿Qué hace una araña en internet? Teje la web.",
    "¿Por qué la luna fue al médico? Porque se sentía en cuarto menguante.",
    "¿Qué hace un globo en una fiesta? Se infla de felicidad.",
    "¿Qué le dice un gusano a otro? Voy a dar una vuelta a la manzana.",
    "¿Por qué las ardillas no usan celular? Porque ya tienen su propia cola.",
    "¿Qué hace una sombra en la oscuridad? Se esconde.",
    "¿Por qué el sol nunca se pone? Porque siempre brilla.",
    "¿Qué hace una llave en un cajón? Abre puertas a la imaginación.",
    "¿Por qué los relojes son malos contando chistes? Porque siempre dan la hora.",
    "¿Qué le dice un diente a otro? ¡Nos vemos en la muela!",
    "¿Por qué la computadora fue al médico? Porque tenía un virus.",
    "¿Qué hace una escalera en un edificio? Eleva la diversión.",
    "¿Por qué el viento es buen amigo? Porque siempre sopla contigo.",
    "¿Qué le dijo una estrella a otra? Brilla, que brillas.",
    "¿Cuál es el colmo de un sastre? Que siempre le quede corto el hilo.",
    "¿Qué hace un cartero en el gimnasio? Entrega mensajes y se pone en forma."
]

# Lista auxiliar para controlar los chistes no repetidos
unused_jokes = ALL_JOKES.copy()

def get_random_joke():
    global unused_jokes, ALL_JOKES
    if not unused_jokes:
        unused_jokes = ALL_JOKES.copy()
    joke = random.choice(unused_jokes)
    unused_jokes.remove(joke)
    return joke

# ***********************
# INICIALIZACIÓN DEL BOT
# ***********************
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Función auxiliar para enviar mensajes al canal público
async def send_public_message(message: str):
    public_channel = bot.get_channel(PUBLIC_CHANNEL_ID)
    if public_channel:
        await public_channel.send(message)
    else:
        print("No se pudo encontrar el canal público.")

# ***********************
# COMANDOS DE GESTIÓN DE PUNTUACIONES (Solo el propietario y solo desde el canal privado)
# ***********************
@bot.command()
async def actualizar_puntuacion(ctx, jugador: discord.Member, puntos: int):
    # Verifica que el autor sea el propietario y que el comando se ejecute en el canal privado
    if ctx.author.id != OWNER_ID or ctx.channel.id != PRIVATE_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return

    try:
        puntos = int(puntos)
    except ValueError:
        await send_public_message("Por favor, proporciona un número válido de puntos.")
        return

    data = load_data()
    user_id = str(jugador.id)
    if user_id in data['participants']:
        puntos_actuales = int(data['participants'][user_id].get('puntos', 0))
        data['participants'][user_id]['puntos'] = puntos_actuales + puntos
    else:
        data['participants'][user_id] = {
            'nombre': jugador.display_name,
            'puntos': puntos,
            'etapa': current_stage
        }
    save_data(data)
    await send_public_message(f"✅ Puntuación actualizada: {jugador.display_name} ahora tiene {data['participants'][user_id]['puntos']} puntos")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def reducir_puntuacion(ctx, jugador: discord.Member, puntos: int):
    # Se utiliza actualizar_puntuacion con valor negativo
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

# ***********************
# COMANDOS DE CONSULTA (abiertos para todos)
# ***********************
@bot.command()
async def ver_puntuacion(ctx):
    data = load_data()
    user_id = str(ctx.author.id)
    if user_id in data['participants']:
        await ctx.send(f"🏆 Tu puntuación actual es: {data['participants'][user_id]['puntos']}")
    else:
        await ctx.send("❌ No estás registrado en el torneo")

@bot.command()
async def clasificacion(ctx):
    data = load_data()
    sorted_players = sorted(data['participants'].items(), key=lambda item: int(item[1]['puntos']), reverse=True)
    ranking = "🏅 Clasificación Actual:\n"
    for idx, (user_id, player) in enumerate(sorted_players, 1):
        ranking += f"{idx}. {player['nombre']} - {player['puntos']} puntos\n"
    await ctx.send(ranking)

# ***********************
# COMANDOS DE GESTIÓN DEL TORNEO (Solo el propietario y solo desde el canal privado)
# ***********************
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
    data = load_data()
    sorted_players = sorted(data['participants'].items(), key=lambda item: int(item[1]['puntos']), reverse=True)
    cutoff = STAGES[current_stage]
    avanzan = sorted_players[:cutoff]
    eliminados = sorted_players[cutoff:]
    
    for user_id, player in avanzan:
        try:
            user = await bot.fetch_user(int(user_id))
            await user.send(f"🎉 ¡Felicidades! Has avanzado a la etapa {current_stage}")
        except Exception as e:
            print(f"Error al enviar mensaje a {user_id}: {e}")
    
    for user_id, player in eliminados:
        try:
            user = await bot.fetch_user(int(user_id))
            await user.send("❌ Lo siento, has sido eliminado del torneo")
        except Exception as e:
            print(f"Error al enviar mensaje a {user_id}: {e}")
    
    data['participants'] = {user_id: player for user_id, player in avanzan}
    save_data(data)
    await send_public_message(f"✅ Etapa {current_stage} iniciada. {cutoff} jugadores avanzaron")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def eliminar_jugador(ctx, jugador: discord.Member):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PRIVATE_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return

    data = load_data()
    user_id = str(jugador.id)
    if user_id in data['participants']:
        del data['participants'][user_id]
        save_data(data)
        try:
            await jugador.send("🚫 Has sido eliminado del torneo")
        except:
            pass
        await send_public_message(f"✅ {jugador.display_name} eliminado del torneo")
    else:
        await send_public_message("❌ Jugador no encontrado")
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

# ***********************
# COMANDO DE ENTRETENIMIENTO (abierto para todos)
# ***********************
@bot.command()
async def chiste(ctx):
    await ctx.send(get_random_joke())

# ***********************
# EVENTO ON_READY
# ***********************
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user.name}')

# ***********************
# INTERACCIÓN EN LENGUAJE NATURAL (abierto para todos)
# ***********************
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.lower()

    # Si se menciona "topmejores", mostrar los 10 mejores jugadores
    if "topmejores" in content:
        data = load_data()
        sorted_players = sorted(data['participants'].items(), key=lambda item: int(item[1]['puntos']), reverse=True)
        ranking_text = "🏅 Top 10 Mejores:\n"
        for idx, (user_id, player) in enumerate(sorted_players[:10], 1):
            ranking_text += f"{idx}. {player['nombre']} - {player['puntos']} puntos\n"
        await message.channel.send(ranking_text)
        return

    # Si se menciona "ranking" (sin "topmejores"), mostrar el ranking personal del usuario
    elif "ranking" in content:
        data = load_data()
        sorted_players = sorted(data['participants'].items(), key=lambda item: int(item[1]['puntos']), reverse=True)
        user_id = str(message.author.id)
        found = False
        user_rank = 0
        for rank, (uid, player) in enumerate(sorted_players, 1):
            if uid == user_id:
                user_rank = rank
                found = True
                break
        if found:
            await message.channel.send(f"🏆 Tu ranking es el {user_rank} de {len(sorted_players)} con {data['participants'][user_id]['puntos']} puntos")
        else:
            await message.channel.send("❌ No estás registrado en el torneo")
        return

    # Si se solicita un chiste
    if "chiste" in content or "cuéntame un chiste" in content:
        await message.channel.send(get_random_joke())
        return

    await bot.process_commands(message)

# ***********************
# SERVIDOR WEB PARA MANTENER EL BOT ACTIVO (Útil para hosting como Render)
# ***********************
app = Flask('')

@app.route('/')
def home():
    return "El bot está funcionando!"

def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

thread = threading.Thread(target=run_webserver)
thread.start()

# ***********************
# INICIAR EL BOT
# ***********************
bot.run(os.getenv('DISCORD_TOKEN'))
