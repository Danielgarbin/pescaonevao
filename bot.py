import discord
import psycopg2
import psycopg2.extras
from discord.ext import commands
import json
import random
import os
import re
import threading
from flask import Flask

######################################
# CONFIGURACIÓN: IDs y Servidor
######################################
OWNER_ID = 1336609089656197171         # Tu Discord ID (único autorizado para comandos sensibles)
CHANNEL_ID = 1338126297666424874         # Canal donde se publican resultados y se ejecutan los comandos
GUILD_ID = 1337387112403697694            # ID de tu servidor (guild)

######################################
# CONEXIÓN A LA BASE DE DATOS POSTGRESQL
######################################
DATABASE_URL = os.environ.get("DATABASE_URL")  # Configurada en Render
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True

def init_db():
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id TEXT PRIMARY KEY,
                nombre TEXT,
                puntos INTEGER DEFAULT 0,
                symbolic INTEGER DEFAULT 0,
                etapa INTEGER DEFAULT 1,
                eliminado BOOLEAN DEFAULT FALSE,
                logros JSONB DEFAULT '[]'
            )
        """)
init_db()

######################################
# CONFIGURACIÓN DEL TORNEO: Etapas y Nombres
######################################
STAGES = {1: 60, 2: 48, 3: 32, 4: 24, 5: 14}  # Máximo de jugadores que avanzan en cada etapa
stage_names = {
    1: "Battle Royale",
    2: "Snipers vs Runners",
    3: "Boxfight duos",
    4: "Pescadito dice",
    5: "Gran Final"
}
current_stage = 1  # Etapa inicial

######################################
# VARIABLE GLOBAL PARA TRIVIA
######################################
active_trivia = {}  # key: channel.id, value: dict con la trivia actual

######################################
# FUNCIONES PARA LA BASE DE DATOS
######################################
def get_participant(user_id):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM participants WHERE id = %s", (user_id,))
        return cur.fetchone()

def get_all_participants():
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM participants")
        rows = cur.fetchall()
        data = {"participants": {}}
        for row in rows:
            data["participants"][row["id"]] = row
        return data

def upsert_participant(user_id, participant):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO participants (id, nombre, puntos, symbolic, etapa, eliminado, logros)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                puntos = EXCLUDED.puntos,
                symbolic = EXCLUDED.symbolic,
                etapa = EXCLUDED.etapa,
                eliminado = EXCLUDED.eliminado,
                logros = EXCLUDED.logros
        """, (
            user_id,
            participant["nombre"],
            participant.get("puntos", 0),
            participant.get("symbolic", 0),
            participant.get("etapa", current_stage),
            participant.get("eliminado", False),
            json.dumps(participant.get("logros", []))
        ))

def update_score(user: discord.Member, delta: int):
    user_id = str(user.id)
    participant = get_participant(user_id)
    if participant is None:
        participant = {
            "nombre": user.display_name,
            "puntos": 0,
            "symbolic": 0,
            "etapa": current_stage,
            "eliminado": False,
            "logros": []
        }
    new_points = int(participant.get("puntos", 0)) + delta
    participant["puntos"] = new_points
    upsert_participant(user_id, participant)
    return new_points

def award_symbolic_reward(user: discord.Member, reward: int):
    user_id = str(user.id)
    participant = get_participant(user_id)
    if participant is None:
        participant = {
            "nombre": user.display_name,
            "puntos": 0,
            "symbolic": 0,
            "etapa": current_stage,
            "eliminado": False,
            "logros": []
        }
    current_symbolic = int(participant.get("symbolic", 0))
    new_symbolic = current_symbolic + reward
    participant["symbolic"] = new_symbolic
    upsert_participant(user_id, participant)
    return new_symbolic

