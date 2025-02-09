import os
from flask import Flask, render_template, request

app = Flask(__name__)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
