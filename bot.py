import discord
import sqlite3
from discord.ext import commands
import json
import random
from typing import Dict, List
import os
from flask import Flask
import threading

# Conexión a la base de datos SQLite
conn = sqlite3.connect('tournament.db')
cursor = conn.cursor()

# Crear la tabla de jugadores si no existe
cursor.execute('''
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY,
        score INTEGER DEFAULT 0,
        stage INTEGER DEFAULT 1
    )
''')
conn.commit()

# Configuración inicial
# El token se tomará de la variable de entorno "DISCORD_TOKEN"
PREFIX = '!'
STAGES = {1: 60, 2: 48, 3: 24, 4: 12, 5: 1}  # Etapa: jugadores que avanzan
current_stage = 1

# Sistema de almacenamiento (JSON)
def save_data(data):
    with open('tournament_data.json', 'w') as f:
        json.dump(data, f)

def load_data():
    try:
        with open('tournament_data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"participants": {}}

# Inicialización del bot
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ----------------------------
# Comandos de gestión de puntuaciones
# ----------------------------
@bot.command()
async def actualizar_puntuacion(ctx, jugador: discord.Member, puntos: int):
    data = load_data()
    user_id = str(jugador.id)
    
    if user_id in data['participants']:
        data['participants'][user_id]['puntos'] += puntos
    else:
        data['participants'][user_id] = {
            'nombre': jugador.display_name,
            'puntos': puntos,
            'etapa': current_stage
        }
    
    save_data(data)
    await ctx.send(f"✅ Puntuación actualizada: {jugador.display_name} ahora tiene {data['participants'][user_id]['puntos']} puntos")

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
    # Ordenar participantes por puntos de forma descendente
    sorted_players = sorted(data['participants'].items(), key=lambda item: item[1]['puntos'], reverse=True)
    
    ranking = "🏅 Clasificación Actual:\n"
    for idx, (user_id, player) in enumerate(sorted_players, 1):
        ranking += f"{idx}. {player['nombre']} - {player['puntos']} puntos\n"
    
    await ctx.send(ranking)

# ----------------------------
# Comandos de gestión del torneo
# ----------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def avanzar_etapa(ctx):
    global current_stage
    current_stage += 1
    data = load_data()
    
    # Ordenar jugadores y seleccionar los que avanzan
    sorted_players = sorted(data['participants'].items(), key=lambda item: item[1]['puntos'], reverse=True)
    cutoff = STAGES[current_stage]
    avanzan = sorted_players[:cutoff]
    eliminados = sorted_players[cutoff:]
    
    # Notificar a los jugadores que avanzan
    for user_id, player in avanzan:
        try:
            user = await bot.fetch_user(int(user_id))
            await user.send(f"🎉 ¡Felicidades! Has avanzado a la etapa {current_stage}")
        except Exception as e:
            print(f"Error al enviar mensaje a {user_id}: {e}")
    
    # Notificar a los jugadores eliminados
    for user_id, player in eliminados:
        try:
            user = await bot.fetch_user(int(user_id))
            await user.send("❌ Lo siento, has sido eliminado del torneo")
        except Exception as e:
            print(f"Error al enviar mensaje a {user_id}: {e}")
    
    # Conservar solo a los jugadores que avanzaron
    data['participants'] = {user_id: player for user_id, player in avanzan}
    save_data(data)
    await ctx.send(f"✅ Etapa {current_stage} iniciada. {cutoff} jugadores avanzaron")

@bot.command()
@commands.has_permissions(administrator=True)
async def eliminar_jugador(ctx, jugador: discord.Member):
    data = load_data()
    user_id = str(jugador.id)
    
    if user_id in data['participants']:
        del data['participants'][user_id]
        save_data(data)
        try:
            await jugador.send("🚫 Has sido eliminado del torneo")
        except:
            pass
        await ctx.send(f"✅ {jugador.display_name} eliminado del torneo")
    else:
        await ctx.send("❌ Jugador no encontrado")

# ----------------------------
# Comandos de entretenimiento
# ----------------------------
JOKES = [
    "¿Qué hace un pez en el agua? ¡Nada!",
    "¿Cómo se dice pañuelo en japonés? Saka-moko",
    "¿Qué le dice un huevo a una sartén? Me tienes frito"
]

@bot.command()
async def chiste(ctx):
    await ctx.send(random.choice(JOKES))

# ----------------------------
# Sistema de etapas y notificaciones
# ----------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def configurar_etapa(ctx, etapa: int):
    global current_stage
    current_stage = etapa
    await ctx.send(f"✅ Etapa actual configurada a {etapa}")

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user.name}')

# ----------------------------
# Interacción en lenguaje natural
# ----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    content = message.content.lower()
    
    # Si el mensaje menciona "ranking", responde con el ranking actual
    if "ranking" in content:
        data = load_data()
        sorted_players = sorted(data['participants'].items(), key=lambda item: item[1]['puntos'], reverse=True)
        ranking_text = "🏅 Ranking Actual:\n"
        for idx, (user_id, player) in enumerate(sorted_players, 1):
            ranking_text += f"{idx}. {player['nombre']} - {player['puntos']} puntos\n"
        await message.channel.send(ranking_text)
        return
    
    # Si el mensaje pide un chiste
    if "chiste" in content or "cuéntame un chiste" in content:
        await message.channel.send(random.choice(JOKES))
        return
    
    await bot.process_commands(message)

# ----------------------------
# Servidor Web para mantener el bot activo (útil para Render)
# ----------------------------
app = Flask('')

@app.route('/')
def home():
    return "El bot está funcionando!"

def run_webserver():
    port = int(os.environ.get("PORT", 8080))  # Usa el puerto asignado por Render o 8080 por defecto
    app.run(host='0.0.0.0', port=port)

# Iniciar el servidor web en un hilo separado
thread = threading.Thread(target=run_webserver)
thread.start()

# ----------------------------
# Iniciar el bot
# ----------------------------
bot.run(os.getenv('DISCORD_TOKEN'))
