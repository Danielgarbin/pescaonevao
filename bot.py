import discord
import psycopg2
import psycopg2.extras
from discord.ext import commands
import json
import random
import os
import re
import threading
import unicodedata
from flask import Flask, request, jsonify

######################################
# CONFIGURACIÓN: IDs y Servidor
######################################
OWNER_ID = 1336609089656197171         # Tu Discord ID (único autorizado para comandos sensibles)
PRIVATE_CHANNEL_ID = 1338130641354620988  # Canal privado para comandos sensibles (no se utiliza en la versión final)
PUBLIC_CHANNEL_ID  = 1338126297666424874  # Canal público donde se muestran resultados sensibles
SPECIAL_HELP_CHANNEL = 1337708244327596123  # Canal especial para que el owner reciba la lista extendida de comandos
GUILD_ID = 123456789012345678            # REEMPLAZA con el ID real de tu servidor (guild)

API_SECRET = os.environ.get("API_SECRET")  # Para la API privada (opcional)

######################################
# CONEXIÓN A LA BASE DE DATOS POSTGRESQL
######################################
DATABASE_URL = os.environ.get("DATABASE_URL")  # Usualmente la Internal Database URL de Render
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
                logros JSONB DEFAULT '[]'
            )
        """)
init_db()

######################################
# CONFIGURACIÓN INICIAL DEL TORNEO
######################################
PREFIX = '!'
# Configuración de etapas: cada etapa tiene un número determinado de jugadores.
STAGES = {1: 60, 2: 48, 3: 32, 4: 24, 5: 14}
current_stage = 1
stage_names = {
    1: "Battle Royale",
    2: "Snipers vs Runners",
    3: "Boxfight duos",
    4: "Pescadito dice",
    5: "Gran Final"
}

######################################
# VARIABLE GLOBAL PARA TRIVIA
######################################
active_trivia = {}  # key: channel.id, value: {"question": ..., "answer": ...}

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
            INSERT INTO participants (id, nombre, puntos, symbolic, etapa, logros)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                puntos = EXCLUDED.puntos,
                symbolic = EXCLUDED.symbolic,
                etapa = EXCLUDED.etapa,
                logros = EXCLUDED.logros
        """, (
            user_id,
            participant["nombre"],
            participant.get("puntos", 0),
            participant.get("symbolic", 0),
            participant.get("etapa", current_stage),
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
            "logros": []
        }
    current_symbolic = int(participant.get("symbolic", 0))
    new_symbolic = current_symbolic + reward
    participant["symbolic"] = new_symbolic
    upsert_participant(user_id, participant)
    return new_symbolic

######################################
# NORMALIZACIÓN DE CADENAS
######################################
def normalize_string(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).replace(" ", "").lower()

