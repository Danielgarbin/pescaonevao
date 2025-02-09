import discord
from discord.ext import commands
from transformers import pipeline
import random

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
nlp = pipeline("question-answering", model="distilbert-base-cased-distilled-squad")

chistes = [
    "¿Por qué los pájaros no usan Facebook? Porque ya tienen Twitter.",
    "¿Cuál es el pez más divertido? El pez payaso.",
    "¿Qué hace una abeja en el gimnasio? ¡Zum-ba!"
]

@bot.event
async def on_ready():
    print(f'Bot is ready. We have logged in as {bot.user}')

@bot.command()
async def avanzar(ctx, *jugadores):
    mensaje = ", ".join(jugadores) + " pasan a la siguiente etapa"
    await ctx.send(mensaje)

@bot.command()
async def eliminar(ctx, jugador):
    await ctx.author.send(f'Has sido eliminado, {jugador}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if "chiste" in message.content.lower():
        await message.channel.send(random.choice(chistes))
    
    # Preguntar clasificación
    if "mi clasificación" in message.content.lower():
        jugador = message.author.name
        # Aquí se agregaría la lógica para obtener la clasificación del jugador
        await message.channel.send(f'{jugador}, tu clasificación es...')
    
    # Responder preguntas en lenguaje natural
    if bot.user.mentioned_in(message):
        context = "Contexto relevante sobre el torneo o los jugadores"
        question = message.content.replace(f'<@!{bot.user.id}>', '').strip()
        response = nlp(question=question, context=context)
        await message.channel.send(response['answer'])

    await bot.process_commands(message)

bot.run('YOUR_DISCORD_BOT_TOKEN')

