# yandex_music_downloader
Основано на:
* MarshalX/yandex-music-api
* Telegram Bot API

Телеграм бот + скачка музыки артиста, альбома, плейлиста, сборника с вашего аккаунта yandex.music.ru. Рекомендуется для работы в паре с медиосервером.
для работы необходимо:
1. Токен вашего яндекс аккаунта
2. Токен телеграмм вашего бота
3. config.py с вашими настройками в папке с программой

# Установка
1. git clone
2. cd yandex_music_downloader
3. nano config.py
______________
    telegramm_token = "YOUR_TOKEN"
    ya_token = "YOUR_TOKEN"
    download_path = 'YOUR_DOWNLOAD_PATH'
______________

4. python tbot.py

# Использование
1. Отправьте команду вашему боту:


    /download

2. Выберете один из вариантов скачивания, следуйте советом вашего бота.
3. Музыка скачается в выбранную вами директорию "YOUR_DOWNLOAD_PATH"

Музыка качаются в максимальном доступном качестве до 320 kbps с записанными тегами, обложкой, текстом песни, если он есть на яндексе.

