import discord
from discord.ext import commands
import json
import random
from typing import Dict, List

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
TOKEN = 'TU_TOKEN_DEL_BOT'
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

bot = commands.Bot(command_prefix='!', intents=intents)

# Comandos de gestión de puntuaciones
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
    sorted_players = sorted(data['participants'].values(), key=lambda x: x['puntos'], reverse=True)
    
    ranking = "🏅 Clasificación Actual:\n"
    for idx, player in enumerate(sorted_players, 1):
        ranking += f"{idx}. {player['nombre']} - {player['puntos']} puntos\n"
    
    await ctx.send(ranking)

# Comandos de gestión del torneo
@bot.command()
@commands.has_permissions(administrator=True)
async def avanzar_etapa(ctx):
    global current_stage
    current_stage += 1
    data = load_data()
    
    # Ordenar jugadores y seleccionar los que avanzan
    sorted_players = sorted(data['participants'].values(), key=lambda x: x['puntos'], reverse=True)
    cutoff = STAGES[current_stage]
    avanzan = sorted_players[:cutoff]
    eliminados = sorted_players[cutoff:]
    
    # Actualizar etapa de los jugadores
    for player in avanzan:
        user = await bot.fetch_user(int(player['user_id']))
        try:
            await user.send(f"🎉 ¡Felicidades! Has avanzado a la etapa {current_stage}")
        except:
            pass
    
    for player in eliminados:
        user = await bot.fetch_user(int(player['user_id']))
        try:
            await user.send("❌ Lo siento, has sido eliminado del torneo")
        except:
            pass
    
    # Limpiar datos para nueva etapa
    data['participants'] = {k:v for k,v in data['participants'].items() if v in avanzan}
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

# Comandos de entretenimiento
JOKES = [
    "¿Qué hace un pez en el agua? ¡Nada!",
    "¿Cómo se dice pañuelo en japonés? Saka-moko",
    "¿Qué le dice un huevo a una sartén? Me tienes frito"
]

@bot.command()
async def chiste(ctx):
    await ctx.send(random.choice(JOKES))

# Sistema de etapas y notificaciones
@bot.command()
@commands.has_permissions(administrator=True)
async def configurar_etapa(ctx, etapa: int):
    global current_stage
    current_stage = etapa
    await ctx.send(f"✅ Etapa actual configurada a {etapa}")

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user.name}')
    
import os
bot.run(os.getenv('DISCORD_TOKEN'))