######################################
# CHISTES (170 chistes)
######################################
ALL_JOKES = [
    # Bloque 1: 70 chistes originales
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
    "¿Qué hace un globo en una fiesta? Se infla de felicidad!",
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

    # Bloque 2: 50 chistes adicionales
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

    # Bloque 3: 50 chistes nuevos (los mejores que jamás he creado)
    "¿Por qué el reloj se fue al gimnasio? Porque quería marcar ritmo.",
    "¿Qué hace un pez en el ordenador? Nada en la red.",
    "¿Por qué los fantasmas no pueden mentir? Porque se les ve a través.",
    "¿Qué le dijo una computadora a otra? ¡Eres mi byte favorito!",
    "¿Por qué el pan no se duerme? Porque siempre está tostado.",
    "¿Qué hace una impresora en el desierto? Imprime arena.",
    "¿Por qué la luna se fue de vacaciones? Porque necesitaba un descanso de la Tierra.",
    "¿Qué le dijo el vino al queso? ¡Juntos somos una combinación perfecta!",
    "¿Por qué el semáforo siempre es puntual? Porque nunca se queda en rojo.",
    "¿Qué hace una escalera en la nieve? Se derrite de frío.",
    "¿Por qué el gato estudió informática? Porque quería ser el ratón de biblioteca.",
    "¿Qué le dijo el árbol a la brisa? ¡Eres mi aire favorito!",
    "¿Por qué el café se hizo influencer? Porque siempre estaba espresso en las redes.",
    "¿Qué hace un zapato en una cita? Camina a tu lado.",
    "¿Por qué la lámpara se negó a trabajar? Porque estaba en modo ahorro.",
    "¿Qué le dijo el ventilador al termómetro? ¡Nos complementamos perfectamente!",
    "¿Por qué el reloj se sintió presionado? Porque no tenía tiempo para descansar.",
    "¿Qué hace un libro en la playa? Se abre al sol.",
    "¿Por qué el lápiz rompió con la pluma? Porque necesitaba escribir su propia historia.",
    "¿Qué dijo el espejo cuando vio su reflejo? ¡Eres mi otra mitad!",
    "¿Por qué la manzana se volvió famosa? Porque siempre tenía un iPhone a la mano.",
    "¿Qué hace un teléfono en el cine? Toma selfies en la oscuridad.",
    "¿Por qué el ratón de computadora fue a la escuela? Para mejorar su clic.",
    "¿Qué le dijo el jardín a la maceta? ¡Eres la flor de mi vida!",
    "¿Por qué el helado fue al médico? Porque se sentía derretido por dentro.",
    "¿Qué hace un carro en el gimnasio? Levanta ruedas.",
    "¿Por qué el panadero fue a la playa? Porque quería hacer pan tostado.",
    "¿Qué dijo el tomate a la lechuga? ¡Eres la ensalada de mi vida!",
    "¿Por qué el camión se puso a cantar? Porque tenía una gran carga de ritmo.",
    "¿Qué hace un globo en la oficina? Eleva la productividad.",
    "¿Por qué la batería se siente recargada? Porque siempre está conectada.",
    "¿Qué dijo el reloj digital al analógico? ¡Actualízate, amigo!",
    "¿Por qué el zapato se sintió perdido? Porque no encontró su par.",
    "¿Qué hace una taza en una fiesta de té? Se sirve de buena compañía.",
    "¿Por qué la cuchara siempre es amable? Porque tiene una gran capacidad de servir.",
    "¿Qué le dijo la ventana al sol? ¡Déjame ver el mundo!",
    "¿Por qué el motor se emocionó? Porque se encendió la pasión.",
    "¿Qué hace un boomerang cuando se cansa? Se queda en pausa y vuelve a su punto.",
    "¿Qué hace una impresora 4D? Imprime tu futuro.",
    "¿Por qué el microondas es tan sabio? Porque siempre calienta la verdad.",
    "¿Qué hace una cámara en una fiesta? Captura momentos inolvidables.",
    "¿Por qué el altavoz nunca se calla? Porque siempre tiene voz.",
    "¿Qué le dijo el modem al router? ¡Conéctate conmigo!",
    "¿Por qué la batería siempre está en forma? Porque se carga constantemente.",
    "¿Qué hace un cargador en el gimnasio? Levanta energía.",
    "¿Por qué el disco duro siempre es puntual? Porque guarda el tiempo.",
    "¿Qué dijo el proyector a la pantalla? ¡Ilumina mi camino!",
    "¿Por qué el cable HDMI es un gran amigo? Porque siempre transmite buenas vibras.",
    "¿Qué hace un ventilador en invierno? Enfría el ambiente.",
    "¿Por qué el monitor siempre tiene buena imagen? Porque se cuida a sí mismo."
]

######################################
# INICIALIZACIÓN DEL BOT
######################################
intents = discord.Intents.default()
intents.members = True   # Para acceder a todos los miembros del servidor
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def send_public_message(message: str):
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(message)
    else:
        print("No se pudo encontrar el canal público.")

