import re
from datetime import datetime
import logging
from urllib.parse import urlparse
import requests
from cryptography.fernet import Fernet
from aiogram import Bot, Dispatcher, executor, types
from netschoolapi import NetSchoolAPI, errors
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import Text
import sqlite3

cipher = Fernet('FERNET_TOKEN')

bot = Bot(token='BOT_TOKEN', parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)


def get_keyboard():
    '''Клавиатура регистрации'''
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton('Регистрация'))
    return kb


def get_cancel():
    '''Клавиатура отмены'''
    return types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton('/cancel'))


class Standard(StatesGroup):
    '''Класс состояний покоя'''
    standard = State()


class Registrations(StatesGroup):
    '''Класс состояний регистрации'''
    waiting_for_url = State()
    waiting_for_login = State()
    waiting_for_password = State()
    waiting_for_school = State()
    confirm_school = State()
    finishing_registration = State()


class Settings(StatesGroup):
    '''Класс состояний настроек'''
    menu = State()
    delete_account = State()
    author = State()
    auto_alert = State()


def get_kb_stand():
    '''Стандартная клавиатура'''
    buttons = ['🕒Расписание уроков']
    buttons1 = ['📖Домашка']
    buttons2 = ['⚙Настройки']

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(*buttons)
    kb.add(*buttons1)
    kb.add(*buttons2)
    return kb


class Functions:

    def __init__(self, id_user):
        self.id_user = id_user

    def get_user_data(self):
        try:
            sqlite_connection = sqlite3.connect('data_base.db')
            cursor = sqlite_connection.cursor()

            sql_select_query = """select * from users_data_base where id = ?"""
            cursor.execute(sql_select_query, (self.id_user,))
            records = cursor.fetchall()

            for row in records:
                url = row[3]
                login = str(row[4])
                password = str(row[5])
                school = row[6]

            login = login[2:len(login) - 1]
            password = password[2:len(password) - 1]

            login_de = cipher.decrypt(login, ttl=None).decode('utf-8')
            password_de = cipher.decrypt(password, ttl=None).decode('utf-8')

            return [url, login_de, password_de, school]

        except sqlite_connection.Error as error:
            print(error, datetime.today(), ' ', datetime.time())

    def delete_user_data(self):

        sqlite_connection = sqlite3.connect('data_base.db')
        cursor = sqlite_connection.cursor()

        sql_select_query = """DELETE FROM users_data_base WHERE id = ?"""
        cursor.execute(sql_select_query, (self.id_user,))
        sqlite_connection.commit()
        cursor.close()

    async def get_schedule(self, day_int, day):
        """Получение расписания"""

        func = Functions(id_user=self.id_user)
        auth = func.get_user_data()

        try:
            ns = NetSchoolAPI(auth[0])
            await ns.login(
                auth[1],
                auth[2],
                auth[3]
            )
            tmp = await ns.diary()

            schedule_data = tmp.schedule[day_int]
            null = [f'Вот Ваше расписание на {day}:\n']

            six_days = len(tmp.schedule) > 5

            for lesson in schedule_data.lessons:
                start = str(lesson.start)
                end = str(lesson.end)
                l1 = len(start)
                l2 = len(end)

                start_n = start[:l1 - 3]
                end_n = end[:l2 - 3]
                ex = str(lesson.number) + ") " + lesson.subject + " " + f"<b>{start_n}</b>" + " - " + f"<b>{end_n}</b>"
                null.append(ex)
            await ns.logout()

            return [null, six_days]
        except IndexError:
            return [[f'Расписания на {day} нет'], True]

    async def get_homework(self, day_int, day):
        """Получение домашнего задания"""

        func = Functions(id_user=self.id_user)
        auth = func.get_user_data()

        try:
            ns = NetSchoolAPI(auth[0])
            await ns.login(
                auth[1],
                auth[2],
                auth[3]
            )
            tmp = await ns.diary()

            schedule_data = tmp.schedule[day_int]
            null = [f'Вот Ваша домашка на {day}:\n']

            six_days = len(tmp.schedule) > 5

            for lesson in schedule_data.lessons:

                if len(lesson.assignments) != 0:
                    name = lesson.subject
                    homework_data = lesson.assignments[0].content
                    comment = lesson.assignments[0].comment
                    is_duty = lesson.assignments[0].is_duty
                    number = str(lesson.number)

                    ex = number + ') ' + f"<b><u>{name}</u></b>" + '\n' + f"<i>{homework_data}</i>\n"
                    if comment != '':
                        ex += f'<b>Комментарий от учителя:</b> {comment}\n'
                    if is_duty:
                        ex += f"❗<b>Обязательно к сдаче</b>\n"
                    null.append(ex)

            await ns.logout()
            return [null, six_days]
        except IndexError:
            return [[f'Домашнего задания на {day} нет'], True]


