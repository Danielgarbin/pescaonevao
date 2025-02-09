import os
from flask import Flask, render_template, request
import discord
from discord.ext import commands

app = Flask(__name__)

# Inicializar el bot de Discord
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.guilds = True
intents.message_content = True

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

bot = commands.Bot(command_prefix="!", intents=intents)

# Base de datos simple en memoria para almacenar puntuaciones
puntuaciones = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/puntuacion', methods=['POST'])
def actualizar_puntuacion():
    jugador = request.form['jugador']
    puntos = int(request.form['puntos'])
    if jugador in puntuaciones:
        puntuaciones[jugador] += puntos
    else:
        puntuaciones[jugador] = puntos
    return f'Puntuación actualizada para {jugador}: {puntuaciones[jugador]} puntos'

@app.route('/keep_alive')
def keep_alive():
    # Verificar si el bot está conectado
    if bot.is_closed():
        return 'Bot is not running!', 500
    return 'Bot is running!'

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