######################################
# CHISTES: 200 chistes originales para sacar carcajadas
######################################
ALL_JOKES = [
    "¿Por qué los programadores confunden Halloween y Navidad? Porque OCT 31 == DEC 25.",
    "¿Qué hace una abeja en el gimnasio? ¡Zum-ba!",
    "¿Por qué el libro de matemáticas estaba triste? Porque tenía demasiados problemas.",
    "¿Qué le dijo el cero al ocho? ¡Bonito cinturón!",
    "¿Por qué el tomate se puso rojo? Porque vio la ensalada desnuda.",
    "¿Qué hace una computadora en el baño? Navega en Internet.",
    "¿Por qué el pájaro no usa Facebook? Porque ya tiene Twitter.",
    "¿Qué le dijo un semáforo a otro? No me mires, me estoy cambiando.",
    "¿Por qué el elefante no usa computadora? Porque le tiene miedo al ratón.",
    "¿Qué hace un pez en el cine? Nada, solo va a ver la película.",
    "¿Por qué la escoba está feliz? Porque barrió con todo.",
    "¿Qué le dijo una taza a otra? ¡Qué taza tan bonita!",
    "¿Por qué el café no se ríe? Porque se toma muy en serio su espresso.",
    "¿Qué hace una abeja en el ordenador? Zumba en la red.",
    "¿Por qué el cartero nunca se pierde? Porque siempre sigue la dirección.",
    "¿Qué dijo la luna cuando vio al sol? ¡Qué radiante eres!",
    "¿Por qué el libro fue al hospital? Porque tenía un capítulo roto.",
    "¿Qué le dijo un espejo a otro? Nos vemos en la próxima reflexión.",
    "¿Por qué el reloj fue a la escuela? Porque quería aprender a dar la hora.",
    "¿Qué hace un plátano en el gimnasio? Se hace banana split.",
    "¿Por qué la bicicleta no puede parar de reír? Porque tiene dos ruedas de chiste.",
    "¿Qué le dijo el pan a la mantequilla? ¡Eres mi untable favorito!",
    "¿Por qué el perro se sentó en el sol? Porque quería ser un hot dog.",
    "¿Qué hace una araña en la computadora? Teje la web.",
    "¿Por qué el jardinero siempre está feliz? Porque florece cada día.",
    "¿Qué dijo el pato cuando vio una película? ¡Cuac, qué buena está!",
    "¿Por qué el zapato se puso a dieta? Porque tenía demasiadas suelas.",
    "¿Qué hace una oveja en la piscina? Nada, solo hace 'baa' de frío.",
    "¿Por qué el pájaro cantaba en la oficina? Porque era un ave de la risa.",
    "¿Qué dijo la naranja al exprimirse? ¡No me dejes sin zumo!",
    "¿Por qué el libro de chistes se sentía solo? Porque nadie lo leía.",
    "¿Qué hace un pez en el gimnasio? Nada, pero levanta aletas.",
    "¿Por qué el músico se perdió? Porque no encontró su nota.",
    "¿Qué dijo el semáforo en una discusión? ¡Alto ahí, no me mires!",
    "¿Por qué el queso no quiere jugar? Porque se siente muy 'gruyere'.",
    "¿Qué hace una fresa en la playa? Se pone en mermelada.",
    "¿Por qué el cartero se rió? Porque encontró una carta de amor.",
    "¿Qué le dijo la computadora al ratón? ¡Te sigo a todas partes!",
    "¿Por qué el huevo fue a la fiesta? Porque sabía que iba a romper la cáscara.",
    "¿Qué hace un árbol en el gimnasio? Levanta hojas.",
    "¿Por qué el pájaro usó sombrero? Porque quería ser 'pájaro de ala'.",
    "¿Qué le dijo un volcán a otro? ¡Tienes erupción de simpatía!",
    "¿Por qué el teléfono estaba enojado? Porque no le contestaban sus llamadas.",
    "¿Qué hace un semáforo en una carrera? Cambia de colores.",
    "¿Por qué la vaca fue al espacio? Para ver la luna de queso.",
    "¿Qué dijo el cartero al paquete? ¡Eres mi entrega favorita!",
    "¿Por qué el plátano se fue del supermercado? Porque se peló.",
    "¿Qué hace un ratón en el teatro? Actúa en 'ratonera'.",
    "¿Por qué el pez siempre es puntual? Porque nada le detiene.",
    "¿Qué dijo el helado al sol? ¡Me derrito de risa!",
    "¿Por qué la computadora fue al médico? Porque tenía virus de risa.",
    "¿Qué hace una luna en la biblioteca? Ilumina las lecturas.",
    "¿Por qué el perro se puso a estudiar? Porque quería ser un 'can-cer'.",
    "¿Qué le dijo el pez al anzuelo? ¡No me atrapes, soy libre!",
    "¿Por qué el gato se escondió en el teclado? Porque quería presionar teclas.",
    "¿Qué hace una manzana en la escuela? Aprende a ser una fruta madura.",
    "¿Por qué la silla fue al gimnasio? Porque quería ponerse a tono.",
    "¿Qué dijo el espejo cuando se rió? ¡Qué reflejo tan gracioso!",
    "¿Por qué el semáforo se fue de vacaciones? Para cambiar de color.",
    "¿Qué hace una bicicleta en la lluvia? Se moja las ruedas.",
    "¿Por qué el café se puso triste? Porque se enfrió su entusiasmo.",
    "¿Qué dijo la tostadora al pan? ¡Te haré un dorado chiste!",
    "¿Por qué el sol no juega cartas? Porque siempre quema la mano.",
    "¿Qué hace un globo en la oficina? Se infla de orgullo.",
    "¿Por qué el ratón se quedó en casa? Porque temía al gato de la vida real.",
    "¿Qué dijo la cebolla al cortarse? ¡Estoy llorando de felicidad!",
    "¿Por qué el cartero se fue a bailar? Porque quería entregar movimientos.",
    "¿Qué hace una galleta en la computadora? Se conecta a la red 'crujiente'.",
    "¿Por qué el reloj se rió? Porque marcó el tiempo de la diversión.",
    "¿Qué dijo el plátano al naranjo? ¡Eres cítrico y único!",
    "¿Por qué la lámpara se encendió de alegría? Porque vio una idea brillante.",
    "¿Qué hace un lápiz en el cine? Dibuja sonrisas.",
    "¿Por qué la alfombra se rió? Porque se sintió 'tapizada' de humor.",
    "¿Qué dijo el viento al árbol? ¡Te sacudí de la risa!",
    "¿Por qué el pez fue al gimnasio? Para mejorar su 'escama'.",
    "¿Qué hace una oveja en el teatro? Da un 'baa' de ovación.",
    "¿Por qué la planta baila? Porque tiene raíces de ritmo.",
    "¿Qué dijo el caracol al acelerar? ¡Voy con toda la 'cascarita'!",
    "¿Por qué el chocolate no quiere compartir? Porque es muy 'amargo' a veces.",
    "¿Qué hace un delfín en la biblioteca? Lee a carcajadas.",
    "¿Por qué la nube se fue de viaje? Para despejar sus ideas.",
    "¿Qué dijo el lápiz al cuaderno? ¡Eres mi mejor hoja de ruta!",
    "¿Por qué el dinosaurio no juega a las cartas? Porque ya es un 'ex-cazador'.",
    "¿Qué hace una taza en el gimnasio? Levanta 'café' fuerte.",
    "¿Por qué el globo se emocionó? Porque le dijeron que iba a volar alto.",
    "¿Qué dijo el cartero a la carta? ¡Eres mi envío favorito!",
    "¿Por qué la fresa no se rinde? Porque siempre se vuelve 'fresita' en cada intento.",
    "¿Qué hace una taza de té en la biblioteca? Se infunde de sabiduría.",
    "¿Por qué el ratón se inscribió en clases de baile? Para mejorar su 'movimiento'.",
    "¿Qué dijo la computadora a la impresora? ¡No te quedes sin tinta de humor!",
    "¿Por qué la escalera se rió? Porque siempre sube el ánimo.",
    "¿Qué hace un plátano en la orquesta? Da un 'solo' de sabor.",
    "¿Por qué la puerta se cerró de golpe? Porque estaba llena de 'bromas'.",
    "¿Qué dijo el café al despertarse? ¡Estoy espresso de felicidad!",
    "¿Por qué el teléfono se calló? Porque se quedó sin 'tono'.",
    "¿Qué hace un caracol en la autopista? Toma la vía lenta.",
    "¿Por qué el pastel se volvió famoso? Porque tenía la receta del éxito.",
    "¿Qué dijo el ventilador al calentarse? ¡Estoy enfriado de risa!",
    "¿Por qué la cebolla fue al circo? Para hacer llorar de risa a la gente.",
    "¿Qué hace una sandía en el desierto? Se derrite de tanto reír.",
    "¿Por qué el semáforo se volvió poeta? Porque siempre decía '¡Alto, belleza!'",
    "¿Qué hace un cartero en la playa? Entrega arena y sol.",
    "¿Por qué la computadora se puso nerviosa? Porque tenía demasiadas pestañas abiertas.",
    "¿Qué dijo el disco duro al USB? ¡Guarda tus secretos, yo tengo memoria!",
    "¿Por qué la impresora se fue de vacaciones? Porque necesitaba recargar tinta de vida.",
    "¿Qué hace una calculadora en una fiesta? Suma diversión.",
    "¿Por qué el robot se fue al bar? Porque necesitaba un poco de aceite para lubricar sus circuitos.",
    "¿Qué le dijo el café a la leche? ¡Juntos somos una mezcla perfecta!",
    "¿Por qué el ventilador siempre está relajado? Porque sabe cómo girar la situación.",
    "¿Qué dijo la batería al cargador? ¡Eres mi fuente de energía!",
    "¿Por qué el microondas es tan rápido? Porque siempre calienta el ambiente.",
    "¿Qué hace un cargador en el gimnasio? ¡Carga músculo!",
    "¿Por qué el smartphone se puso celoso? Porque el tablet tenía mejor pantalla.",
    "¿Qué le dijo el WiFi al router? ¡Conectemos nuestros corazones!",
    "¿Por qué el módem se rompió? Porque no pudo soportar tanta conexión.",
    "¿Qué hace una alarma en la mañana? Despierta las carcajadas.",
    "¿Por qué la lámpara fue a terapia? Porque tenía problemas de iluminación.",
    "¿Qué dijo la bombilla al interruptor? ¡Enciéndeme tu atención!",
    "¿Por qué la puerta se puso a bailar? Porque tenía bisagras con ritmo.",
    "¿Qué hace un libro en el supermercado? Busca ofertas de lectura.",
    "¿Por qué la pluma se puso a llorar? Porque se le acabó la tinta.",
    "¿Qué le dijo el cuaderno al bolígrafo? ¡Escribe, que te sigo la idea!",
    "¿Por qué el escritorio se sentía solo? Porque no tenía compañía de ideas.",
    "¿Qué hace una silla en la biblioteca? Se sienta a leer.",
    "¿Por qué la ventana se emocionó? Porque abrió nuevas perspectivas.",
    "¿Qué dijo el mantel a la mesa? ¡Eres el soporte de mis sueños!",
    "¿Por qué el microondas rompió el silencio? Porque siempre tenía algo caliente que decir.",
    "¿Qué hace un tostador en invierno? Calienta la mañana con alegría.",
    "¿Por qué la cafetera era tan popular? Porque siempre servía una buena taza de humor.",
    "¿Qué dijo el exprimidor a la fruta? ¡Exprime lo mejor de ti!",
    "¿Por qué la batidora estaba de buen humor? Porque mezclaba risas y alegría.",
    "¿Qué hace una olla en el fuego? Cocina chistes a fuego lento.",
    "¿Por qué el sartén se enamoró de la cuchara? Porque juntos hacían el mejor revuelto.",
    "¿Qué dijo la freidora al aceite? ¡Eres mi chispa de energía!",
    "¿Por qué el rallador era tan divertido? Porque siempre sacaba lo mejor de cada cosa.",
    "¿Qué hace una tapa en la olla? Mantiene los secretos del sabor.",
    "¿Por qué la jarra se llenó de alegría? Porque siempre servía buenos momentos.",
    "¿Qué dijo el vaso a la copa? ¡Brindemos por la amistad!",
    "¿Por qué la botella se sintió especial? Porque contenía la esencia de la diversión.",
    "¿Qué hace un sacacorchos en la cena? Abre la fiesta con estilo.",
    "¿Por qué la pizza se ríe? Porque siempre tiene rebanadas de humor.",
    "¿Qué dijo el helado al cono? ¡Juntos somos la combinación perfecta!",
    "¿Por qué el hot dog se puso contento? Porque siempre estaba en su punto.",
    "¿Qué hace una hamburguesa en la parrilla? Cocina chistes a la brasa.",
    "¿Por qué la ensalada es la comediante? Porque siempre mezcla risas y sabores.",
    "¿Qué dijo el sándwich al pan? ¡Juntos somos una gran broma!",
    "¿Por qué el postre se sentía triunfante? Porque siempre terminaba con broche de oro.",
    "¿Qué hace una galleta en el horno? Se dora de risa.",
    "¿Por qué el brownie se puso famoso? Porque tenía un toque de genialidad.",
    "¿Qué dijo el flan al caramelo? ¡Eres la dulzura de mi vida!",
    "¿Por qué el batido siempre está animado? Porque mezcla sabores y alegría.",
    "¿Qué hace un pastel en el cumpleaños? Crea momentos inolvidables.",
    "¿Por qué el merengue se ríe? Porque siempre está en las nubes de la diversión.",
    "¿Qué dijo el churro al chocolate? ¡Eres mi complemento perfecto!",
    "¿Por qué el café con leche se puso de moda? Porque siempre traía buena energía.",
    "¿Qué hace una tortilla en la sartén? Revuelve chistes a lo loco.",
    "¿Por qué el arroz se sintió especial? Porque siempre acompañaba los mejores momentos.",
    "¿Qué dijo el frijol a la lenteja? ¡Juntos somos la chispa de la comida!",
    "¿Por qué la paella fue a la fiesta? Porque sabía mezclar a todos con sabor.",
    "¿Qué hace una crema batida en el postre? Añade el toque final de dulzura.",
    "¿Por qué el zumo se sentía fresco? Porque siempre exprimía la risa.",
    "¿Qué dijo el té helado al verano? ¡Refresca mi humor!",
    "¿Por qué el chocolate caliente se abrazó? Porque derritía corazones.",
    "¿Qué hace una bebida en la fiesta? Brinda momentos de alegría.",
    "¿Por qué el licor se volvió poeta? Porque embriagaba de sentimientos.",
    "¿Qué dijo el cóctel a la fiesta? ¡Soy la mezcla perfecta de diversión!",
    "¿Por qué la soda se rió a carcajadas? Porque burbujeaba de felicidad.",
    "¿Qué hace una cerveza en el bar? Sirve risas en cada sorbo.",
    "¿Por qué el vino era tan elegante? Porque siempre brindaba por la vida.",
    "¿Qué dijo el champán en la celebración? ¡Burbujas de alegría para todos!",
    "¿Por qué el refresco se sintió animado? Porque siempre tenía chispa.",
    "¿Qué hace una limonada en el verano? Exprime el sol y la risa.",
    "¿Por qué el zumo de naranja fue invitado a la fiesta? Porque sabía dar vitamina de humor.",
    "¿Qué dijo el agua mineral al agitarse? ¡Siempre refresco el ambiente!",
    "¿Por qué el té de hierbas se volvió famoso? Porque tenía la receta de la calma y la risa.",
    "¿Qué hace una infusión en la tarde? Endulza los momentos con humor.",
    "¿Por qué la mermelada se sentía especial? Porque endulzaba cada día.",
    "¿Qué dijo el pan tostado al aguacate? ¡Juntos somos la tendencia del desayuno!",
    "¿Por qué el cereal se reía en la mañana? Porque siempre traía buen grano de humor.",
    "¿Qué hace una avena en el desayuno? Nutre el cuerpo y alegra el alma."
]
unused_jokes = ALL_JOKES.copy()