@dp.message_handler(commands='start', state="*")
async def start(message: types.Message):
    '''Обработчик команды /start'''
    conn = sqlite3.connect('data_base.db')
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users_data_base WHERE id = ?", (message.from_user.id,))

    if cursor.fetchone() is None:

        await message.answer(text="Привет!")

        await message.answer(text="Это Telegram бот, с помощью которого Вы можете следить за Вашими оценками даже"
                                  " не заходя в Сетевой город")

        await message.answer(text="Для регистрации нажмите на соответствующую кнопку снизу⬇",
                             reply_markup=get_keyboard())
    else:
        await message.reply(text="С возвращением, Ваши данные я уже загрузил")
        await message.answer(text="Можете начинать пользоваться ботом", reply_markup=get_kb_stand())
        await Standard.standard.set()


@dp.message_handler(commands=['cancel'], state=Registrations)
async def cmd_cancel(message: types.Message, state: FSMContext):
    '''Обработчик команды отмены'''
    current_state = await state.get_state()
    if current_state is None:
        return

    await message.reply('Хорошо, как захотите вернуться - напишите)',
                        reply_markup=get_keyboard())
    await state.finish()


@dp.message_handler(Text(equals='Регистрация', ignore_case=True), state=None)
async def registration(message: types.message):
    '''Начало регистрации'''
    await message.reply(text="Хорошо", reply_markup=get_cancel())

    await message.answer(text="Для начала отправьте мне Интернет-адрес Сетевого Города:")
    await Registrations.waiting_for_url.set()


@dp.message_handler(lambda message: message.text, content_types=['text'], state=Registrations.waiting_for_url)
async def enter_login(message: types.Message, state: FSMContext):
    '''Сохранение URL'''
    async with state.proxy() as DATA:
        try:
            url_sgo = message.text
            http = re.search('http://', url_sgo)

            if http == None:
                http = re.search('https://', url_sgo)
                if http == None:
                    url_sgo = "https://" + url_sgo

            parsed = urlparse(url_sgo)
            url = f"http://{parsed.netloc}"
            requests.get(url)
            DATA['url'] = url

            await Registrations.next()

            await message.answer("Отлично, теперь отправте мне Ваш логин от дневника:")
        except requests.exceptions.ConnectionError:
            await bot.send_message(chat_id=message.from_user.id, text='Введите адрес электронного дневника!')


@dp.message_handler(lambda message: message.text, content_types=['text'], state=Registrations.waiting_for_login)
async def enter_login(message: types.message, state: FSMContext):
    '''Сохранение логина'''
    async with state.proxy() as DATA:
        DATA['login'] = message.text

    await Registrations.next()

    await message.answer("Теперь отправьте мне Ваш пароль:")
    await message.answer("Можете не беспокоиться за сохранность данных, я их шифрую так,"
                         " что даже мой создатель не может их прочитать")


