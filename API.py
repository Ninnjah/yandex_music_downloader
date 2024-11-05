import os
import logging
import time
from pathlib import Path
from typing import Tuple

import music_tag
import requests

from dotenv import load_dotenv, find_dotenv
from yandex_music import Album, Client, Track
from yandex_music.exceptions import NotFoundError

from m3u8 import PlaylistGenerator

load_dotenv(find_dotenv())
client = Client(token=os.getenv("YA_TOKEN"))
client.init()
folder_music = os.getenv("DOWNLOAD_PATH_MUSIC")
replace_playlist_path = int(os.getenv("REPLACE_PLAYLIST_PATH"))
folder_audiobooks = os.getenv("DOWNLOAD_PATH_BOOKS")
folder_podcasts = os.getenv("DOWNLOAD_PATH_PODCASTS")
wrong_symbols = r"#<$+%>!`&*‘|?{}“=>/:\@"  # спецсимволы которые негативно влияют на создание каталогов и файлов
logger = logging.getLogger(__name__)


def retry(attempt_count: int = 3, timeout: float = 1):
    def decorator(f):
        def wrapper(*args, **kwargs):
            for attempt in range(attempt_count):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if attempt + 1 == attempt_count:
                        logger.warning("retry - %s", e)
                    else:
                        time.sleep(timeout)
        return wrapper
    return decorator


def search_and_download_artist(search: str):
    """Ищем лучший результат по запросу артиста и скачиваем все его песни в папку download с разбивкой по альбомам"""

    try:
        search_result = client.search(search, type_="artist", page=0, nocorrect=False)
        artist_id = search_result["artists"]["results"][0]["id"]
        artist_name = search_result["artists"]["results"][0]["name"]
    except Exception as e:
        logger.warning(e, exc_info=True)
        logger.warning("No results! You sure?")
        return f"Твой запрос: {search} не найден."

    direct_albums_count = search_result["artists"]["results"][0]["counts"][
        "direct_albums"
    ]
    logger.info(
        "Start download: Artist ID: %s / Artist name: %s / Direct albums: %s",
        artist_id,
        artist_name,
        direct_albums_count,
    )
    # находим список альбомов артиста с информацией
    direct_albums = client.artistsDirectAlbums(artist_id=artist_id, page_size=1000)
    # проходимся по каждому альбому
    for album in direct_albums:
        # проходимся по каждому диску в альбоме и загружаем его в папку
        download_album(album["id"])

    return f"Успешно скачал артиста: {artist_name} с его {direct_albums_count} альбомами."


def _make_album_dir(album: Album) -> Tuple[Path, Path]:
    if album.artists[0].various:
        album_folder = Path(
            folder_music, "Various artist", f"{album.title} ({album.year})"
        )
    else:
        artist_id = album.artists[0].id
        artist_name = album.artists[0].name
        artist_folder = Path(folder_music, artist_name)
        artist_cover_pic = Path(artist_folder, "artist.jpg")

        artist_folder.mkdir(parents=True, exist_ok=True)

        if not artist_cover_pic.exists():
            artist_info = client.artists_brief_info(artist_id=artist_id)
            artist_cover_link = artist_info.artist.cover.get_url(size="1000x1000")
            with artist_cover_pic.open("wb") as f:
                res = requests.get(artist_cover_link)
                f.write(res.content)

        album_folder = Path(artist_folder, f"{album.title} ({album.year})")

    album_folder.mkdir(parents=True, exist_ok=True)
    album_cover_pic = Path(album_folder, "cover.jpg")
    if not album_cover_pic.exists():
        with album_cover_pic.open("wb") as f:
            res = requests.get(album.get_cover_url("1000x1000"))
            f.write(res.content)

    return album_folder, album_cover_pic