def get_random_joke():
    global unused_jokes, ALL_JOKES
    if not unused_jokes:
        unused_jokes = ALL_JOKES.copy()
    joke = random.choice(unused_jokes)
    unused_jokes.remove(joke)
    return joke

######################################
# TRIVIA: 200 preguntas de cultura general
######################################
ALL_TRIVIA = [
    {"question": "¿Quién escribió 'Cien Años de Soledad'?", "answer": "gabriel garcía márquez"},
    {"question": "¿Cuál es el río más largo del mundo?", "answer": "amazonas"},
    {"question": "¿En qué año llegó el hombre a la Luna?", "answer": "1969"},
    {"question": "¿Cuál es el planeta más cercano al Sol?", "answer": "mercurio"},
    {"question": "¿Cuál es el animal terrestre más rápido?", "answer": "guepardo"},
    {"question": "¿Cuántos planetas hay en el sistema solar?", "answer": "8"},
    {"question": "¿En qué continente se encuentra Egipto?", "answer": "áfrica"},
    {"question": "¿Cuál es el idioma más hablado en el mundo?", "answer": "chino"},
    {"question": "¿Qué instrumento mide la temperatura?", "answer": "termómetro"},
    {"question": "¿Cuál es la capital de Francia?", "answer": "parís"},
    {"question": "¿Cuál es el océano más grande del mundo?", "answer": "pacífico"},
    {"question": "¿En qué país se encuentra la Torre Eiffel?", "answer": "francia"},
    {"question": "¿Quién pintó la Mona Lisa?", "answer": "leonardo da vinci"},
    {"question": "¿Cuál es el idioma oficial de Brasil?", "answer": "portugués"},
    {"question": "¿Qué gas respiramos?", "answer": "oxígeno"},
    {"question": "¿Cuál es el animal más grande del planeta?", "answer": "ballena azul"},
    {"question": "¿En qué año comenzó la Segunda Guerra Mundial?", "answer": "1939"},
    {"question": "¿Quién descubrió América?", "answer": "cristóbal colón"},
    {"question": "¿Cuál es la montaña más alta del mundo?", "answer": "everest"},
    {"question": "¿Qué país tiene la mayor población?", "answer": "china"},
    {"question": "¿Cuál es el metal más valioso?", "answer": "oro"},
    {"question": "¿En qué continente se encuentra Australia?", "answer": "oceania"},
    {"question": "¿Quién escribió 'Don Quijote de la Mancha'?", "answer": "miguel de cervantes"},
    {"question": "¿Cuál es el río más largo de Europa?", "answer": "volga"},
    {"question": "¿Qué instrumento mide la presión atmosférica?", "answer": "barómetro"},
    {"question": "¿Cuál es el país más grande del mundo?", "answer": "rusia"},
    {"question": "¿En qué año cayó el Muro de Berlín?", "answer": "1989"},
    {"question": "¿Qué elemento tiene el símbolo 'Fe'?", "answer": "hierro"},
    {"question": "¿Cuál es la capital de Italia?", "answer": "roma"},
    {"question": "¿Quién escribió 'La Odisea'?", "answer": "homero"},
    {"question": "¿Cuál es la moneda oficial de Japón?", "answer": "yen"},
    {"question": "¿Qué planeta es conocido como el planeta rojo?", "answer": "marte"},
    {"question": "¿En qué país se encuentra el Taj Mahal?", "answer": "india"},
    {"question": "¿Cuál es la ciudad más poblada del mundo?", "answer": "tokio"},
    {"question": "¿Quién fue el primer presidente de Estados Unidos?", "answer": "george washington"},
    {"question": "¿Cuál es el símbolo químico del agua?", "answer": "h2o"},
    {"question": "¿Qué país es famoso por sus tulipanes?", "answer": "países bajos"},
    {"question": "¿Cuál es el continente más pequeño?", "answer": "oceania"},
    {"question": "¿Quién escribió 'Romeo y Julieta'?", "answer": "william shakespeare"},
    {"question": "¿Qué instrumento se usa para ver las estrellas?", "answer": "telescopio"},
    {"question": "¿Cuál es la capital de Alemania?", "answer": "berlín"},
    {"question": "¿En qué año se firmó la Declaración de Independencia de EE.UU.?", "answer": "1776"},
    {"question": "¿Qué país es conocido por su pizza y pasta?", "answer": "italia"},
    {"question": "¿Cuál es el principal gas de efecto invernadero?", "answer": "dióxido de carbono"},
    {"question": "¿Quién fue el inventor de la bombilla?", "answer": "thomas edison"},
    {"question": "¿Cuál es la capital de España?", "answer": "madrid"},
    {"question": "¿Qué deporte se juega en Wimbledon?", "answer": "tenis"},
    {"question": "¿En qué país se originó el sushi?", "answer": "japón"},
    {"question": "¿Cuál es el animal terrestre más pesado?", "answer": "elefante africano"},
    {"question": "¿Qué país es conocido como la tierra del sol naciente?", "answer": "japón"},
    {"question": "¿Cuál es el órgano más grande del cuerpo humano?", "answer": "piel"},
    {"question": "¿En qué año terminó la Primera Guerra Mundial?", "answer": "1918"},
    {"question": "¿Qué planeta tiene el anillo más famoso?", "answer": "saturno"},
    {"question": "¿Quién pintó 'La noche estrellada'?", "answer": "vincent van gogh"},
    {"question": "¿Cuál es el idioma oficial de Egipto?", "answer": "árabe"},
    {"question": "¿Qué instrumento se usa para medir el pH?", "answer": "pH-metro"},
    {"question": "¿Cuál es la capital de Canadá?", "answer": "ottawa"},
    {"question": "¿En qué continente se encuentra el desierto del Sahara?", "answer": "áfrica"},
    {"question": "¿Qué gas es esencial para la respiración de las plantas?", "answer": "dióxido de carbono"},
    {"question": "¿Quién escribió 'El Principito'?", "answer": "antoine de saint-exupéry"},
    {"question": "¿Cuál es el elemento más abundante en el universo?", "answer": "hidrógeno"},
    {"question": "¿Qué deporte es conocido como 'el rey'?", "answer": "fútbol"},
    {"question": "¿En qué país se originó el tango?", "answer": "argentina"},
    {"question": "¿Cuál es la capital de Australia?", "answer": "camberra"},
    {"question": "¿Quién descubrió la penicilina?", "answer": "alexander fleming"},
    {"question": "¿Cuál es el símbolo químico del oro?", "answer": "au"},
    {"question": "¿Qué instrumento se usa para medir la humedad?", "answer": "higrómetro"},
    {"question": "¿En qué año se fundó Roma?", "answer": "753 a.c."},
    {"question": "¿Cuál es el océano más profundo?", "answer": "pacífico"},
    {"question": "¿Qué país tiene la forma de una bota?", "answer": "italia"},
    {"question": "¿Quién es el autor de 'La Divina Comedia'?", "answer": "dante alighieri"},
    {"question": "¿Cuál es la capital de Rusia?", "answer": "moscú"},
    {"question": "¿En qué año cayó el Imperio Romano de Occidente?", "answer": "476"},
    {"question": "¿Qué instrumento mide la velocidad del viento?", "answer": "anemómetro"},
    {"question": "¿Cuál es la capital de China?", "answer": "beijing"},
    {"question": "¿Quién descubrió América en 1492?", "answer": "cristóbal colón"},
    {"question": "¿Cuál es el idioma oficial de Suiza?", "answer": "alemán, francés, italiano y romanche"},
    {"question": "¿Qué país es famoso por sus tulipanes y molinos?", "answer": "países bajos"},
    {"question": "¿En qué continente se encuentra el monte Kilimanjaro?", "answer": "áfrica"},
    {"question": "¿Quién pintó 'El Grito'?", "answer": "edvard munch"},
    {"question": "¿Cuál es la capital de Portugal?", "answer": "lisboa"},
    {"question": "¿En qué año se produjo la Revolución Francesa?", "answer": "1789"},
    {"question": "¿Qué animal es conocido como el rey de la selva?", "answer": "león"},
    {"question": "¿Cuál es el símbolo químico de la plata?", "answer": "ag"},
    {"question": "¿Quién escribió 'La Metamorfosis'?", "answer": "franz kafka"},
    {"question": "¿Cuál es la capital de Grecia?", "answer": "atenas"},
    {"question": "¿En qué año se firmó el Tratado de Versalles?", "answer": "1919"},
    {"question": "¿Qué instrumento se utiliza para medir la tierra?", "answer": "geómetro"},
    {"question": "¿Cuál es el país más pequeño del mundo?", "answer": "vaticano"},
    {"question": "¿Quién fue el primer hombre en el espacio?", "answer": "yuri gagarin"},
    {"question": "¿Cuál es la capital de India?", "answer": "nueva delhi"},
    {"question": "¿En qué continente se encuentra la Patagonia?", "answer": "américa del sur"},
    {"question": "¿Qué elemento químico tiene el símbolo 'C'?", "answer": "carbono"},
    {"question": "¿Quién escribió 'Hamlet'?", "answer": "william shakespeare"},
    {"question": "¿Cuál es el planeta más grande del sistema solar?", "answer": "júpiter"},
    {"question": "¿En qué año se inauguró el Canal de Panamá?", "answer": "1914"},
    {"question": "¿Qué país es conocido por el carnaval de Río?", "answer": "brasil"},
    {"question": "¿Cuál es la capital de Sudáfrica?", "answer": "pretoria (administrativa)"},
    {"question": "¿Quién pintó 'Guernica'?", "answer": "pablo picasso"},
    {"question": "¿Qué instrumento mide la intensidad sísmica?", "answer": "sismógrafo"},
    {"question": "¿Cuál es el nombre de la estrella más cercana a la Tierra?", "answer": "sol"},
    {"question": "¿En qué año se descubrió el fuego?", "answer": "prehistórico"},
    {"question": "¿Qué país tiene más islas en el mundo?", "answer": "suecia"},
    {"question": "¿Quién escribió 'El Señor de los Anillos'?", "answer": "j. r. r. tolkien"},
    {"question": "¿Cuál es el río más largo de Asia?", "answer": "yangtsé"},
    {"question": "¿En qué país se encuentra Machu Picchu?", "answer": "perú"},
    {"question": "¿Qué científico desarrolló la teoría de la relatividad?", "answer": "albert einstein"},
    {"question": "¿Cuál es la capital de Corea del Sur?", "answer": "seúl"},
    {"question": "¿En qué año se fundó Microsoft?", "answer": "1975"},
    {"question": "¿Qué país es conocido por su chocolate y relojes?", "answer": "suiza"},
    {"question": "¿Cuál es el símbolo químico del platino?", "answer": "pt"},
    {"question": "¿Quién escribió '1984'?", "answer": "george orwell"},
    {"question": "¿Cuál es la capital de Noruega?", "answer": "oslo"},
    {"question": "¿En qué continente se encuentra la Antártida?", "answer": "antártida"},
    {"question": "¿Qué animal es el símbolo de Australia?", "answer": "canguro"},
    {"question": "¿Quién fue el primer hombre en pisar la Luna?", "answer": "neil armstrong"},
    {"question": "¿Cuál es el deporte nacional de Japón?", "answer": "sumo"},
    {"question": "¿En qué año se produjo la caída del Muro de Berlín?", "answer": "1989"},
    {"question": "¿Qué país es famoso por sus pirámides?", "answer": "egipto"},
    {"question": "¿Cuál es el instrumento musical de cuerdas más antiguo?", "answer": "arpa"},
    {"question": "¿Quién escribió 'El Quijote'?", "answer": "miguel de cervantes"},
    {"question": "¿Cuál es el idioma oficial de Israel?", "answer": "hebreo"},
    {"question": "¿En qué continente se encuentra Islandia?", "answer": "europa"},
    {"question": "¿Qué científico es conocido por sus leyes del movimiento?", "answer": "isaac newton"},
    {"question": "¿Cuál es la capital de Turquía?", "answer": "ancara"},
    {"question": "¿En qué año se descubrió América?", "answer": "1492"},
    {"question": "¿Qué país tiene la mayor extensión territorial?", "answer": "rusia"},
    {"question": "¿Cuál es el principal componente del sol?", "answer": "hidrógeno"},
    {"question": "¿Quién pintó 'La última cena'?", "answer": "leonardo da vinci"},
    {"question": "¿Cuál es la capital de México?", "answer": "ciudad de méxico"},
    {"question": "¿En qué año se inventó el teléfono?", "answer": "1876"},
    {"question": "¿Qué país es conocido por el sushi?", "answer": "japón"},
    {"question": "¿Cuál es el órgano encargado de bombear sangre en el cuerpo humano?", "answer": "corazón"},
    {"question": "¿Quién escribió 'El Hobbit'?", "answer": "j. r. r. tolkien"},
    {"question": "¿Cuál es la capital de Arabia Saudita?", "answer": "riyadh"},
    {"question": "¿En qué año se inauguró el metro de Londres?", "answer": "1863"},
    {"question": "¿Qué país es famoso por sus samuráis?", "answer": "japón"},
    {"question": "¿Cuál es el símbolo químico del hierro?", "answer": "fe"},
    {"question": "¿Quién fue el primer ministro del Reino Unido durante la Segunda Guerra Mundial?", "answer": "winston churchill"},
    {"question": "¿Cuál es la capital de Argentina?", "answer": "buenos aires"},
    {"question": "¿En qué año se lanzó el primer iPhone?", "answer": "2007"},
    {"question": "¿Qué país es conocido por el carnaval de Venecia?", "answer": "italia"},
    {"question": "¿Cuál es la moneda oficial del Reino Unido?", "answer": "libra esterlina"},
    {"question": "¿Quién escribió 'El retrato de Dorian Gray'?", "answer": "oscar wilde"},
    {"question": "¿Cuál es la capital de Suecia?", "answer": "estocolmo"},
    {"question": "¿En qué año se abolió la esclavitud en Estados Unidos?", "answer": "1865"},
    {"question": "¿Qué país es conocido por su Oktoberfest?", "answer": "alemania"},
    {"question": "¿Cuál es el animal nacional de Canadá?", "answer": "castor"},
    {"question": "¿Quién pintó 'La persistencia de la memoria'?", "answer": "salvador dalí"},
    {"question": "¿Cuál es la capital de Holanda?", "answer": "ámsterdam"},
    {"question": "¿En qué año se descubrió la electricidad?", "answer": "siglo xviii"},
    {"question": "¿Qué país es famoso por el whisky?", "answer": "escocia"},
    {"question": "¿Cuál es el elemento químico con el símbolo 'Na'?", "answer": "sodio"},
    {"question": "¿Quién escribió 'Crimen y Castigo'?", "answer": "fiódor dostoyevski"},
    {"question": "¿Cuál es la capital de Bélgica?", "answer": "bruselas"},
    {"question": "¿En qué año se fundó la Organización de las Naciones Unidas (ONU)?", "answer": "1945"},
    {"question": "¿Qué deporte se juega en el Tour de Francia?", "answer": "ciclismo"},
    {"question": "¿Cuál es la montaña más alta de América?", "answer": "aconcagua"},
    {"question": "¿Quién pintó 'El nacimiento de Venus'?", "answer": "sandro botticelli"},
    {"question": "¿Cuál es el principal ingrediente del guacamole?", "answer": "aguacate"},
    {"question": "¿En qué año se fundó Apple Inc.?", "answer": "1976"},
    {"question": "¿Qué país es conocido por su samba?", "answer": "brasil"},
    {"question": "¿Cuál es la capital de Dinamarca?", "answer": "copenhague"},
    {"question": "¿Quién escribió 'El Alquimista'?", "answer": "paulo coelho"},
    {"question": "¿Cuál es el símbolo químico del plomo?", "answer": "pb"},
    {"question": "¿En qué país se encuentra la Gran Muralla?", "answer": "china"},
    {"question": "¿Qué instrumento mide la concentración de iones?", "answer": "electrómetro"},
    {"question": "¿Cuál es la capital de Finlandia?", "answer": "helinski"},
    {"question": "¿Quién fue el autor de 'El Perfume'?", "answer": "patrick suskind"},
    {"question": "¿En qué año se inventó la imprenta?", "answer": "1440"},
    {"question": "¿Qué país es conocido por sus fjords?", "answer": "noruega"},
    {"question": "¿Cuál es el órgano encargado de filtrar la sangre?", "answer": "riñón"},
    {"question": "¿Quién pintó 'Las Meninas'?", "answer": "diego velázquez"},
    {"question": "¿Cuál es la capital de Polonia?", "answer": "varsovia"},
    {"question": "¿En qué año se lanzó el primer satélite artificial, el Sputnik?", "answer": "1957"},
    {"question": "¿Qué país es conocido por su cerveza y salchichas?", "answer": "alemania"},
    {"question": "¿Cuál es el símbolo químico del carbono?", "answer": "c"},
    {"question": "¿Quién escribió 'El nombre de la rosa'?", "answer": "umberto eco"},
    {"question": "¿Cuál es la capital de Nueva Zelanda?", "answer": "wellington"},
    {"question": "¿En qué año se celebraron los primeros Juegos Olímpicos modernos?", "answer": "1896"},
    {"question": "¿Qué país es famoso por sus paisajes alpinos?", "answer": "suiza"},
    {"question": "¿Cuál es el principal componente del aire?", "answer": "nitrógeno"},
    {"question": "¿Quién fue el primer hombre en escalar el Everest?", "answer": "edmund hillary y tenzing norgay"},
    {"question": "¿Cuál es la capital de Irlanda?", "answer": "dublín"},
    {"question": "¿En qué año se fundó la Unión Europea?", "answer": "1993"},
    {"question": "¿Qué país es conocido por el flamenco?", "answer": "españa"},
    {"question": "¿Cuál es el símbolo químico del mercurio?", "answer": "hg"},
    {"question": "¿Quién escribió 'Fahrenheit 451'?", "answer": "ray bradbury"},
    {"question": "¿Cuál es la capital de Austria?", "answer": "viena"},
    {"question": "¿En qué año se creó Facebook?", "answer": "2004"},
    {"question": "¿Qué país es famoso por sus castillos y lagos?", "answer": "suiza"},
    {"question": "¿Cuál es el principal componente de las estrellas?", "answer": "hidrógeno"},
    {"question": "¿Quién pintó 'La Gioconda'?", "answer": "leonardo da vinci"},
    {"question": "¿Cuál es la capital de Indonesia?", "answer": "jacarta"},
    {"question": "¿En qué año se fundó la ciudad de Roma?", "answer": "753 a.c."},
    {"question": "¿Qué país es conocido por el whisky y los Highlands?", "answer": "escocia"},
    {"question": "¿Cuál es el símbolo químico del potasio?", "answer": "k"},
    {"question": "¿Quién escribió 'Matar a un ruiseñor'?", "answer": "harper lee"},
    {"question": "¿Cuál es la capital de Egipto?", "answer": "el cairo"},
    {"question": "¿En qué año se celebró la primera Copa del Mundo de Fútbol?", "answer": "1930"}
]
unused_trivia = ALL_TRIVIA.copy()

