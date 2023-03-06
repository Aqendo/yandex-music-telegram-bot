__author__ = "Aqendo"
__credits__ = ["Aqendo", "MarshalX"]
__license__ = "LGPL"
__version__ = "1.0.0"
__maintainer__ = "Aqendo"
__email__ = "a@aqendo.eu.org"
__status__ = "Production"

import asyncio
import logging
import os
import re
from functools import partial, wraps
from uuid import uuid4

import aiohttp
import eyed3
import yandex_music
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineQueryResultCachedAudio,
    InlineQueryResultAudio,
    InlineQueryResultArticle,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    ChosenInlineResult,
    InputMediaAudio,
    FSInputFile,
    BufferedInputFile,
)
from aiogram.types.input_text_message_content import InputTextMessageContent
from dotenv import find_dotenv, load_dotenv
from eyed3.id3.frames import ImageFrame
from yandex_music import ClientAsync

from database import DB

load_dotenv(find_dotenv())
REGEX_TOKEN = re.compile(r"y\w{1,4}_\w{1,1000}")
db = DB(os.getenv("DB_PATH"))
TOKEN = os.environ.get("BOT_TOKEN")
client_cache = {}


def wrap(func):
    @wraps(func)
    async def run(*args, loop=None, executor=None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, pfunc)

    return run


bot = Bot(TOKEN, parse_mode="HTML")
router = Router()


@router.message(Command(commands=["start"]))
async def command_start_handler(message: Message) -> None:
    await message.answer(
        """Используй /settoken YOURTOKEN для того чтобы применить токен
Инструкция:

(Опционально) Открываем DevTools в браузере и на вкладке Network включаем троттлинг.
Переходим по ссылке https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d
Авторизуемся при необходимости и предоставляем доступ
Браузер перенаправит на адрес вида https://music.yandex.ru/#access_token=AQAAAAAYc***&token_type=bearer&expires_in=31535645. Очень быстро произойдет редирект на другую страницу, поэтому нужно успеть скопировать ссылку.
Ваш токен, то что находится после access_token."""  # noqa: E501
    )


@router.message(Command(commands=["settoken"]))
async def set_token_handler(message: Message) -> None:
    token = message.text.strip("/settoken ")
    if re.match(REGEX_TOKEN, token):
        await db.set_token(message.from_user.id, token)
        await message.answer(
            "Успешно выставлен этот токен:\n\n" + token + "\nкак твой"
        )
    else:
        await message.answer(
            "Токен не прошёл проверку на валидность, точно ли он правильный? Если нет,то напиши в комментах в @t4stunnimods"  # noqa: E501
        )


async def now_playing(
    inline_query: types.InlineQuery, client: yandex_music.ClientAsync
):
    # Пытаемся получить последний играющий трек
    queues = await client.queues_list()
    last_queue = await client.queue(queues[0].id)
    last_track_id = None
    try:
        last_track_id = last_queue.get_current_track()
    except IndexError:
        # Библиотека Маршала не поддерживает Мою Волну,
        # по крайней мере на данный момент.
        await inline_query.answer(
            [
                InlineQueryResultArticle(
                    id="done",
                    title="Невозможно получить",
                    input_message_content=InputTextMessageContent(
                        message_text='Видимо, вы слушаете сейчас "Мою волну", к сожалению встроенный API Яндекс Музыки не позволяет получить информацию о треке, который сейчас играет. Попробуйте сохранить его в плейлист (или забейте в поиск) и включите его там. Раздел "Мне нравится" тоже подходит.'  # noqa: E501
                    ),
                )
            ],
            is_personal=True,
            cache_time=0,
        )
        return
    track = await last_track_id.fetch_track_async()
    id_from_db = await db.get_value(str(track.id))
    if id_from_db is not None:
        await inline_query.answer(
            [
                InlineQueryResultCachedAudio(
                    id="done", type="audio", audio_file_id=id_from_db
                )
            ],
            is_personal=True,
            cache_time=0,
        )
        return
    await inline_query.answer(
        [
            InlineQueryResultAudio(
                id=track.id,
                audio_duration=track.duration_ms // 1000,
                title=track.title,
                performer=track.artists[0].name,
                audio_url="https://a.pomf.cat/tncpzw.mp3?a=" + str(uuid4()),
                reply_markup=InlineKeyboardMarkup(
                    row_width=1,
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Идёт загрузка...",
                                callback_data="downloading",
                            )
                        ]
                    ],
                ),
            )
        ],
        is_personal=True,
        cache_time=0,
    )