@dp.message_handler(lambda message: message.text, content_types=['text'], state=Registrations.waiting_for_password)
async def enter_password(message: types.message, state: FSMContext):
    '''Сохранение пароля'''
    async with state.proxy() as DATA:
        DATA['password'] = message.text

    await Registrations.next()
    await bot.send_message(chat_id=message.from_user.id, text='Теперь напишите мне номер Вашей школы:')


@dp.message_handler(lambda message: message.text, content_types=['text'], state=Registrations.waiting_for_school)
async def enter_school_finish(message: types.message, state: FSMContext):
    '''Сохранение школы'''
    async with state.proxy() as DATA:
        try:
            parsed = DATA['url']

            url = f"{parsed}/webapi/schools/search?name={message.text}"

            response = requests.get(url)

            data_school = response.json()[0]['shortName']

            DATA['school'] = data_school
            await message.answer(f'Ваша школа: {data_school}')

            await message.answer('Верно?', reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True)
                                 .add(types.KeyboardButton('Да'), types.KeyboardButton('Нет')))
            await Registrations.next()
        except IndexError:
            await bot.send_message(chat_id=message.from_user.id, text='Я не смог найти полное название Вашей школы(')
            await bot.send_message(chat_id=message.from_user.id, text='Проверьте введённый номер школы и отправьте'
                                                                      ' его мне заново⬇')


@dp.message_handler(lambda message: message.text, content_types=['text'], state=Registrations.confirm_school)
async def confirm_school(message: types.Message, state: FSMContext):
    if message.text == 'Да':
        async with state.proxy() as DATA:
            await bot.send_message(chat_id=message.from_user.id,
                                   text="Хорошо, теперь проверьте правильность введённых данных:\n"
                                        f"Адрес сайта: <b>{DATA['url']}</b>\nЛогин: <b>{DATA['login']}</b>\n"
                                        f"Пароль: <b>{DATA['password']}</b>\nШкола: <b>{DATA['school']}</b>")
            await bot.send_message(chat_id=message.from_user.id,
                                   text="Всё верно?",
                                   reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True)
                                   .add(types.KeyboardButton('Да'), types.KeyboardButton('Нет')))
        await Registrations.next()
    elif message.text == 'Нет':
        await Registrations.waiting_for_school.set()
        await message.answer('Тогда снова отправьте мне номер своей школы', reply_markup=get_cancel())
    else:
        await message.answer('Используй кнопки ниже⬇')


@dp.message_handler(lambda message: message.text == 'Нет', content_types=['text'],
                    state=Registrations.finishing_registration)
async def incorrect_data(message: types.message):
    '''Отмена правильности введённых данных'''
    await Registrations.waiting_for_url.set()
    await message.reply("Хорошо, теперь снова отправь мне Интернет адрес Сетевого Города", reply_markup=get_cancel())


@dp.message_handler(lambda message: message.text == 'Да', content_types=['text'],
                    state=Registrations.finishing_registration)
async def finishing_registration(message: types.message, state: FSMContext):
    """Шифрование данных и занос их в БД"""
    async with state.proxy() as DATA:
        login_utf = DATA['login'].encode('utf-8')
        password_utf = DATA['password'].encode('utf-8')
        login_hash = cipher.encrypt(login_utf)
        password_hash = cipher.encrypt(password_utf)

        sqlite_connections = sqlite3.connect('data_base.db')
        cursor = sqlite_connections.cursor()
        sqlite_insert_query = f'''INSERT INTO users_data_base

                                VALUES 
                                ({message.from_user.id}, '{message.from_user.username}', '{datetime.today()}',
                                '{DATA['url']}', "{login_hash}", "{password_hash}", '{DATA['school']}', '0')'''
        cursor.execute(sqlite_insert_query)
        sqlite_connections.commit()
        cursor.close()

    await message.reply(text='Отлично, теперь попробуйте нажать на одну из кнопок ниже и бот Вам ответит',
                        reply_markup=get_kb_stand())
    await bot.send_message(chat_id=message.from_user.id,
                           text='Так же если что-то будет не понятно, нажмите на эту кнопку')
    await bot.send_message(chat_id=message.from_user.id, text='⬇')
    await Standard.standard.set()