@retry(attempt_count=5)
def _download_track(track: Track) -> Path:
    album = track.albums[0]
    album_folder, album_cover_pic = _make_album_dir(album)

    track_info = client.tracks_download_info(track_id=track.track_id, get_direct_links=True)
    track_info = sorted(track_info, reverse=True, key=lambda key: key["bitrate_in_kbps"])[0]

    logger.info(
        "Start Download: ID: %s %s bitrate: %s %s",
        track.track_id,
        track.title,
        track_info["bitrate_in_kbps"],
        track_info["direct_link"],
    )

    info = {
        "title": track.title,
        "volume_number": album.track_position.volume,
        "total_volumes": len(album.volumes) if album.volumes else 1,
        "track_position": album.track_position.index,
        "total_track": album["track_count"],
        "genre": album.genre,
        "artist": track.artists_name()[0],
        "album_artist": [artist for artist in album.artists_name()],
        "album": album["title"],
    }
    if album["release_date"]:
        info["album_year"] = album["release_date"][:10]
    elif album["year"]:
        info["album_year"] = album["year"]
    else:
        info["album_year"] = ""

    track_file = (
        album_folder /
        f"{info['track_position']} - "
        f"{''.join([_ for _ in info['title'][:80] if _ not in wrong_symbols])}.mp3"
    )
    if os.path.exists(track_file):
        logger.info("Track already exists. Continue.")
        return track_file

    client.request.download(url=track_info["direct_link"], filename=track_file)
    logger.info("Track downloaded. Start write tag's.")

    # начинаем закачивать тэги в трек
    mp3 = music_tag.load_file(track_file)
    mp3["tracktitle"] = info["title"]
    if album["version"] is not None:
        mp3["album"] = info["album"] + " " + album["version"]
    else:
        mp3["album"] = info["album"]
    mp3["discnumber"] = info["volume_number"]
    mp3["totaldiscs"] = info["total_volumes"]
    mp3["tracknumber"] = info["track_position"]
    mp3["totaltracks"] = info["total_track"]
    mp3["genre"] = info["genre"]
    mp3["Year"] = info["album_year"]
    if track.version is not None:
        mp3["comment"] = f"{track.version} / Release date {info['album_year']}"
    else:
        mp3["comment"] = f"Release date {info['album_year']}"
    mp3["artist"] = info["artist"]
    mp3["album_artist"] = info["album_artist"]
    try:
        lyrics = client.tracks_lyrics(
            track_id=track.track_id, format="TEXT"
        ).fetch_lyrics()
    except NotFoundError:
        pass
    except Exception as e:
        logger.error(e, exc_info=True)
    else:
        with open(track_file.with_suffix(".txt"), "w") as text_song:
            text_song.write(lyrics)
        mp3["lyrics"] = lyrics

    with open(album_cover_pic, "rb") as img_in:
        mp3["artwork"] = img_in.read()
    mp3.save()
    logger.info("Tag's is wrote")

    return track_file


def get_album_info(album_id):
    """Получаем информацию об альбоме"""
    album = client.albumsWithTracks(album_id=album_id)
    return (
        f"Альбом: {album['title']}\n"
        f"артист:{', '. join([art['name'] for art in album['artists']])}\n"
        f"количество треков: {album['track_count']}"
    )


def download_album(album_id):
    """Скачиваем альбом"""
    album = client.albumsWithTracks(album_id=album_id)
    logger.info(
        "Album ID: %s / Album title - %s",
        album.id,
        album.title,
    )

    for n_volume, disk in enumerate(album.volumes, start=1):
        logger.info(
            "Start download: Volume №: %d из %d",
            n_volume,
            len(album.volumes),
        )

        for track in disk:
            _download_track(track)

    return f"Успешно скачал альбом/сборник: {album.title} с его {album.track_count} композициями."


def get_playlist_info(owner_id: str, playlist_id: int):
    """Получаем информацию о плейлисте"""
    playlist = client.users_playlists(playlist_id, owner_id)
    if isinstance(playlist, list):
        playlist = playlist[0]

    return (
        f"Плейлист: {playlist.title}\n"
        f"количество треков: {playlist.track_count}"
    )


def download_playlist(playlist_data: str):
    """Скачиваем плейлист"""
    owner_id, playlist_id = playlist_data.split(":")
    playlist = client.users_playlists(playlist_id, owner_id)
    playlist_entries = []
    old_root = Path(folder_music)
    new_root = Path("/music")

    if isinstance(playlist, list):
        playlist = playlist[0]
    logger.info(
        "Playlist owner: %s / Playlist ID: %s / Playlist title - %s",
        playlist.owner.login,
        playlist.playlist_id,
        playlist.title,
    )

    for track_info in playlist.tracks:
        track = track_info.track
        track_path = _download_track(track)
        if track_path:
            if replace_playlist_path:
                track_path = new_root / track_path.relative_to(old_root)

            playlist_entries.append(
                {
                    "name": track_path.as_posix(),
                    "title": " - ".join((track.artists_name()[0], track.title)),
                    "duration": audio.info.length
                }
            )

    playlist_path = Path(folder_music, playlist.title).with_suffix(".m3u")
    with playlist_path.open("w") as f:
        f.write(PlaylistGenerator(playlist_entries, playlist_name=playlist.title).generate())

    return f"Успешно скачал плейлист: {playlist.title} с его {playlist.track_count} композициями."