async def search_and_play(
    inline_query: InlineQuery, client: yandex_music.ClientAsync
):
    search_results: yandex_music.Search = await client.search(
        inline_query.query, True, "track", 0
    )
    results_inline = []
    try:
        cached = await db.check([x.id for x in search_results.tracks.results])
    except AttributeError:
        await inline_query.answer(
            [
                InlineQueryResultArticle(
                    type="article",
                    id="done",
                    title="Ничего не нашлось",
                    input_message_content=InputTextMessageContent(
                        message_text="Ничего не нашлось"
                    ),
                )
            ]
        )
        return
    cached = {x[0]: x[1] for x in cached}
    for track in search_results.tracks.results:
        title = track.title
        artist = track.artists[0].name
        if str(track.id) in cached:
            results_inline.append(
                InlineQueryResultCachedAudio(
                    id="done" + str(uuid4())[:7],
                    type="audio",
                    audio_file_id=cached[str(track.id)],
                )
            )
        else:
            results_inline.append(
                InlineQueryResultAudio(
                    id=track.id,
                    audio_duration=track.duration_ms // 1000,
                    title=title,
                    performer=artist,
                    audio_url=os.getenv("BLANK_MP3_URL") + str(uuid4()),
                    reply_markup=InlineKeyboardMarkup(
                        row_width=1,
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="Идёт загрузка...",
                                    callback_data="downloading",
                                )
                            ]
                        ],
                    ),
                )
            )
    await inline_query.answer(results_inline, is_personal=True, cache_time=0)


@router.inline_query()
async def inline_query_handler(inline_query: InlineQuery):
    # Проверяем, есть ли токен пользователя в БД
    token = await db.get_token(inline_query.from_user.id)
    if token is None:
        await inline_query.answer(
            [],
            cache_time=0,
            is_personal=0,
            switch_pm_text="Вы не авторизованы",
            switch_pm_parameter="done",
        )
        return
    is_created = False
    if inline_query.from_user.id not in client_cache:
        client = ClientAsync(token)
        await client.init()
        client_cache[inline_query.from_user.id] = client
        is_created = True
    else:
        client = client_cache[inline_query.from_user.id]

    if inline_query.query == "":
        await now_playing(inline_query, client)
    else:
        await search_and_play(inline_query, client)
    if is_created:
        await asyncio.sleep(60 * 10)
        del client_cache[inline_query.from_user.id]


@router.chosen_inline_result()
async def chosen_result_handler(
    inline_query: ChosenInlineResult,
):
    if inline_query.result_id.startswith("done"):
        return
    result_id = inline_query.result_id
    token = await db.get_token(inline_query.from_user.id)
    is_created = False
    if inline_query.from_user.id not in client_cache:
        client = ClientAsync(token)
        await client.init()
        client_cache[inline_query.from_user.id] = client
        is_created = True
    else:
        client = client_cache[inline_query.from_user.id]
    last_track = (await client.tracks(result_id))[0]
    idd = last_track.id
    id_from_db = await db.get_value(idd)
    if id_from_db is not None:
        await bot.edit_message_media(
            inline_message_id=inline_query.inline_message_id,
            media=InputMediaAudio(
                type="audio",
                media=id_from_db,
            ),
        )
        return

    # Генерируем путь для скачивания музыки, обязательно рандом
    name = os.getenv("MUSIC_DOWNLOAD_DIR") + str(uuid4()) + ".mp3"
    muslist = await last_track.get_download_info_async()
    # Сортируем, нам нужно максимальное качество
    musll = list(filter(lambda x: x.codec == "mp3", muslist))
    muslist = max(musll, key=lambda x: int(x.bitrate_in_kbps))

    # А вот это чтобы работал IntelliSense
    if not isinstance(muslist, yandex_music.download_info.DownloadInfo):
        return

    # Яндекс Музыка, дай пж прямую ссылку
    # На самом деле получает ссылку библиотека Маршала
    link = await muslist.get_direct_link_async()

    # Запрашиваем файл мп3 с сервером Яндекс Музыки
    async with aiohttp.ClientSession() as session:
        async with session.get(link) as resp:
            if resp.status == 200:
                # А вот и наш файлик музыки
                file = await resp.read()
                with open(name, mode="wb") as f:
                    f.write(file)

                # Получаем обложку к музычке
                async with aiohttp.ClientSession() as session1:
                    async with session1.get(
                        "https://"
                        + last_track.cover_uri.replace("%%", "200x200")
                    ) as resp1:
                        # Инжектим обложку в мп3 файл
                        cover = await resp1.read()
                        eyed = eyed3.load(name)
                        if eyed.tag is None:
                            eyed.initTag()
                        eyed.tag.title = last_track.title
                        eyed.tag.images.set(
                            ImageFrame.FRONT_COVER, cover, "image/jpeg"
                        )
                        eyed.tag.save()

                        # Логируем его в чат лога
                        # со всеми изменёнными данными
                        message = await bot.send_audio(
                            os.getenv("LOG_CHAT_ID"),
                            FSInputFile(
                                name,
                                "%s- %s.mp3"
                                % (
                                    last_track.artists[0].name,
                                    last_track.title,
                                ),
                            ),
                            title=last_track.title,
                            performer=last_track.artists[0].name,
                            duration=last_track.duration_ms // 1000,
                            thumb=BufferedInputFile(cover, "cover.jpeg"),
                        )
                        # Мы получили file_id и теперь можем дать
                        # его пользователю
                        await bot.edit_message_media(
                            inline_message_id=inline_query.inline_message_id,
                            media=InputMediaAudio(
                                type="audio",
                                media=message.audio.file_id,
                            ),
                        )
                        # Добавляем в БД file_id данной песенки
                        await db.set_value(idd, message.audio.file_id)

                # Удаляем скачанный файлик
                await wrap(os.unlink)(name)
    if is_created:
        await asyncio.sleep(60 * 10)
        del client_cache[inline_query.from_user.id]


async def main() -> None:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