def kb_schedule(six_days):
    """Инлайн кнопки расписания"""
    buttons = [
        types.InlineKeyboardButton('Пн', callback_data='schedule_monday'),
        types.InlineKeyboardButton('Вт', callback_data='schedule_tuesday'),
        types.InlineKeyboardButton('Ср', callback_data='schedule_wednesday'),
        types.InlineKeyboardButton('Чт', callback_data='schedule_thursday'),
        types.InlineKeyboardButton('Пт', callback_data='schedule_friday')
    ]
    if six_days:
        buttons.append(types.InlineKeyboardButton('Сб', callback_data='schedule_saturday'))
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    keyboard.add(*buttons)
    return keyboard


def kb_homework(six_days):
    '''Инлайн кнопки домашней работы'''
    buttons = [
        types.InlineKeyboardButton('Пн', callback_data='homework_monday'),
        types.InlineKeyboardButton('Вт', callback_data='homework_tuesday'),
        types.InlineKeyboardButton('Ср', callback_data='homework_wednesday'),
        types.InlineKeyboardButton('Чт', callback_data='homework_thursday'),
        types.InlineKeyboardButton('Пт', callback_data='homework_friday')
    ]
    if six_days:
        buttons.append(types.InlineKeyboardButton('Сб', callback_data='homework_saturday'))
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    keyboard.add(*buttons)
    return keyboard


@dp.message_handler(lambda message: message.text == '🕒Расписание уроков', content_types=['text'],
                    state=Standard.standard)
async def schedule(message: types.message, state: FSMContext):
    """Отправка расписания в Telegram"""
    func = Functions(message.from_user.id)

    day = datetime.today().weekday()
    if day == 0:
        weekday = 1
        text = 'вторник'
    elif day == 1:
        weekday = 2
        text = 'среду'
    elif day == 2:
        weekday = 3
        text = 'четверг'
    elif day == 3:
        weekday = 4
        text = 'пятницу'
    elif day == 4 or 5 or 6:
        weekday = 0
        text = 'понедельник'

    try:
        data_tg = await func.get_schedule(weekday, text)
        await bot.send_message(chat_id=message.from_user.id, text='\n'.join(map(str, data_tg[0])),
                               reply_markup=kb_schedule(data_tg[1]))
    except errors.AuthError:
        await message.answer('Вы неправильно ввели логин или пароль, пройдите регистрацию заново')
        await message.answer('Для этого нажмите на кнопку ниже:', reply_markup=types.
                             ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton('Регистрация')))
        await state.finish()

        try:
            func.delete_user_data()

        except sqlite_connection.Error as error:
            print('бб, с ДБ трабл ', datetime.today(), ' ', datetime.time())
            await bot.send_message(chat_id=message.from_user.id, text='У бота возникли проблемы, для её решения'
                                                                      ' отправьте разработчику https://t.me/mirnsknight'
                                                                      ' скриншот ошибки:'
                                                                      f'{error}')


async def edit_message(message: types.Message, new_schedule: str, six_days, type_work):
    """Редактирование сообщения"""
    if type_work == 'schedule':
        await message.edit_text(new_schedule, reply_markup=kb_schedule(six_days))
    elif type_work == 'homework':
        await message.edit_text(new_schedule, reply_markup=kb_homework(six_days))


