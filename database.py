__author__ = "Aqendo"
__credits__ = ["Aqendo", "MarshalX"]
__license__ = "LGPL"
__version__ = "1.0.0"
__maintainer__ = "Aqendo"
__email__ = "a@aqendo.eu.org"
__status__ = "Production"

import os
import sqlite3

import aiosqlite


class DB:
    def __init__(self, name):
        self.cache_tokens = {}
        self.name = name
        if not os.path.exists(name):
            try:
                sqlite_connection = sqlite3.connect(name)
                sqlite_create_table_query = """CREATE TABLE musics (
                                            id TEXT,
                                            file_id TEXT);
                                           """
                sqlite_create_table_query1 = """ CREATE TABLE tokens (
                                            userid TEXT,
                                            token TEXT);"""
                cursor = sqlite_connection.cursor()
                print("База данных подключена к SQLite")
                cursor.execute(sqlite_create_table_query)
                cursor.execute(sqlite_create_table_query1)
                sqlite_connection.commit()
                print("Таблица SQLite создана")
                cursor.close()
            except sqlite3.Error as error:
                print("Ошибка при подключении к sqlite", error)
            finally:
                if sqlite_connection:
                    sqlite_connection.close()
                    print("Соединение с SQLite закрыто")

    async def set_value(self, key, value):
        sqlite_connection = None
        try:
            sqlite_connection = await aiosqlite.connect(self.name)
            insert_value = """INSERT OR REPLACE INTO musics
                (id, file_id) VALUES(?, ?);"""
            cursor = await sqlite_connection.cursor()
            await cursor.execute(insert_value, (key, value))
            await sqlite_connection.commit()
        except aiosqlite.Error as error:
            print("Ошибка при подключении к sqlite", error)
        finally:
            if sqlite_connection:
                await sqlite_connection.close()

    async def set_token(self, userid, token):
        sqlite_connection = None
        try:
            self.cache_tokens[userid] = token
            sqlite_connection = await aiosqlite.connect(self.name)
            insert_value = """INSERT OR REPLACE INTO tokens
                (userid, token) VALUES(?, ?);"""
            cursor = await sqlite_connection.cursor()
            await cursor.execute(insert_value, (userid, token))
            await sqlite_connection.commit()
        except aiosqlite.Error as error:
            print("Ошибка при подключении к sqlite", error)
        finally:
            if sqlite_connection:
                await sqlite_connection.close()

    async def get_token(self, userid):
        sqlite_connection = None
        try:
            if userid in self.cache_tokens:
                return self.cache_tokens[userid]
            sqlite_connection = await aiosqlite.connect(self.name)
            select = """SELECT token FROM tokens
            WHERE userid=?;"""
            cursor = await sqlite_connection.cursor()
            executed = await cursor.execute(select, (str(userid),))
            file_id = await executed.fetchall()
            return file_id and file_id[0][0] or None
        except aiosqlite.Error as error:
            print("Ошибка при подключении к sqlite", error)
        finally:
            if sqlite_connection:
                await sqlite_connection.close()

    async def get_value(self, key):
        sqlite_connection = None
        try:
            sqlite_connection = await aiosqlite.connect(self.name)
            select = """SELECT file_id FROM musics
            WHERE id=?;"""
            cursor = await sqlite_connection.cursor()
            file_id = await (await cursor.execute(select, (key,))).fetchall()
            return file_id and file_id[0][0] or None
        except aiosqlite.Error as error:
            print("Ошибка при подключении к sqlite", error)
        finally:
            if sqlite_connection:
                await sqlite_connection.close()

    async def check(self, values: list):
        try:
            sqlite_connection = await aiosqlite.connect(self.name)
            select = f"""SELECT * FROM musics
            where id in ({str(values)[1:-1]}); """
            cursor = await sqlite_connection.cursor()
            file_ids = await (await cursor.execute(select)).fetchall()
            return file_ids or []
        except aiosqlite.Error as error:
            print("Ошибка при подключении к sqlite", error)
        finally:
            if sqlite_connection:
                await sqlite_connection.close()
