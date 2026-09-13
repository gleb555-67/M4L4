import config
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telebot import apihelper
apihelper.proxy = {'https': 'socks5://127.0.0.1:9150'}
import sqlite3

bot = telebot.TeleBot(config.API_TOKEN)

# ------------------- Инициализация БД -------------------
def init_db():
    conn = sqlite3.connect("movie_database.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY,
            title TEXT,
            year INTEGER,
            rating REAL,
            overview TEXT,
            img TEXT,
            genre TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER,
            movie_id INTEGER,
            PRIMARY KEY (user_id, movie_id),
            FOREIGN KEY (movie_id) REFERENCES movies (id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ------------------- Работа с БД (фильмы) -------------------
def get_movie_by_id(movie_id):
    conn = sqlite3.connect("movie_database.db")
    cur = conn.cursor()
    cur.execute("SELECT id, title, year, rating, overview, img, genre FROM movies WHERE id = ?", (movie_id,))
    row = cur.fetchone()
    conn.close()
    return row

def search_movies_by_title(query):
    conn = sqlite3.connect("movie_database.db")
    cur = conn.cursor()
    cur.execute("SELECT id, title, year, rating, overview, img, genre FROM movies WHERE LOWER(title) LIKE ?", ('%' + query.lower() + '%',))
    rows = cur.fetchall()
    conn.close()
    return rows

def search_movies_by_genre(genre):
    conn = sqlite3.connect("movie_database.db")
    cur = conn.cursor()
    cur.execute("SELECT id, title, year, rating, overview, img, genre FROM movies WHERE LOWER(genre) LIKE ?", ('%' + genre.lower() + '%',))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_all_unique_genres():
    conn = sqlite3.connect("movie_database.db")
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT genre FROM movies WHERE genre IS NOT NULL AND genre != ''")
    results = cur.fetchall()
    conn.close()
    genres_set = set()
    for (genre_str,) in results:
        parts = [g.strip() for g in genre_str.replace(';', ',').split(',') if g.strip()]
        genres_set.update(parts)
    return sorted(genres_set)

# ------------------- Работа с избранным -------------------
def is_favorite(user_id, movie_id):
    conn = sqlite3.connect("movie_database.db")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM favorites WHERE user_id=? AND movie_id=?", (user_id, movie_id))
    result = cur.fetchone() is not None
    conn.close()
    return result

def add_favorite(user_id, movie_id):
    conn = sqlite3.connect("movie_database.db")
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO favorites (user_id, movie_id) VALUES (?, ?)", (user_id, movie_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_favorite(user_id, movie_id):
    conn = sqlite3.connect("movie_database.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM favorites WHERE user_id=? AND movie_id=?", (user_id, movie_id))
    conn.commit()
    conn.close()

def get_favorites(user_id):
    conn = sqlite3.connect("movie_database.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id, m.title, m.year
        FROM movies m
        JOIN favorites f ON m.id = f.movie_id
        WHERE f.user_id = ?
        ORDER BY m.title
    """, (user_id,))
    results = cur.fetchall()
    conn.close()
    return results

# ------------------- Функции для формирования клавиатур -------------------
def get_favorite_button(movie_id, user_id):
    if is_favorite(user_id, movie_id):
        return InlineKeyboardButton("Удалить из избранного ❌", callback_data=f"remove_{movie_id}")
    else:
        return InlineKeyboardButton("Добавить в избранное 🌟", callback_data=f"favorite_{movie_id}")

def send_info(bot, message, row, show_favorite=True):
    movie_id, title, year, rating, overview, img, genre = row
    info = f"""
📍Название фильма:   {title}
📍Год:               {year}
📍Жанры:             {genre}
📍Рейтинг IMDB:      {rating}

🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻
{overview}
"""
    bot.send_photo(message.chat.id, img)
    if show_favorite:
        markup = InlineKeyboardMarkup()
        markup.row_width = 1
        markup.add(get_favorite_button(movie_id, message.chat.id))
        bot.send_message(message.chat.id, info, reply_markup=markup)
    else:
        bot.send_message(message.chat.id, info)

def main_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton('/random'), KeyboardButton('/genres'), KeyboardButton('/favorites'))
    return markup

# ------------------- Обработчики callback'ов -------------------
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.message.chat.id

    if call.data.startswith("favorite"):
        movie_id = int(call.data.split("_")[1])
        if add_favorite(user_id, movie_id):
            bot.answer_callback_query(call, "Фильм добавлен в избранное! ✅")
        else:
            bot.answer_callback_query(call, "Уже в избранном 😉")

    elif call.data.startswith("remove"):
        movie_id = int(call.data.split("_")[1])
        remove_favorite(user_id, movie_id)
        bot.answer_callback_query(call, "Фильм удалён из избранного ❌")

    elif call.data.startswith("movie_"):
        movie_id = int(call.data.split("_")[1])
        row = get_movie_by_id(movie_id)
        if row:
            send_info(bot, call.message, row, show_favorite=True)
            bot.answer_callback_query(call)
        else:
            bot.answer_callback_query(call, "Фильм не найден", show_alert=True)

    elif call.data.startswith("genre_"):
        genre = call.data.split("_", 1)[1]
        results = search_movies_by_genre(genre)
        if results:
            markup = InlineKeyboardMarkup(row_width=2)
            buttons = []
            for movie in results[:10]:
                movie_id, title, year, _, _, _, _ = movie
                buttons.append(InlineKeyboardButton(f"{title} ({year})", callback_data=f"movie_{movie_id}"))
            markup.add(*buttons)
            bot.send_message(
                call.message.chat.id,
                f"Фильмы в жанре '{genre}': (показаны первые 10)",
                reply_markup=markup
            )
            bot.answer_callback_query(call)
        else:
            bot.answer_callback_query(call, "В этом жанре фильмов не найдено", show_alert=True)

# ------------------- Обработчики команд -------------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        """Привет! Добро пожаловать в лучший кино-чат-бот🎥!
Здесь ты найдёшь 1000 фильмов 🔥
Нажми /random, чтобы получить случайный фильм,
напиши название фильма — я попытаюсь его найти,
используй /genres для просмотра всех жанров,
/favorites для просмотра избранного 🎬""",
        reply_markup=main_markup()
    )

@bot.message_handler(commands=['random'])
def random_movie(message):
    conn = sqlite3.connect("movie_database.db")
    cur = conn.cursor()
    cur.execute("SELECT id, title, year, rating, overview, img, genre FROM movies ORDER BY RANDOM() LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row:
        send_info(bot, message, row)
    else:
        bot.send_message(message.chat.id, "База данных пуста 😕")

@bot.message_handler(commands=['favorites'])
def show_favorites(message):
    user_id = message.chat.id
    favorites = get_favorites(user_id)
    if not favorites:
        bot.send_message(message.chat.id, "У вас пока нет избранных фильмов. Добавьте их через кнопку 'В избранное'!")
        return

    markup = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for movie_id, title, year in favorites:
        buttons.append(InlineKeyboardButton(f"{title} ({year})", callback_data=f"movie_{movie_id}"))
    markup.add(*buttons)
    bot.send_message(
        message.chat.id,
        f"Ваши избранные фильмы ({len(favorites)}):\nНажмите на фильм для подробностей.",
        reply_markup=markup
    )

@bot.message_handler(commands=['genres'])
def show_all_genres(message):
    genres = get_all_unique_genres()
    if not genres:
        bot.send_message(message.chat.id, "В базе данных нет жанров.")
        return

    markup = InlineKeyboardMarkup(row_width=3)
    buttons = [InlineKeyboardButton(genre, callback_data=f"genre_{genre}") for genre in genres]
    markup.add(*buttons)
    bot.send_message(
        message.chat.id,
        f"Все доступные жанры ({len(genres)}):\nНажмите на жанр, чтобы увидеть фильмы.",
        reply_markup=markup
    )

# ------------------- Обработчик текстовых сообщений (поиск по названию) -------------------
@bot.message_handler(func=lambda message: True)
def echo_message(message):
    # Поиск по названию
    rows = search_movies_by_title(message.text)
    if rows:
        if len(rows) == 1:
            bot.send_message(message.chat.id, "Конечно! Я знаю этот фильм😌")
            send_info(bot, message, rows[0])
        else:
            bot.send_message(message.chat.id, f"Найдено несколько фильмов по запросу '{message.text}':")
            markup = InlineKeyboardMarkup(row_width=2)
            buttons = []
            for movie in rows[:10]:
                movie_id, title, year, _, _, _, _ = movie
                buttons.append(InlineKeyboardButton(f"{title} ({year})", callback_data=f"movie_{movie_id}"))
            markup.add(*buttons)
            bot.send_message(message.chat.id, "Выберите нужный фильм:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Я не знаю такого фильма. Попробуйте найти по жанру через /genres.")

bot.infinity_polling()