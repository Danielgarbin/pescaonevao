from flask import Flask, render_template, request
import discord
from discord.ext import commands

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/puntuacion', methods=['POST'])
def puntuacion():
    jugador = request.form['jugador']
    puntos = int(request.form['puntos'])
    # Lógica para actualizar la puntuación del jugador
    return 'Puntuación actualizada'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