def get_book_info(album_id):
    """Получаем информацию о книге"""
    book = client.albumsWithTracks(album_id=album_id)
    return f"Аудиокнига:\n{book['title']}\nсодержание из {book['track_count']} частей."


def download_book(album_id):
    """Скачиваем аудиокнигу"""
    s = client.albumsWithTracks(album_id=album_id)
    info_book = {}

    for i in range(len(s["title"])):
        if s["title"][i] in ".—":
            info_book["author"] = s["title"][:i].strip()
            if s["version"]:
                info_book["book_title"] = (
                    s["title"][i + 1 :].strip() + " (" + s["version"] + ")"
                )
            else:
                info_book["book_title"] = s["title"][i + 1 :].strip()
            break
        else:
            info_book["author"] = "Сборники"
            info_book["book_title"] = s["title"]

    info_book["artists"] = ", ".join([x["name"] for x in s["artists"]])
    info_book["cover_url"] = "https://" + s["cover_uri"].replace("%%", "1000x1000")
    info_book["parts"] = s["track_count"]
    if s["labels"]:
        info_book["labels"] = s["labels"][0]["name"]
    info_book["description"] = s["description"]

    logger.info("Author: %s", info_book["author"])
    logger.info(f"Book ID: %s / Book title - %s", album_id, info_book["book_title"])

    folder_author = f"{folder_audiobooks}/{info_book['author']}"
    if len(info_book["book_title"]) > 50:
        info_book["short_book_title"] = info_book["book_title"][:50] + "..."
        folder_book = f"{folder_author}/{''.join([ _ for _ in info_book['short_book_title'] if _ not in wrong_symbols])}/"
    else:
        folder_book = f"{folder_author}/{''.join([ _ for _ in info_book['book_title'] if _ not in wrong_symbols])}/"

    os.makedirs(os.path.dirname(folder_book), exist_ok=True)
    file_cover = f"{folder_book}/cover.jpg"
    with open(file_cover, "wb") as f:
        rec = requests.get(info_book["cover_url"])
        f.write(rec.content)

    volumes = s["volumes"]
    for volume in volumes:
        for part in volume:
            # начинаем закачивать треки

            track_info = client.tracks_download_info(
                track_id=part["id"], get_direct_links=True
            )  # узнаем информацию о треке
            track_info.sort(reverse=True, key=lambda key: key["bitrate_in_kbps"])
            part_download_link = track_info[0]["direct_link"]

            part_echo = f"Start Download: ID: {part['id']} {part['title']} bitrate: {track_info[0]['bitrate_in_kbps']} {track_info[0]['direct_link']}"
            logger.info(part_echo)  # вывод в лог
            part_name = "".join([_ for _ in part["title"] if _ not in wrong_symbols])
            if len(part["title"]) > 50:
                track_file = f"{folder_book}/{part['albums'][0]['track_position']['index']} - {part_name[:20]+ '...'+ part_name[-20:]}.mp3"
            else:
                track_file = f"{folder_book}/{part['albums'][0]['track_position']['index']} - {part_name}.mp3"
            # проверяем существование трека на сервере
            if os.path.exists(track_file):
                track_echo_ok = "Track already exists. Continue."
                logger.info(track_echo_ok)
                continue

            with open(track_file, "wb") as f:
                rec = requests.get(part_download_link)
                f.write(rec.content)

            logger.info("Track downloaded. Start write tag's.")  # вывод в лог

            mp3 = music_tag.load_file(track_file)
            mp3["tracktitle"] = part["title"]
            mp3["album"] = info_book["book_title"]
            mp3["discnumber"] = part["albums"][0]["track_position"]["volume"]
            mp3["tracknumber"] = part["albums"][0]["track_position"]["index"]
            mp3["totaltracks"] = info_book["parts"]
            mp3["genre"] = s["genre"]
            mp3["Year"] = s["year"]
            mp3["artist"] = info_book["artists"]
            mp3["album_artist"] = info_book["artists"]
            mp3["comment"] = info_book["description"]
            with open(file_cover, "rb") as img_in:
                mp3["artwork"] = img_in.read()
            mp3.save()
            logger.info("Tag's is wrote")
    return f"Успешно скачал аудиокнигу: {info_book['book_title']} из {info_book['parts']} частей"