def get_random_trivia():
    global unused_trivia, ALL_TRIVIA
    if not unused_trivia:
        unused_trivia = ALL_TRIVIA.copy()
    trivia = random.choice(unused_trivia)
    unused_trivia.remove(trivia)
    return trivia

######################################
# INICIALIZACIÓN DEL BOT
######################################
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

async def send_public_message(message: str):
    public_channel = bot.get_channel(PUBLIC_CHANNEL_ID)
    if public_channel:
        await public_channel.send(message)
    else:
        print("No se pudo encontrar el canal público.")

######################################
# ENDPOINTS DE LA API PRIVADA
######################################
app = Flask(__name__)

def check_auth(req):
    auth = req.headers.get("Authorization")
    if not auth or auth != f"Bearer {API_SECRET}":
        return False
    return True

@app.route("/", methods=["GET"])
def home_page():
    return "El bot está funcionando!", 200

@app.route("/api/update_points", methods=["POST"])
def api_update_points():
    if not check_auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    if not data or "member_id" not in data or "points" not in data:
        return jsonify({"error": "Missing parameters"}), 400
    try:
        member_id = int(data["member_id"])
        points = int(data["points"])
    except ValueError:
        return jsonify({"error": "Invalid parameters"}), 400
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return jsonify({"error": "Guild not found"}), 404
    try:
        member = guild.get_member(member_id)
        if member is None:
            member = bot.loop.run_until_complete(guild.fetch_member(member_id))
    except Exception as e:
        return jsonify({"error": "Member not found", "details": str(e)}), 404
    new_points = update_score(member, points)
    bot.loop.create_task(send_public_message(f"✅ API: Puntuación actualizada: {member.display_name} ahora tiene {new_points} puntos"))
    return jsonify({"message": "Puntuación actualizada", "new_points": new_points}), 200