@dp.callback_query_handler(Text(startswith='schedule_'), state=Standard.standard)
async def callbacks_schedule(call: types.CallbackQuery):
    """Обработчик callback-ов расписания"""

    func = Functions(call.from_user.id)

    day = call.data.split('_')[1]

    if day == 'monday':

        data_diary = await func.get_schedule(0, 'понедельник')
        await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                           type_work='schedule')

    elif day == 'tuesday':

        data_diary = await func.get_schedule(1, 'вторник')
        await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                           type_work='schedule')

    elif day == 'wednesday':

        data_diary = await func.get_schedule(2, 'среду')
        await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                           type_work='schedule')

    elif day == 'thursday':

        data_diary = await func.get_schedule(3, 'четверг')
        await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                           type_work='schedule')

    elif day == 'friday':

        data_diary = await func.get_schedule(4, 'пятницу')
        await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                           type_work='schedule')

    elif day == 'saturday':

        data_diary = await func.get_schedule(5, 'субботу')
        await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                           type_work='schedule')


@dp.message_handler(lambda message: message.text == '📖Домашка', content_types=['text'], state=Standard.standard)
async def homework(message: types.message, state: FSMContext):
    '''Отправка домашнего задания в Telegram'''

    day = datetime.today().weekday()
    if day == 0:
        weekday = 1
        text = 'вторник'
    elif day == 1:
        weekday = 2
        text = 'среду'
    elif day == 2:
        weekday = 3
        text = 'четверг'
    elif day == 3:
        weekday = 4
        text = 'пятницу'
    elif day == 4 or 5 or 6:
        weekday = 0
        text = 'понедельник'

    func = Functions(message.from_user.id)

    try:
        data_diary = await func.get_homework(weekday, text)
        if len(data_diary[0]) > 1:
            await bot.send_message(chat_id=message.from_user.id, text='\n'.join(map(str, data_diary[0])),
                                   reply_markup=kb_homework(six_days=data_diary[1]))
        else:
            await bot.send_message(chat_id=message.from_user.id, text=data_diary[0][0],
                                   reply_markup=kb_homework(six_days=data_diary[1]))

    except errors.AuthError:

        await message.answer('Ты неправильно ввёл логин или пароль, пройди регистрацию заново')
        await message.answer('Для этого нажми на кнопку ниже:', reply_markup=types.
                             ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton('Регистрация')))
        await state.finish()

        try:
            func.delete_user_data()

        except sqlite_connection.Error as error:
            print('бб, с ДБ трабл ', datetime.today(), ' ', datetime.time())
            await bot.send_message(chat_id=message.from_user.id, text='У бота возникли проблемы, для её решения'
                                                                      ' отправь разработчику ....'
                                                                      ' скриншот ошибки:'
                                                                      f'{error}')


@dp.callback_query_handler(Text(startswith='homework_'), state=Standard.standard)
async def callbacks_homework(call: types.CallbackQuery):
    """Обработчик callback-ов домашнего задания"""

    func = Functions(call.from_user.id)

    day_call = call.data.split("_")[1]

    if day_call == 'monday':

        data_diary = await func.get_homework(0, 'понедельник')

        if len(data_diary[0]) > 1:
            await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                               type_work='homework')
        else:
            await edit_message(call.message, f'Домашки на понедельник нет', six_days=data_diary[1],
                               type_work='homework')

    elif day_call == 'tuesday':

        data_diary = await func.get_homework(1, 'вторник')

        if len(data_diary[0]) > 1:
            await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                               type_work='homework')
        else:
            await edit_message(call.message, f'Домашки на вторник нет', six_days=data_diary[1],
                               type_work='homework')

    elif day_call == 'wednesday':

        data_diary = await func.get_homework(2, 'среду')

        if len(data_diary[0]) > 1:
            await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                               type_work='homework')
        else:
            await edit_message(call.message, f'Домашки на среду нет', six_days=data_diary[1], type_work='homework')

    elif day_call == 'thursday':

        data_diary = await func.get_homework(3, 'четверг')

        if len(data_diary[0]) > 1:
            await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                               type_work='homework')
        else:
            await edit_message(call.message, f'Домашки на четверг нет', six_days=data_diary[1],
                               type_work='homework')

    elif day_call == 'friday':

        data_diary = await func.get_homework(4, 'пятницу')

        if len(data_diary[0]) > 1:
            await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                               type_work='homework')
        else:
            await edit_message(call.message, f'Домашки на пятницу нет', six_days=data_diary[1],
                               type_work='homework')

    elif day_call == 'saturday':

        data_diary = await func.get_homework(5, 'среду')

        if len(data_diary[0]) > 1:
            await edit_message(call.message, '\n'.join(map(str, data_diary[0])), six_days=data_diary[1],
                               type_work='homework')
        else:
            await edit_message(call.message, f'Домашки на субботу нет', six_days=data_diary[1],
                               type_work='homework')


