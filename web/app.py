import os
from flask import Flask, render_template, request
import discord
from discord.ext import commands

# Definir los permisos necesarios para el bot
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.guilds = True
intents.message_content = True  # Permite al bot leer el contenido de los mensajes

# Obtener el token del bot y el ID del servidor desde las variables de entorno
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

# Inicializar el bot de Discord
bot = commands.Bot(command_prefix="!", intents=intents)

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/puntuacion', methods=['POST'])
def puntuacion():
    jugador = request.form['jugador']
    puntos = int(request.form['puntos'])
    # Lógica para actualizar la puntuación del jugador
    # Aquí puedes agregar lógica adicional para interactuar con el bot de Discord si es necesario
    return 'Puntuación actualizada'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