@app.route("/api/delete_member", methods=["POST"])
def api_delete_member():
    if not check_auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    if not data or "member_id" not in data:
        return jsonify({"error": "Missing parameter: member_id"}), 400
    try:
        member_id = int(data["member_id"])
    except ValueError:
        return jsonify({"error": "Invalid member_id"}), 400
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return jsonify({"error": "Guild not found"}), 404
    try:
        member = guild.get_member(member_id)
        if member is None:
            member = bot.loop.run_until_complete(guild.fetch_member(member_id))
    except Exception as e:
        return jsonify({"error": "Member not found", "details": str(e)}), 404
    with conn.cursor() as cur:
        cur.execute("DELETE FROM participants WHERE id = %s", (str(member.id),))
    bot.loop.create_task(send_public_message(f"✅ API: {member.display_name} eliminado del torneo"))
    return jsonify({"message": "Miembro eliminado"}), 200

@app.route("/api/set_stage", methods=["POST"])
def api_set_stage():
    if not check_auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    if not data or "stage" not in data:
        return jsonify({"error": "Missing parameter: stage"}), 400
    try:
        stage = int(data["stage"])
    except ValueError:
        return jsonify({"error": "Invalid stage"}), 400
    global current_stage
    current_stage = stage
    bot.loop.create_task(send_public_message(f"✅ API: Etapa actual configurada a {stage}"))
    return jsonify({"message": "Etapa configurada", "stage": stage}), 200

