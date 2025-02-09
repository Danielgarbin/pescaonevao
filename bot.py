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
JOKES = [
    "¿Qué hace un pez en el agua? ¡Nada!",
    "¿Cómo se dice pañuelo en japonés? Saka-moko",
    "¿Qué le dice un huevo a una sartén? Me tienes frito"
]

@bot.command()
async def chiste(ctx):
    await ctx.send(random.choice(JOKES))

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
    
    if "ranking" in content:
        data = load_data()
        sorted_players = sorted(data['participants'].items(), key=lambda item: int(item[1]['puntos']), reverse=True)
        ranking_text = "🏅 Ranking Actual:\n"
        for idx, (user_id, player) in enumerate(sorted_players, 1):
            ranking_text += f"{idx}. {player['nombre']} - {player['puntos']} puntos\n"
        await message.channel.send(ranking_text)
        return
    
    if "chiste" in content or "cuéntame un chiste" in content:
        await message.channel.send(random.choice(JOKES))
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
