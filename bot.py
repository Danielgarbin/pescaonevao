import discord
import sqlite3
from discord.ext import commands
import json
import random
import os
import threading
from flask import Flask

##############################
# CONFIGURACIÓN DEL PROPIETARIO Y CANALES
##############################
OWNER_ID = 1336609089656197171         # REEMPLAZA con tu Discord ID (entero)
PRIVATE_CHANNEL_ID = 1338130641354620988  # REEMPLAZA con el ID del canal privado (para comandos sensibles)
PUBLIC_CHANNEL_ID  = 1338126297666424874  # REEMPLAZA con el ID del canal público (donde se muestran resultados)

##############################
# CONEXIÓN A LA BASE DE DATOS SQLITE (para el torneo; opcional)
##############################
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

##############################
# CONFIGURACIÓN INICIAL DEL TORNEO
##############################
PREFIX = '!'
STAGES = {1: 60, 2: 48, 3: 24, 4: 12, 5: 1}  # Etapa: jugadores que avanzan
current_stage = 1

##############################
# SISTEMA DE ALMACENAMIENTO (JSON) PARA EL TORNEO
##############################
def save_data(data):
    with open('tournament_data.json', 'w') as f:
        json.dump(data, f)

def load_data():
    try:
        with open('tournament_data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"participants": {}}

##############################
# CHISTES – 120 chistes (70 originales + 50 nuevos)
##############################
ALL_JOKES = [
    # --- 70 chistes originales ---
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
    "¿Qué hace un cartero en el gimnasio? Entrega mensajes y se pone en forma.",

    # --- 50 chistes nuevos (adicionales) ---
    "¿Por qué el ordenador fue al psicólogo? Porque tenía demasiadas ventanas abiertas.",
    "¿Qué hace un gato en la computadora? Busca ratones.",
    "¿Por qué la bicicleta no se siente sola? Porque siempre tiene dos ruedas.",
    "¿Qué dijo una impresora frustrada? ¡Estoy sin tinta y sin ideas!",
    "¿Por qué el café nunca se va de vacaciones? Porque siempre está espresso.",
    "¿Qué le dice una calculadora a otra? ¡Tú sumas, yo resto!",
    "¿Por qué el pan no se pierde? Porque siempre tiene miga.",
    "¿Qué hace una manzana en la universidad? Estudia para ser jugosa.",
    "¿Por qué el ventilador es un buen amigo? Porque siempre te da frescura.",
    "¿Qué hace un árbol en una fiesta? Da sombra a los chismes.",
    "¿Por qué el reloj se inscribió a clases de baile? Para aprender a marcar el compás.",
    "¿Qué le dijo el sol a la nube? ¡No te escondas, que te estoy buscando!",
    "¿Por qué el zapato se quedó en casa? Porque estaba muy apretado.",
    "¿Qué hace una lámpara cuando se enoja? Se da una vuelta de chispa.",
    "¿Por qué la nieve nunca miente? Porque es siempre transparente.",
    "¿Qué dijo la almohada al despertador? ¡Déjame dormir, por favor!",
    "¿Por qué el lápiz se deprimió? Porque siempre se siente afilado.",
    "¿Qué hace una fruta cuando se divierte? Se pone en rodajas.",
    "¿Por qué la luna siempre está soltera? Porque tiene fases de compromiso.",
    "¿Qué le dice un espejo a otro? ¡Reflejo lo que siento!",
    "¿Por qué el semáforo no juega a las escondidas? Porque siempre se pone en rojo.",
    "¿Qué hace un pastel en la biblioteca? Busca recetas de historias dulces.",
    "¿Por qué el teléfono rompió con el celular? Porque quería señal de independencia.",
    "¿Qué le dijo una cuchara a un tenedor? ¡Qué tenedor tan puntiagudo tienes!",
    "¿Por qué el edificio no se ríe? Porque es muy serio y tiene pisos.",
    "¿Qué hace un globo cuando se siente triste? Se desinfla.",
    "¿Por qué la araña es una buena amiga? Porque siempre teje conexiones.",
    "¿Qué le dijo el queso a la galleta? ¡Juntos formamos un snack perfecto!",
    "¿Por qué el caracol nunca gana carreras? Porque siempre se lleva la casa a cuestas.",
    "¿Qué hace una botella en el desierto? Se siente muy vacía.",
    "¿Por qué el piano se siente artístico? Porque siempre toca el alma.",
    "¿Qué dijo la taza cuando se rompió? ¡Fue un descafeinado accidente!",
    "¿Por qué el helado es buen amigo? Porque nunca se derrite en la adversidad.",
    "¿Qué hace una estrella fugaz en una fiesta? Cumple deseos.",
    "¿Por qué el cuaderno se sintió ofendido? Porque alguien escribió mal sus líneas.",
    "¿Qué le dijo la naranja al exprimidor? ¡No me exprimas, por favor!",
    "¿Por qué el teclado se volvió romántico? Porque encontraba las teclas de su corazón.",
    "¿Qué hace un cuadro en un museo? Se queda enmarcado en sus pensamientos.",
    "¿Por qué el sombrero es tan modesto? Porque siempre se inclina ante la moda.",
    "¿Qué le dice una escalera a otra? ¡Nos vemos en el siguiente nivel!",
    "¿Por qué la mantequilla se derrite de felicidad? Porque siempre está en su punto.",
    "¿Qué hace un martillo en el gimnasio? Golpea sus límites.",
    "¿Por qué la tostadora es la reina de la cocina? Porque siempre está en la cresta del pan.",
    "¿Qué le dijo el helado a la galleta? ¡Eres mi complemento perfecto!",
    "¿Por qué el campo de fútbol se siente orgulloso? Porque siempre está lleno de goles.",
    "¿Qué hace una botella de agua en el desierto? Se hidrata de alegría.",
    "¿Por qué la escoba es buena en matemáticas? Porque siempre barre con los números.",
    "¿Qué dijo el microondas al refrigerador? ¡Calienta la competencia!",
    "¿Por qué el libro se quedó en silencio? Porque tenía muchas páginas en blanco.",
    "¿Qué hace una lámpara en una fiesta? Ilumina la diversión."
]

# Función para obtener un chiste aleatorio sin repetir hasta agotar la lista
unused_jokes = ALL_JOKES.copy()
def get_random_joke():
    global unused_jokes, ALL_JOKES
    if not unused_jokes:
        unused_jokes = ALL_JOKES.copy()
    joke = random.choice(unused_jokes)
    unused_jokes.remove(joke)
    return joke

##############################
# FUNCIÓN PARA OTORGAR RECOMPENSAS SIMBÓLICAS (ESTRELLAS)
##############################
def award_symbolic_reward(user: discord.Member, reward: int):
    data = load_data()
    user_id = str(user.id)
    if user_id not in data['participants']:
        data['participants'][user_id] = {
            'nombre': user.display_name,
            'puntos': 0,          # Puntaje del torneo (se mantiene separado)
            'symbolic': 0,        # Estrellas simbólicas ganadas en juegos de entretenimiento
            'etapa': current_stage,
            'logros': []
        }
    else:
        if 'symbolic' not in data['participants'][user_id]:
            data['participants'][user_id]['symbolic'] = 0
    current_symbolic = int(data['participants'][user_id].get('symbolic', 0))
    new_symbolic = current_symbolic + reward
    data['participants'][user_id]['symbolic'] = new_symbolic
    save_data(data)
    return new_symbolic

##############################
# VARIABLES PARA ESTADOS DE JUEGOS NATURALES
##############################
active_trivia = {}  # key: channel.id, value: { "question": ..., "answer": ... }

trivia_questions = [
    {"question": "¿Cuál es el río más largo del mundo?", "answer": "amazonas"},
    {"question": "¿En qué año llegó el hombre a la Luna?", "answer": "1969"},
    {"question": "¿Cuál es el planeta más cercano al Sol?", "answer": "mercurio"},
    {"question": "¿Quién escribió 'Cien Años de Soledad'?", "answer": "gabriel garcía márquez"},
    {"question": "¿Cuál es el animal terrestre más rápido?", "answer": "guepardo"},
    {"question": "¿Cuántos planetas hay en el sistema solar?", "answer": "8"},
    {"question": "¿En qué continente se encuentra Egipto?", "answer": "áfrica"},
    {"question": "¿Cuál es el idioma más hablado en el mundo?", "answer": "chino"},
    {"question": "¿Qué instrumento mide la temperatura?", "answer": "termómetro"},
    {"question": "¿Cuál es la capital de Francia?", "answer": "parís"}
]

MEMES = [
    "https://i.imgflip.com/1bij.jpg",
    "https://i.imgflip.com/26am.jpg",
    "https://i.imgflip.com/30b1gx.jpg",
    "https://i.imgflip.com/3si4.jpg",
    "https://i.imgflip.com/2fm6x.jpg"
]

predicciones = [
    "Hoy, las estrellas te favorecen... ¡pero recuerda usar protector solar!",
    "El oráculo dice: el mejor momento para actuar es ahora, ¡sin miedo!",
    "Tu destino es tan brillante que necesitarás gafas de sol.",
    "El futuro es incierto, pero las risas están garantizadas.",
    "Hoy encontrarás una sorpresa inesperada... ¡quizás un buen chiste!",
    "El universo conspira a tu favor, ¡aprovéchalo!",
    "Tu suerte cambiará muy pronto, y será motivo de celebración.",
    "Las oportunidades se presentarán, solo debes estar listo para recibirlas.",
    "El oráculo revela que una gran aventura te espera en el horizonte.",
    "Confía en tus instintos, el camino correcto se te mostrará."
]

##############################
# INICIALIZACIÓN DEL BOT
##############################
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

##############################
# COMANDOS DEL SISTEMA DE PUNTOS (con “!” – Solo el Propietario en canal privado)
# (Estos afectan el puntaje del torneo, NO las recompensas simbólicas)
##############################
@bot.command()
async def actualizar_puntuacion(ctx, jugador: discord.Member, puntos: int):
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
        current = int(data['participants'][user_id].get('puntos', 0))
        data['participants'][user_id]['puntos'] = current + puntos
    else:
        data['participants'][user_id] = {
            'nombre': jugador.display_name,
            'puntos': puntos,
            'etapa': current_stage,
            'logros': []
        }
    save_data(data)
    await send_public_message(f"✅ Puntuación actualizada: {jugador.display_name} ahora tiene {data['participants'][user_id]['puntos']} puntos")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def reducir_puntuacion(ctx, jugador: discord.Member, puntos: int):
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

@bot.command()
async def ver_puntuacion(ctx):
    data = load_data()
    user_id = str(ctx.author.id)
    if user_id in data['participants']:
        await ctx.send(f"🏆 Tu puntaje del torneo es: {data['participants'][user_id]['puntos']}")
    else:
        await ctx.send("❌ No estás registrado en el torneo")

@bot.command()
async def clasificacion(ctx):
    data = load_data()
    sorted_players = sorted(data['participants'].items(), key=lambda item: int(item[1]['puntos']), reverse=True)
    ranking = "🏅 Clasificación del Torneo:\n"
    for idx, (uid, player) in enumerate(sorted_players, 1):
        ranking += f"{idx}. {player['nombre']} - {player['puntos']} puntos\n"
    await ctx.send(ranking)

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
    for uid, player in avanzan:
        try:
            user = await bot.fetch_user(int(uid))
            await user.send(f"🎉 ¡Felicidades! Has avanzado a la etapa {current_stage}")
        except Exception as e:
            print(f"Error al enviar mensaje a {uid}: {e}")
    for uid, player in eliminados:
        try:
            user = await bot.fetch_user(int(uid))
            await user.send("❌ Lo siento, has sido eliminado del torneo")
        except Exception as e:
            print(f"Error al enviar mensaje a {uid}: {e}")
    data['participants'] = {uid: player for uid, player in avanzan}
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
    uid = str(jugador.id)
    if uid in data['participants']:
        del data['participants'][uid]
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

@bot.command()
async def chiste(ctx):
    await ctx.send(get_random_joke())

##############################
# INTERACCIÓN EN LENGUAJE NATURAL (sin “!”)
##############################
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.lower().strip()

    # AYUDA: "comandos" o "lista de comandos"
    if content in ["comandos", "lista de comandos"]:
        help_text = (
            "**Resumen de Comandos:**\n\n"
            "• **Lenguaje Natural:**\n"
            "   - **ranking:** Muestra tu posición y puntaje del torneo.\n"
            "   - **topmejores:** Muestra el ranking de los 10 jugadores con mayor puntaje del torneo.\n"
            "   - **chiste** o **cuéntame un chiste:** Te devuelve un chiste aleatorio (sin repetición hasta agotar la lista).\n"
            "   - **quiero jugar trivia / jugar trivia / trivia:** Inicia una partida de trivia; si respondes correctamente, ganas 1 estrella simbólica.\n"
            "   - **oráculo** o **predicción:** Recibe una predicción divertida.\n"
            "   - **meme** o **muéstrame un meme:** Te muestra un meme aleatorio.\n"
            "   - **juguemos piedra papel tijeras, yo elijo [tu elección]:** Juega a Piedra, Papel o Tijeras; si ganas, ganas 1 estrella simbólica.\n"
            "   - **duelo de chistes contra @usuario:** Inicia un duelo de chistes entre tú y otro usuario; el ganador gana 1 estrella simbólica.\n\n"
            "• **Comandos Sensibles (con '!') – Solo el Propietario en canal privado (afectan el puntaje del torneo):**\n"
            "   - **!actualizar_puntuacion @usuario [puntos]**\n"
            "   - **!reducir_puntuacion @usuario [puntos]**\n"
            "   - **!avanzar_etapa**\n"
            "   - **!eliminar_jugador @usuario**\n"
            "   - **!configurar_etapa [número]**\n"
        )
        await message.channel.send(help_text)
        return

    # TRIVIA
    if any(phrase in content for phrase in ["quiero jugar trivia", "jugar trivia", "trivia"]):
        if message.channel.id not in active_trivia:
            trivia = random.choice(trivia_questions)
            active_trivia[message.channel.id] = trivia
            await message.channel.send(f"**Trivia:** {trivia['question']}\n_Responde en el chat._")
            return

    # Si hay una trivia activa en este canal, verifica la respuesta
    if message.channel.id in active_trivia:
        trivia = active_trivia[message.channel.id]
        if message.content.lower().strip() == trivia['answer'].lower():
            symbolic = award_symbolic_reward(message.author, 1)
            response = f"🎉 ¡Correcto, {message.author.display_name}! Has ganado 1 estrella simbólica. Ahora tienes {symbolic} estrellas simbólicas."
            await message.channel.send(response)
            del active_trivia[message.channel.id]
            return

    # PIEDRA, PAPEL O TIJERAS
    if "juguemos piedra papel tijeras" in content:
        opciones = ["piedra", "papel", "tijeras"]
        user_choice = None
        for op in opciones:
            if op in content:
                user_choice = op
                break
        if not user_choice:
            await message.channel.send("¿Cuál eliges? Por favor indica piedra, papel o tijeras en tu mensaje.")
            return
        bot_choice = random.choice(opciones)
        if user_choice == bot_choice:
            result = "¡Empate!"
        elif (user_choice == "piedra" and bot_choice == "tijeras") or \
             (user_choice == "papel" and bot_choice == "piedra") or \
             (user_choice == "tijeras" and bot_choice == "papel"):
            result = f"¡Ganaste! Yo elegí **{bot_choice}**."
            symbolic = award_symbolic_reward(message.author, 1)
            result += f" Has ganado 1 estrella simbólica. Ahora tienes {symbolic} estrellas simbólicas."
        else:
            result = f"Perdiste. Yo elegí **{bot_choice}**. ¡Inténtalo de nuevo!"
        await message.channel.send(result)
        return

    # DUEL DE CHISTES
    if "duelo de chistes contra" in content:
        if message.mentions:
            opponent = message.mentions[0]
            challenger = message.author
            joke_challenger = get_random_joke()
            joke_opponent = get_random_joke()
            duel_text = (
                f"**Duelo de Chistes:**\n"
                f"{challenger.display_name} dice: {joke_challenger}\n"
                f"{opponent.display_name} dice: {joke_opponent}\n"
            )
            winner = random.choice([challenger, opponent])
            symbolic = award_symbolic_reward(winner, 1)
            duel_text += f"🎉 ¡El ganador es {winner.display_name}! Ha ganado 1 estrella simbólica. Ahora tiene {symbolic} estrellas simbólicas."
            await message.channel.send(duel_text)
            return

    # ORÁCULO / PREDICCIÓN
    if "oráculo" in content or "predicción" in content:
        prediction = random.choice(predicciones)
        await message.channel.send(f"🔮 {prediction}")
        return

    # MEME GENERATOR
    if "meme" in content or "muéstrame un meme" in content:
        meme_url = random.choice(MEMES)
        await message.channel.send(meme_url)
        return

    # TOP 10 MEJORES
    if "topmejores" in content:
        data = load_data()
        sorted_players = sorted(data['participants'].items(), key=lambda item: int(item[1]['puntos']), reverse=True)
        ranking_text = "🏅 **Top 10 Mejores del Torneo:**\n"
        for idx, (uid, player) in enumerate(sorted_players[:10], 1):
            ranking_text += f"{idx}. {player['nombre']} - {player['puntos']} puntos\n"
        await message.channel.send(ranking_text)
        return

    # RANKING PERSONAL (si se menciona "ranking" sin "topmejores")
    if "ranking" in content:
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
            await message.channel.send(f"🏆 {message.author.display_name}, tu ranking es el **{user_rank}** de {len(sorted_players)} y tienes {data['participants'][user_id]['puntos']} puntos en el torneo.")
        else:
            await message.channel.send("❌ No estás registrado en el torneo.")
        return

    # CHISTE (si se menciona "chiste" o "cuéntame un chiste")
    if "chiste" in content or "cuéntame un chiste" in content:
        await message.channel.send(get_random_joke())
        return

    await bot.process_commands(message)

##############################
# EVENTO ON_READY
##############################
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user.name}')

##############################
# SERVIDOR WEB PARA MANTENER EL BOT ACTIVO (Útil para hosting como Render)
##############################
app = Flask('')

@app.route('/')
def home():
    return "El bot está funcionando!"

def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

thread = threading.Thread(target=run_webserver)
thread.start()

##############################
# INICIAR EL BOT
##############################
bot.run(os.getenv('DISCORD_TOKEN'))