######################################
# COMANDOS SENSIBLES DE DISCORD (con “!” – Solo el Propietario en el canal autorizado)
######################################
@bot.command()
async def actualizar_puntuacion(ctx, jugador: str, puntos: int):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    match = re.search(r'\d+', jugador)
    if not match:
        await send_public_message("No se pudo encontrar al miembro.")
        await ctx.message.delete()
        return
    member_id = int(match.group())
    guild = ctx.guild or bot.get_guild(GUILD_ID)
    if guild is None:
        await send_public_message("No se pudo determinar el servidor.")
        await ctx.message.delete()
        return
    try:
        member = guild.get_member(member_id)
        if member is None:
            member = await guild.fetch_member(member_id)
    except Exception as e:
        await send_public_message("No se pudo encontrar al miembro en el servidor.")
        await ctx.message.delete()
        return
    try:
        puntos = int(puntos)
    except ValueError:
        await send_public_message("Por favor, proporciona un número válido de puntos.")
        await ctx.message.delete()
        return
    new_points = update_score(member, puntos)
    await send_public_message(f"✅ Puntuación actualizada: {member.display_name} ahora tiene {new_points} puntos")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def reducir_puntuacion(ctx, jugador: str, puntos: int):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
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
    participant = get_participant(str(ctx.author.id))
    if participant:
        await ctx.send(f"🏆 Tu puntaje del torneo es: {participant.get('puntos', 0)}")
    else:
        await ctx.send("❌ No estás registrado en el torneo")