######################################
# COMANDOS SENSIBLES (Con "!" – Solo el propietario, en cualquier canal)
######################################
@bot.command(name="mas_puntos")
async def mas_puntos(ctx, jugador: str, puntos: int):
    if ctx.author.id != OWNER_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    match = re.search(r'\d+', jugador)
    if not match:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    member_id = int(match.group())
    guild = ctx.guild or bot.get_guild(GUILD_ID)
    if guild is None:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    try:
        member = guild.get_member(member_id)
        if member is None:
            member = await guild.fetch_member(member_id)
    except Exception:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    try:
        puntos = int(puntos)
    except ValueError:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    new_points = update_score(member, puntos)
    await send_public_message(f"✅ {member.display_name} ahora tiene {new_points} puntos")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command(name="menos_puntos")
async def menos_puntos(ctx, jugador: str, puntos: int):
    await mas_puntos(ctx, jugador, -puntos)
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def avanzar_etapa(ctx):
    if ctx.author.id != OWNER_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage
    new_stage = current_stage + 1
    required = STAGES.get(new_stage)
    if not required:
        await send_public_message("No existe una etapa siguiente definida.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    data = get_all_participants()
    active_players = []
    for uid, player in data["participants"].items():
        if (player.get("etapa", 1) == current_stage) and (not player.get("eliminado", False)):
            active_players.append((uid, player))
    sorted_players = sorted(active_players, key=lambda x: int(x[1].get("puntos", 0)), reverse=True)
    advancing = sorted_players[:required]
    eliminated = sorted_players[required:]
    for uid, player in advancing:
        player["etapa"] = new_stage
        player["eliminado"] = False
        upsert_participant(uid, player)
        try:
            member = ctx.guild.get_member(int(uid)) or await ctx.guild.fetch_member(int(uid))
            await member.send(f"🎉 ¡Felicitaciones! Has avanzado a {stage_names[new_stage]}!")
        except Exception as e:
            print(f"Error enviando DM a {uid}: {e}")
    for uid, player in eliminated:
        player["eliminado"] = True
        upsert_participant(uid, player)
        try:
            member = ctx.guild.get_member(int(uid)) or await ctx.guild.fetch_member(int(uid))
            await member.send(f"😢 Lo siento, has sido eliminado del torneo en {stage_names[new_stage]}.")
        except Exception as e:
            print(f"Error enviando DM a {uid}: {e}")
    current_stage = new_stage
    await send_public_message(f"✅ Ahora estamos en {stage_names[new_stage]}.")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def regresar_etapa(ctx):
    if ctx.author.id != OWNER_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage
    if current_stage == 1:
        await send_public_message("Ya estás en la etapa 1. No se puede retroceder más.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    new_stage = current_stage - 1
    data = get_all_participants()
    for uid, player in data["participants"].items():
        if player.get("etapa", 1) > new_stage:
            player["etapa"] = new_stage
            player["eliminado"] = False
            upsert_participant(uid, player)
    current_stage = new_stage
    await send_public_message(f"✅ Se ha retrocedido a {stage_names[new_stage]}.")
    try:
        await ctx.message.delete()
    except:
        pass

######################################
# EVENTO ON_MESSAGE: Comandos de Lenguaje Natural
######################################
@bot.event
async def on_message(message):
    # Si el mensaje comienza con "!" y el autor no es el propietario, se borra sin respuesta.
    if message.content.startswith("!") and message.author.id != OWNER_ID:
        try:
            await message.delete()
        except:
            pass
        return

    # Si el mensaje comienza con "!" y es del propietario, se procesa como comando sensible.
    if message.content.startswith("!") and message.author.id == OWNER_ID:
        await bot.process_commands(message)
        return

    if message.author.bot:
        return
    content = message.content.strip().lower()
    if content == "ranking":
        data = get_all_participants()
        sorted_players = sorted(data["participants"].items(), key=lambda item: int(item[1].get("puntos", 0)), reverse=True)
        user_id = str(message.author.id)
        found = False
        user_rank = 0
        for rank, (uid, player) in enumerate(sorted_players, 1):
            if uid == user_id:
                user_rank = rank
                found = True
                break
        stage_name = stage_names.get(current_stage, f"Etapa {current_stage}")
        if found:
            response = f"🏆 {message.author.display_name}, tu ranking en {stage_name} es el **{user_rank}** de {len(sorted_players)} y tienes {data['participants'][user_id].get('puntos', 0)} puntos."
        else:
            response = "❌ No estás registrado en el torneo."
        await message.channel.send(response)
        return
    if content == "topmejores":
        data = get_all_participants()
        sorted_players = sorted(data["participants"].items(), key=lambda item: int(item[1].get("puntos", 0)), reverse=True)
        stage_name = stage_names.get(current_stage, f"Etapa {current_stage}")
        ranking_text = f"🏅 Top 10 Mejores de {stage_name}:\n"
        for idx, (uid, player) in enumerate(sorted_players[:10], 1):
            ranking_text += f"{idx}. {player['nombre']} - {player.get('puntos', 0)} puntos\n"
        await message.channel.send(ranking_text)
        return
    if content in ["comandos", "lista de comandos"]:
        help_text = (
            "**Resumen de Comandos (Lenguaje Natural):**\n\n"
            "   - **ranking:** Muestra tu posición y puntaje individual (y si has sido eliminado).\n"
            "   - **topmejores:** Muestra el Top 10 Mejores de la etapa actual.\n"
            "   - **chiste** o **cuéntame un chiste:** Devuelve un chiste aleatorio.\n"
            "   - **quiero jugar trivia / jugar trivia / trivia:** Inicia una partida de trivia.\n"
            "   - **oráculo** o **predicción:** Recibe una predicción divertida.\n"
            "   - **meme** o **muéstrame un meme:** Muestra un meme aleatorio.\n"
            "   - **juguemos piedra papel tijeras, yo elijo [tu elección]:** Juega a Piedra, Papel o Tijeras.\n"
            "   - **duelo de chistes contra @usuario:** Inicia un duelo de chistes.\n"
        )
        await message.channel.send(help_text)
        return
    if content in ["chiste", "cuéntame un chiste"]:
        await message.channel.send(get_random_joke())
        return
    if any(phrase in content for phrase in ["quiero jugar trivia", "jugar trivia", "trivia"]):
        if message.channel.id not in active_trivia:
            trivia = random.choice(trivia_questions)
            active_trivia[message.channel.id] = trivia
            await message.channel.send(f"**Trivia:** {trivia['question']}\n_Responde en el chat._")
            return
    if message.channel.id in active_trivia:
        trivia = active_trivia[message.channel.id]
        if message.content.strip().lower() == trivia['answer'].lower():
            symbolic = award_symbolic_reward(message.author, 1)
            response = f"🎉 ¡Correcto, {message.author.display_name}! Has ganado 1 estrella simbólica. Ahora tienes {symbolic} estrellas."
            await message.channel.send(response)
            del active_trivia[message.channel.id]
            return
    if any(phrase in content for phrase in ["oráculo", "predicción"]):
        prediction = random.choice(predicciones)
        await message.channel.send(f"🔮 {prediction}")
        return
    if content in ["meme", "muéstrame un meme"]:
        meme_url = random.choice(MEMES)
        await message.channel.send(meme_url)
        return
    if any(phrase in content for phrase in ["juguemos piedra papel tijeras"]):
        opciones = ["piedra", "papel", "tijeras"]
        user_choice = next((op for op in opciones if op in content), None)
        if not user_choice:
            await message.channel.send("¿Cuál eliges? Indica piedra, papel o tijeras.")
            return
        bot_choice = random.choice(opciones)
        if user_choice == bot_choice:
            result = "¡Empate!"
        elif (user_choice == "piedra" and bot_choice == "tijeras") or \
             (user_choice == "papel" and bot_choice == "piedra") or \
             (user_choice == "tijeras" and bot_choice == "papel"):
            result = f"¡Ganaste! Yo elegí **{bot_choice}**."
            symbolic = award_symbolic_reward(message.author, 1)
            result += f" Ahora tienes {symbolic} estrellas."
        else:
            result = f"Perdiste. Yo elegí **{bot_choice}**. ¡Inténtalo de nuevo!"
        await message.channel.send(result)
        return
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
            duel_text += f"🎉 ¡El ganador es {winner.display_name}! Ahora tiene {symbolic} estrellas."
            await message.channel.send(duel_text)
            return
    await bot.process_commands(message)

######################################
# EVENTO ON_READY
######################################
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user.name}')

######################################
# SERVIDOR WEB MÍNIMO (para que Render detecte un puerto abierto)
######################################
app = Flask(__name__)

@app.route("/")
def home():
    return "El bot está funcionando!"

def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# Inicia el servidor Flask en un hilo separado
threading.Thread(target=run_webserver).start()

######################################
# INICIAR EL BOT
######################################
bot.run(os.getenv('DISCORD_TOKEN'))
