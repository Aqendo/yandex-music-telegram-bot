FROM python:3.11.4-alpine3.18

WORKDIR /usr/src/app

RUN pip install aiogram --pre
RUN pip install yandex_music eyed3 python-dotenv aiosqlite 

COPY . .

CMD ["python", "./main.py"]
