#!/usr/bin/python3
# -*- coding: utf-8 -*-
import time
import telebot
import os
from telebot import types
from API import (
    send_search_request_and_print_result,
    search_and_download_artist,
    download_album,
    get_album_info,
    folder_music,
    download_book,
    get_book_info,
    folder_audiobooks,
)
from dotenv import load_dotenv, find_dotenv
import queue
import threading


load_dotenv(find_dotenv())
bot = telebot.TeleBot(os.getenv('TELEGRAMM_TOKEN'))
download_queue = queue.Queue()
result_queue = queue.Queue()

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, 'Привет, хочешь скачать музыку или аудиокниги? /download')


@bot.message_handler(commands=['download'])
def download_command(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    item1 = types.KeyboardButton("Артиста")
    item2 = types.KeyboardButton("Альбом")
    item3 = types.KeyboardButton('Книгу')
    markup.add(item1, item2, item3)
    msg = bot.send_message(message.chat.id, 'Что будем качать?', reply_markup=markup)
    bot.register_next_step_handler(msg, take_you_choise)


def take_you_choise(message):
    if message.text == "Артиста":
        msg = bot.send_message(message.chat.id, 'Напиши название артиста или группы')
        bot.register_next_step_handler(msg, input_data_artist)
    elif message.text == "Альбом":
        msg = bot.send_message(message.chat.id, 'скинь ссылку на альбом')
        bot.register_next_step_handler(msg, input_data_albom)
    elif message.text == "Книгу":
        msg = bot.send_message(message.chat.id, 'Кинь мне ссылку на книгу с яндекс-музыки')
        bot.register_next_step_handler(msg, input_data_book)


def input_data_artist(message):
    try:
        artist = send_search_request_and_print_result(message.text)
        bot.send_message(message.chat.id, artist)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        item1 = types.KeyboardButton("Качаем!")
        item2 = types.KeyboardButton("Отмена")
        markup.add(item1, item2)
        msg = bot.send_message(message.chat.id, 'Качаем музыку этого артиста?', reply_markup=markup)
        artist_result = artist[artist.find('>>>') + 3:artist.rfind('<<<')].lower()
        cont_type = 'Artist'
        bot.register_next_step_handler(msg, download_from_input_data, cont_type, artist_result)
    except:
        bot.send_message(message.chat.id, f'Что-то пошло не так при поиске информации о артисте {artist}. Посмотри логи.')
        with open(f'{folder_music}/log.log', 'rb') as file:
            bot.send_document(message.chat.id, file)

def input_data_albom(message):
    try:
        album_id = ''.join([x for x in message.text if x.isdigit()])
        print('Album_id: ', album_id)
        album_mess = get_album_info(album_id=album_id)
        bot.send_message(message.chat.id, album_mess)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        item1 = types.KeyboardButton("Качаем!")
        item2 = types.KeyboardButton("Отмена")
        markup.add(item1, item2)
        msg = bot.send_message(message.chat.id, 'Качаем этот альбом?', reply_markup=markup)
        cont_type = 'Album'
        bot.register_next_step_handler(msg, download_from_input_data, cont_type, album_id)
    except:
        bot.send_message(message.chat.id, 'Что-то пошло не так при поиске информации о альбоме. Посмотри логи.')
        with open(f'{folder_music}/log.log', 'rb') as file:
            bot.send_document(message.chat.id, file)


def input_data_book(message):
    try:
        book_id = ''.join([x for x in message.text if x.isdigit()])
        print('Book_id: ', book_id)
        book_mess = get_book_info(album_id=book_id)
        bot.send_message(message.chat.id, book_mess)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        item1 = types.KeyboardButton("Качаем!")
        item2 = types.KeyboardButton("Отмена")
        markup.add(item1, item2)
        msg = bot.send_message(message.chat.id, 'Качаем эту аудиокнигу?', reply_markup=markup)
        cont_type = 'Book'
        bot.register_next_step_handler(msg, download_from_input_data, cont_type, book_id)
    except:
        bot.send_message(message.chat.id, 'Что-то пошло не так при поиске информации о аудиокниге. Посмотри логи.')
        with open(f'{folder_music}/log.log', 'rb') as file:
            bot.send_document(message.chat.id, file)


def download_from_input_data(message, *args):
    try:
        if message.text == 'Качаем!':
            if args[0] == 'Artist':
                download_queue.put((search_and_download_artist, args[1], message.chat.id))
            elif args[0] == 'Album':
                download_queue.put((download_album, args[1], message.chat.id))
            elif args[0] == 'Book':
                download_queue.put((download_book, args[1], message.chat.id))
            bot.send_message(message.chat.id, f"Добавил закачку в очередь.\nВсего в очереди: {download_queue.qsize()} задачи")
        else:
            bot.send_message(message.chat.id, f"Не хочешь? Можешь скачать что-то другое.\nВсего в очереди: {download_queue.qsize()} задачи")
    except:
        bot.send_message(message.chat.id, "Что-то пошло не так при добавлении в очередь. Посмотри log")
        with open(f'{folder_music}/log.log', 'rb') as file:
            bot.send_document(message.chat.id, file)


def download_monitor():
    while True:
        time.sleep(10)
        if download_queue.empty() == False:
            data = download_queue.get()
            result = data[2], data[0](data[1])
            result_queue.put(result)

def result_monitor():
    while True:
        time.sleep(10)
        if result_queue.empty() == False:
            result = result_queue.get()
            bot.send_message(chat_id=result[0], text=result[1])


if __name__ == '__main__':
    download_monitor_thread = threading.Thread(target=download_monitor, daemon=True)
    download_monitor_thread.start()
    result_monitor_thread = threading.Thread(target=result_monitor, daemon=True)
    result_monitor_thread.start()
    bot.polling(none_stop=True)
