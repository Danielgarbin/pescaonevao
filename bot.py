import os
import discord
from discord.ext import commands
import random
from keep_alive import keep_alive  # Importar el script keep_alive

keep_alive()  # Llamar a la función keep_alive

# Definir los permisos necesarios para el bot
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.guilds = True
intents.message_content = True

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

bot = commands.Bot(command_prefix="!", intents=intents)

chistes = [
    "¿Por qué los pájaros no usan Facebook? Porque ya tienen Twitter.",
    "¿Cuál es el pez más divertido? El pez payaso.",
    "¿Qué hace una abeja en el gimnasio? ¡Zum-ba!"
]

# Base de datos simple en memoria para almacenar puntuaciones
puntuaciones = {}

@bot.event
async def on_ready():
    print(f'Bot is ready. We have logged in as {bot.user}')
    if GUILD_ID:
        guild = bot.get_guild(int(GUILD_ID))
        if guild:
            print(f'Bot conectado al servidor: {guild.name} (ID: {guild.id})')

@bot.command()
async def avanzar(ctx, *jugadores):
    mensaje = ", ".join(jugadores) + " pasan a la siguiente etapa"
    await ctx.send(mensaje)

@bot.command()
async def eliminar(ctx, jugador):
    await ctx.author.send(f'Has sido eliminado, {jugador}')

@bot.command()
async def puntuacion(ctx, jugador: str, puntos: int):
    if jugador in puntuaciones:
        puntuaciones[jugador] += puntos
    else:
        puntuaciones[jugador] = puntos
    await ctx.send(f'Puntuación actualizada para {jugador}: {puntuaciones[jugador]} puntos')

@bot.command()
async def mi_clasificacion(ctx):
    jugador = ctx.author.name
    if jugador in puntuaciones:
        await ctx.send(f'{jugador}, tu puntuación es {puntuaciones[jugador]} puntos')
    else:
        await ctx.send(f'{jugador}, aún no tienes puntuaciones registradas')

@bot.command()
async def chiste(ctx):
    await ctx.send(random.choice(chistes))

# Preguntar clasificación
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if "chiste" in message.content.lower():
        await message.channel.send(random.choice(chistes))
    
    if "mi top" in message.content.lower():  # Cambio solicitado
        jugador = message.author.name
        if jugador in puntuaciones:
            await message.channel.send(f'{jugador}, tu puntuación es {puntuaciones[jugador]} puntos')
        else:
            await message.channel.send(f'{jugador}, aún no tienes puntuaciones registradas')
    
    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)