@bot.command()
async def clasificacion(ctx):
    data = get_all_participants()
    sorted_players = sorted(data["participants"].items(), key=lambda item: int(item[1].get("puntos", 0)), reverse=True)
    ranking = "🏅 Clasificación del Torneo:\n"
    for idx, (uid, player) in enumerate(sorted_players, 1):
        ranking += f"{idx}. {player['nombre']} - {player.get('puntos', 0)} puntos\n"
    await ctx.send(ranking)

@bot.command()
async def avanzar_etapa(ctx):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage
    current_stage += 1
    data = get_all_participants()
    sorted_players = sorted(data["participants"].items(), key=lambda item: int(item[1].get("puntos", 0)), reverse=True)
    cutoff = STAGES.get(current_stage)
    if cutoff is None:
        await send_public_message("No hay configuración para esta etapa.")
        await ctx.message.delete()
        return
    avanzan = sorted_players[:cutoff]
    eliminados = sorted_players[cutoff:]
    for uid, player in avanzan:
        player["etapa"] = current_stage
        upsert_participant(uid, player)
        try:
            member = ctx.guild.get_member(int(uid)) or await ctx.guild.fetch_member(int(uid))
            await member.send(f"🎉 ¡Felicidades! Has avanzado a la etapa {current_stage} ({stage_names.get(current_stage, 'Etapa ' + str(current_stage))}).")
        except Exception as e:
            print(f"Error al enviar mensaje a {uid}: {e}")
    for uid, player in eliminados:
        try:
            member = ctx.guild.get_member(int(uid)) or await ctx.guild.fetch_member(int(uid))
            await member.send(f"❌ Lo siento, has sido eliminado del torneo en la etapa {current_stage - 1}.")
        except Exception as e:
            print(f"Error al enviar mensaje a {uid}: {e}")
    await send_public_message(f"✅ Etapa {current_stage} iniciada. {cutoff} jugadores avanzaron y {len(eliminados)} fueron eliminados.")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def retroceder_etapa(ctx):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    global current_stage
    if current_stage <= 1:
        await send_public_message("No se puede retroceder de la etapa 1.")
        try:
            await ctx.message.delete()
        except:
            pass
        return
    current_stage -= 1
    data = get_all_participants()
    for uid, player in data["participants"].items():
        player["etapa"] = current_stage
        upsert_participant(uid, player)
    await send_public_message(f"✅ Etapa retrocedida. Ahora la etapa es {current_stage} ({stage_names.get(current_stage, 'Etapa ' + str(current_stage))}).")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def eliminar_jugador(ctx, jugador: str):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    match = re.search(r'\d+', jugador)
    if not match:
        await send_public_message("No se pudo encontrar al miembro.")
        await ctx.message.delete()
        return
    member_id = int(match.group())
    guild = ctx.guild or bot.get_guild(GUILD_ID)
    if guild is None:
        await send_public_message("No se pudo determinar el servidor.")
        await ctx.message.delete()
        return
    try:
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
    except Exception as e:
        await send_public_message("No se pudo encontrar al miembro en el servidor.")
        await ctx.message.delete()
        return
    user_id = str(member.id)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM participants WHERE id = %s", (user_id,))
    await send_public_message(f"✅ {member.display_name} eliminado del torneo")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def configurar_etapa(ctx, etapa: int):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
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