def kb_settings():
    '''Клавиатура настроек'''
    buttons = [types.KeyboardButton('🗑Удалить аккаунт')]
    buttons2 = [types.KeyboardButton('🏫Информация о школе')]
    buttons3 = [types.KeyboardButton('👤Автор'),
                types.KeyboardButton('↩Назад')]
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(*buttons)
    kb.add(*buttons2)
    kb.add(*buttons3)
    return kb


@dp.message_handler(lambda message: message.text == '⚙Настройки', content_types=['text'], state='*')
async def settings(message: types.Message):
    '''Обработчик команды настроек'''
    await Settings.menu.set()
    await message.answer(text="Вот список текущих настроек:", reply_markup=kb_settings())


def kb_confirm():
    '''Клавиатура подтверждения удаления аккаунта'''
    buttons = [types.KeyboardButton('🚫Нет, я хочу продолжить пользоваться ботом')]
    buttons1 = [types.KeyboardButton('Да, удалить мой аккаунт')]
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(*buttons)
    kb.add(*buttons1)
    return kb


@dp.message_handler(lambda message: message.text == '🗑Удалить аккаунт', content_types=['text'], state=Settings.menu)
async def confirm_deleting(message: types.Message):
    '''Подтверждение удаления аккаунта'''
    await Settings.delete_account.set()
    await message.answer('Ты уверен что хочешь удалить свой аккаунт и стереть данные о тебе из базы данных?',
                         reply_markup=kb_confirm())


@dp.message_handler(lambda message: message.text == 'Да, удалить мой аккаунт', content_types=['text'],
                    state=Settings.delete_account)
async def deleting(message: types.Message, state: FSMContext):
    '''Удаление аккаунта'''
    await message.answer('Очень жаль, что ты покидаешь меня😓')
    await message.answer('Я уже стёр твои данные из своей базы')
    await message.answer('Если захочешь вернуться - нажми на кнопку /start в любой момент, я тебе отвечу)',
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True)
                         .add(types.KeyboardButton('/start')))
    await state.finish()

    try:
        func = Functions(message.from_user.id)
        func.delete_user_data()

    except sqlite_connection.Error as error:
        print('бб, с ДБ трабл ', datetime.today(), ' ', datetime.time())
        await bot.send_message(chat_id=message.from_user.id, text='У бота возникли проблемы, для её решения'
                                                                  ' отправь разработчику ....'
                                                                  ' скриншот ошибки:'
                                                                  f'{error}')


@dp.message_handler(lambda message: message.text == '🚫Нет, я хочу продолжить пользоваться ботом',
                    content_types=['text'], state=Settings.delete_account)
async def deleting_not(message: types.Message):
    '''Отмена удаления аккаунта'''
    await message.answer('Я очень рад, что ты принял такое решение)', reply_markup=kb_settings())
    await Settings.menu.set()


@dp.message_handler(lambda message: message.text == '↩Назад', content_types=['text'],
                    state=Settings)
async def back(message: types.Message, state: FSMContext):
    """Команда "Назад\""""
    type_state = str(await state.get_state())

    if type_state == 'Settings:menu':
        await Standard.standard.set()
        await message.answer('Можешь продолжать пользоваться моими функциями:', reply_markup=get_kb_stand())

    elif type_state == 'Settings:author':
        await Settings.menu.set()
        await message.answer('Вот список текущих настроек:', reply_markup=kb_settings())