def get_podcast_info(podcast_id):
    """Получаем информацию о подкасте"""
    podcast = client.albumsWithTracks(album_id=podcast_id)
    return f"Подкаст:\n{podcast['title']}\nсодержание из {podcast['track_count']} выпусков."


def download_podcast(podcast_id):
    s = client.albumsWithTracks(album_id=podcast_id)
    info_podcast = {
        "title": s["title"],
        "cover_url": "https://" + s["cover_uri"].replace("%%", "1000x1000"),
        "tracks": s["track_count"],
        "short_description": s["short_description"],
        "description": s["description"],
    }
    logger.info(
        f"Podcast ID: %s / Podcast title - %s",
        podcast_id,
        info_podcast["title"],
    )

    folder_podcast = (
        f"{folder_podcasts}/"
        f"{''.join([_ for _ in info_podcast['title'] if _ not in wrong_symbols])}/"
    )

    os.makedirs(os.path.dirname(folder_podcast), exist_ok=True)
    file_cover = f"{folder_podcast}cover.jpg"
    file_description = f"{folder_podcast}info.txt"

    with open(file_cover, "wb") as f:
        rec = requests.get(info_podcast["cover_url"])
        f.write(rec.content)  # записываем картинку обложки

    with open(file_description, "w") as f:
        f.write(info_podcast["description"])

    volumes = s["volumes"]
    for volume in volumes:
        for part in volume:
            track_info = client.tracks_download_info(
                track_id=part["id"], get_direct_links=True
            )
            track_info.sort(reverse=True, key=lambda key: key["bitrate_in_kbps"])
            part_download_link = track_info[0]["direct_link"]

            logger.info(
                f"Start Download: ID: %s %s bitrate: %s %s",
                part["id"],
                part["title"],
                track_info[0]["bitrate_in_kbps"],
                track_info[0]["direct_link"],
            )

            track_file = (
                f"{folder_podcast}/"
                f"#{part['albums'][0]['track_position']['volume']}-"
                f"{part['albums'][0]['track_position']['index']} - "
                f"{''.join([_ for _ in part['title'] if _ not in wrong_symbols])}.mp3"
            )
            # проверяем существование трека на сервере
            if os.path.exists(track_file):
                logger.info("Track already exists. Continue.")
                continue

            with open(track_file, "wb") as f:
                rec = requests.get(part_download_link)
                f.write(rec.content)

            logger.info("Track downloaded. Start write tag's.")

            mp3 = music_tag.load_file(track_file)
            mp3["tracktitle"] = part["title"]

            mp3["discnumber"] = part["albums"][0]["track_position"]["volume"]
            mp3["tracknumber"] = part["albums"][0]["track_position"]["index"]
            mp3["totaltracks"] = info_podcast["tracks"]
            mp3["artist"] = info_podcast["title"]
            mp3["album_artist"] = info_podcast["title"]
            mp3["comment"] = part["short_description"]

            with open(file_cover, "rb") as img_in:
                mp3["artwork"] = img_in.read()
            mp3.save()
            logger.info("Tag's is wrote")

    return f"Успешно скачал подкаст: {info_podcast['title']} из {info_podcast['tracks']} выпусков"


type_to_name = {
    "track": "трек",
    "artist": "исполнитель",
    "album": "альбом",
    "playlist": "плейлист",
    "video": "видео",
    "user": "пользователь",
    "podcast": "подкаст",
    "podcast_episode": "эпизод подкаста",
}


def send_search_request_and_print_result(query):
    """Отправляем запрос с названием артиста/группы и выводим результаты"""
    search_result = client.search(query)

    text = [f'Результаты по запросу "{query}":', ""]

    best_result_text = ""
    if search_result.best:
        type_ = search_result.best.type
        best = search_result.best.result

        text.append(f"\n{type_to_name.get(type_)}: ")

        if type_ == "artist":
            best_result_text = best.name

        text.append(f">>>{best_result_text}<<<")

    if search_result.artists:
        text.append(
            f"\nВсего альбомов: {search_result['artists']['results'][0]['counts']['direct_albums']}"
        )
    return " ".join(text)