# Comando !trivia (disponible para el owner; los demás inician trivia por lenguaje natural)
@bot.command()
async def trivia(ctx):
    if ctx.author.id != OWNER_ID or ctx.channel.id != PUBLIC_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except:
            pass
        return
    if ctx.channel.id in active_trivia:
        await ctx.send("Ya hay una trivia activa en este canal.")
        return
    trivia_item = get_random_trivia()
    active_trivia[ctx.channel.id] = trivia_item
    await ctx.send(f"**Trivia:** {trivia_item['question']}\n_Responde en el chat._")
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def chiste(ctx):
    await ctx.send(get_random_joke())

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

    global stage_names, current_stage, active_trivia

    def normalize_string_local(s):
        return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).replace(" ", "").lower()

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

    if content == "topestrellas":
        data = get_all_participants()
        sorted_by_symbolic = sorted(data["participants"].items(), key=lambda item: int(item[1].get("symbolic", 0)), reverse=True)
        ranking_text = "🌟 Top 10 Estrellas Simbólicas:\n"
        for idx, (uid, player) in enumerate(sorted_by_symbolic[:10], 1):
            ranking_text += f"{idx}. {player['nombre']} - {player.get('symbolic', 0)} estrellas\n"
        await message.channel.send(ranking_text)
        return

    if content in ["comandos", "lista de comandos"]:
        help_text = (
            "**Resumen de Comandos (Lenguaje Natural):**\n\n"
            "   - **ranking:** Muestra tu posición y puntaje del torneo.\n"
            "   - **topmejores:** Muestra el ranking de los 10 jugadores con mayor puntaje del torneo.\n"
            "   - **misestrellas:** Muestra cuántas estrellas simbólicas tienes.\n"
            "   - **topestrellas:** Muestra el ranking de los 10 jugadores con más estrellas simbólicas.\n"
            "   - **chiste** o **cuéntame un chiste:** Devuelve un chiste aleatorio.\n"
            "   - **quiero jugar trivia / jugar trivia / trivia:** Inicia una partida de trivia; si respondes correctamente, ganas 1 estrella simbólica.\n"
            "   - **oráculo** o **predicción:** Recibe una predicción divertida.\n"
            "   - **meme** o **muéstrame un meme:** Muestra un meme aleatorio.\n"
            "   - **juguemos piedra papel tijeras, yo elijo [tu elección]:** Juega a Piedra, Papel o Tijeras; si ganas, ganas 1 estrella simbólica.\n"
            "   - **duelo de chistes contra @usuario:** Inicia un duelo de chistes; el ganador gana 1 estrella simbólica.\n"
        )
        # Si el autor es el owner y lo escribe en el canal especial, se agregan además los comandos sensibles.
        if message.author.id == OWNER_ID and message.channel.id == SPECIAL_HELP_CHANNEL:
            help_text += "\n**Comandos Sensibles (!):**\n"
            help_text += (
                "   - **!actualizar_puntuacion [jugador] [puntos]:** Actualiza la puntuación de un jugador.\n"
                "   - **!reducir_puntuacion [jugador] [puntos]:** Resta puntos a un jugador.\n"
                "   - **!ver_puntuacion:** Muestra tu puntaje actual del torneo.\n"
                "   - **!clasificacion:** Muestra la clasificación completa del torneo.\n"
                "   - **!avanzar_etapa:** Avanza a la siguiente etapa del torneo y notifica a los jugadores.\n"
                "   - **!retroceder_etapa:** Retrocede a la etapa anterior del torneo.\n"
                "   - **!eliminar_jugador [jugador]:** Elimina a un jugador del torneo.\n"
                "   - **!configurar_etapa [etapa]:** Configura manualmente la etapa actual del torneo.\n"
            )
        await message.channel.send(help_text)
        return

    if content == "misestrellas":
        participant = get_participant(str(message.author.id))
        symbolic = 0
        if participant:
            try:
                symbolic = int(participant.get("symbolic", 0))
            except:
                symbolic = 0
        await message.channel.send(f"🌟 {message.author.display_name}, tienes {symbolic} estrellas simbólicas.")
        return

    if content in ["chiste", "cuéntame un chiste"]:
        await message.channel.send(get_random_joke())
        return

    if any(phrase in content for phrase in ["quiero jugar trivia", "jugar trivia", "trivia"]):
        if message.channel.id not in active_trivia:
            trivia_item = get_random_trivia()
            active_trivia[message.channel.id] = trivia_item
            await message.channel.send(f"**Trivia:** {trivia_item['question']}\n_Responde en el chat._")
            return

    if message.channel.id in active_trivia:
        trivia_item = active_trivia[message.channel.id]
        if normalize_string_local(message.content.strip()) == normalize_string_local(trivia_item['answer']):
            symbolic = award_symbolic_reward(message.author, 1)
            response = f"🎉 ¡Correcto, {message.author.display_name}! Has ganado 1 estrella simbólica. Ahora tienes {symbolic} estrellas simbólicas."
            await message.channel.send(response)
            del active_trivia[message.channel.id]
            return

    if any(phrase in content for phrase in ["oráculo", "predicción"]):
        prediction = random.choice([
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
        ])
        await message.channel.send(f"🔮 {prediction}")
        return

    if content in ["meme", "muéstrame un meme"]:
        MEMES = [
            "https://i.imgflip.com/1bij.jpg",
            "https://i.imgflip.com/26am.jpg",
            "https://i.imgflip.com/30b1gx.jpg",
            "https://i.imgflip.com/3si4.jpg",
            "https://i.imgflip.com/2fm6x.jpg"
        ]
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
            result += f" Has ganado 1 estrella simbólica. Ahora tienes {symbolic} estrellas simbólicas."
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
            duel_text += f"🎉 ¡El ganador es {winner.display_name}! Ha ganado 1 estrella simbólica. Ahora tiene {symbolic} estrellas simbólicas."
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
# SERVIDOR WEB PARA MANTENER EL BOT ACTIVO (API PRIVADA)
######################################
def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    threading.Thread(target=run_webserver).start()
    bot.run(os.getenv('DISCORD_TOKEN'))