@dp.message_handler(lambda message: message.text == '🏫Информация о школе', content_types=['text'], state=Settings.menu)
async def school_about(message: types.Message):
    func = Functions(message.from_user.id)
    data = func.get_user_data()

    ns = NetSchoolAPI(data[0])

    await ns.login(
        data[1],
        data[2],
        data[3]
    )

    tmp = await ns.school()

    await ns.logout()

    school_txt = ['<b>Вот актуальная информация о вашей школе:</b>\n']

    if tmp.name != '':
        school_txt.append('<b>Название учреждения:</b>')
        school_txt.append(f'{tmp.name}\n')

    if tmp.about != '':
        school_txt.append('<b>Описание:</b>')
        school_txt.append(f'{tmp.about}\n')

    if tmp.address != '':
        school_txt.append('<b>Фактический адрес:</b>')
        address_split = tmp.address.split(',')
        school_txt.append(f"{address_split[1][1:] + ' ' + address_split[2] + ',' + address_split[3]}\n")

    if tmp.director != '':
        school_txt.append('<b>Директор школы:</b>')
        school_txt.append(f'{tmp.director}\n')

    if tmp.AHC != '':
        school_txt.append('<b>Заместитель директора школы по административно-хозяйственной части:</b>')
        school_txt.append(f'{tmp.AHC}\n')

    if tmp.UVR != '':
        school_txt.append('<b>Заместитель директора школы по учебно-воспитательной работе:</b>')
        school_txt.append(f'{tmp.UVR}\n')

    if tmp.phone != '':
        school_txt.append('<b>Электронная почта:</b>')
        school_txt.append(f'<code>{tmp.email}</code>\n')

    if tmp.email != '':
        school_txt.append('<b>Контактный телефон:</b>')
        school_txt.append(f'<code>{tmp.phone}</code>\n')

    kb = types.InlineKeyboardMarkup()

    if tmp.site != '':
        button1 = types.InlineKeyboardButton(text='Сайт школы', url=tmp.site)
        kb.add(button1)

    await message.answer('\n'.join(map(str, school_txt)), reply_markup=kb)


def kb_author():
    """Клавиатура меню автора"""
    buttons = [types.KeyboardButton('💸Поддержать разработчика')]
    buttons1 = [types.KeyboardButton('↩Назад')]
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(*buttons)
    kb.add(*buttons1)
    return kb


@dp.message_handler(lambda message: message.text == '👤Автор', content_types=['text'], state=Settings.menu)
async def author(message: types.Message):
    """Меню автора"""
    await message.answer('.....', reply_markup=kb_author())

    await Settings.author.set()


@dp.message_handler(lambda message: message.text == '💸Поддержать разработчика', content_types=['text'],
                    state=Settings.author)
async def author(message: types.Message):
    '''Поддержка разработчика'''
    await message.answer('....')


@dp.message_handler(commands=['help'], state="*")
async def help_command(message: types.Message):
    await bot.send_message(chat_id=message.from_user.id, text='С помощью этого бота ты можешь получать информацию'
                                                              ' о домашнем задании и расписании даже не заходя на сайт'
                                                              ' Сетевого города')
    await bot.send_message(chat_id=message.from_user.id, text='Так-же если бот не отвечает на твои сообщения, то введи'
                                                              ' команду /restart \n(иногда бота перезагружают и'
                                                              ' предыдущее его состояние слетает)')
    await bot.send_message(chat_id=message.from_user.id, text='PS: если что быстрый доступ есть к ней в меню')
    await bot.send_message(chat_id=message.from_user.id, text='⬇')


@dp.message_handler(commands=['restart'], state="*")
async def restart_command(message: types.Message):
    await message.answer(text="Бот перезагружен✅", reply_markup=get_kb_stand())
    await Standard.standard.set()


if __name__ == "__main__":
    executor.start_polling(dp,
                           skip_updates=True)
