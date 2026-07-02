# Техническое задание

  

## Модуль GPS/EGTS-мониторинга автобусов

  

Версия: 0.1

Проект: система пассажиропотока и мониторинга автопарка

Технологии: Go, PostgreSQL, PostGIS, TimescaleDB, Python Alembic

  

---

  

# 1. Назначение модуля

  

Необходимо разработать отдельный сервис приема GPS/ГЛОНАСС-данных по протоколу EGTS.

  

Сервис должен принимать данные от GPS-трекеров, автоматически регистрировать неизвестные устройства, сохранять историю координат и обновлять последнюю известную позицию устройства.

  

GPS-модуль должен быть встроен в существующий проект пассажиропотока, но работать изолированно от основной логики подсчета пассажиров.

  

---

  

# 2. Общая архитектура

  

Текущая система пассажиропотока уже содержит API-сервис, PostgreSQL, PostGIS, TimescaleDB и миграции через Alembic.

  

Новый GPS/EGTS-сервис размещается в той же папке проекта, что и API пассажиропотока, но в отдельной директории:

  

```text

project-root/

│── alembic/

│── alembic.ini

│── app/

│── ...

│

├── gps/

│   ├── cmd/

│   │   └── receiver/

│   │       └── main.go

│   ├── internal/

│   │   ├── config/

│   │   ├── egts/

│   │   ├── model/

│   │   ├── storage/

│   │   │   └── postgres/

│   │   └── service/

│   ├── go.mod

│   ├── go.sum

│   └── README.md

```

  

Сервис `gps` пишется на Go.

  

Миграции базы данных выполняются только через существующий Python Alembic в папке `api`.

  

Go-сервис не должен выполнять миграции самостоятельно.

  

---

  

# 3. Границы ответственности

  

## 3.1. Что делает GPS/EGTS-сервис

  

Сервис должен:

  

1. Поднимать TCP-сервер для приема EGTS-пакетов.

2. Принимать подключения от GPS-трекеров.

3. Разбирать EGTS-пакеты.

4. Получать навигационные данные.

5. Преобразовывать поле `client` в `device_id`.

6. Автоматически создавать запись в `bus_trackers`, если устройство ранее не было известно.

7. Сохранять каждую GPS-точку в `gps_timeline`.

8. Обновлять последнюю позицию устройства в `gps_current_position`.

9. Логировать ошибки приема, парсинга и записи в базу.

10. Продолжать работу при ошибках отдельных пакетов.

  

---

  

## 3.2. Что GPS/EGTS-сервис не делает

  

GPS/EGTS-сервис не должен взаимодействовать с таблицами:

  

```text

passenger_timeline

device_current_status

device_events

```

  

Также сервис не должен:

  

1. Считать пассажиропоток.

2. Обновлять статусы камер.

3. Обновлять статусы Atom.

4. Писать события в `device_events`.

5. Выполнять миграции базы данных.

6. Самостоятельно назначать автобус устройству.

7. Самостоятельно менять `bus_number`.

  

---

  

# 4. Используемые существующие таблицы

  

Из существующей схемы GPS/EGTS-сервис использует только таблицу:

  

```text

buses

```

  

Таблица `buses` уже существует в системе:

  

```text

buses

- id integer PK

- bus_number varchar(64) NOT NULL UNIQUE

- camera_count integer NOT NULL CHECK camera_count > 0

- created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP

```

  

Таблица `buses` нужна только как справочник для nullable-связи из `bus_trackers.bus_number`.

  

Если устройство еще не привязано к автобусу, `bus_number` в `bus_trackers` остается `NULL`.

  

---

  

# 5. Входящие данные от EGTS

  

После разбора EGTS-пакета через модуль kuznetsovin/egts-protocol сервис получает данные поля:

  

```json

{

  "client": 194918639,

  "packet_id": 139,

  "navigation_unix_time": 1782073519,

  "received_unix_time": 1782814577,

  "latitude": 55.713711682640415,

  "longitude": 52.342378295106435,

  "speed": 0,

  "pdop": 0,

  "hdop": 0,

  "vdop": 0,

  "nsat": 0,

  "ns": 0,

  "course": 0

}

```

  

Соответствие полей:

  

```text

client                -> device_id

packet_id             -> packet_id

navigation_unix_time  -> navigation_unix_time / navigation_time

received_unix_time    -> received_unix_time / received_time

latitude              -> latitude

longitude             -> longitude

speed                 -> speed

pdop                  -> pdop

hdop                  -> hdop

vdop                  -> vdop

nsat                  -> nsat

ns                    -> ns

course                -> course

```

  

---

  

# 6. Новые таблицы

  

Для GPS/EGTS-модуля создаются 3 новые таблицы:

  

```text

bus_trackers

gps_timeline

gps_current_position

```

  

---

  

# 7. Таблица bus_trackers

  

## 7.1. Назначение

  

Таблица `bus_trackers` хранит GPS-устройства.

  

Если в систему приходит пакет от неизвестного `device_id`, сервис автоматически создает запись в `bus_trackers`.

  

Поле `bus_number` может быть `NULL`.

  

Привязка устройства к автобусу выполняется позже вручную или через административный интерфейс основной системы.

  

---

  

## 7.2. Структура таблицы

  

```sql

CREATE TABLE IF NOT EXISTS bus_trackers (

    device_id BIGINT PRIMARY KEY,

  

    bus_number VARCHAR(64) NULL

        REFERENCES buses(bus_number)

        ON UPDATE CASCADE

        ON DELETE SET NULL,

  

    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

  

    meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,

  

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP

);

  

CREATE INDEX IF NOT EXISTS bus_trackers_bus_number_idx

ON bus_trackers(bus_number);

  

CREATE INDEX IF NOT EXISTS bus_trackers_last_seen_idx

ON bus_trackers(last_seen_at DESC);

```

  

---

  
  

---

  

# 8. Таблица gps_timeline

  

## 8.1. Назначение

  

Таблица `gps_timeline` хранит всю историю GPS-точек.

  

Таблица является TimescaleDB hypertable.

  

В таблице не хранится `bus_number`, потому что на момент получения GPS-пакета устройство может быть еще не привязано к автобусу.

  

Связь с автобусом выполняется через:

  

```text

gps_timeline.device_id -> bus_trackers.device_id -> bus_trackers.bus_number

```

  

---

  

## 8.2. Структура таблицы

  

```sql

CREATE TABLE IF NOT EXISTS gps_timeline (

    id BIGINT GENERATED BY DEFAULT AS IDENTITY,

  

    device_id BIGINT NOT NULL

        REFERENCES bus_trackers(device_id)

        ON UPDATE CASCADE

        ON DELETE CASCADE,

  

    packet_id INTEGER NOT NULL,

  

    navigation_unix_time BIGINT NOT NULL,

    navigation_time TIMESTAMPTZ NOT NULL,

  

    received_unix_time BIGINT NOT NULL,

    received_time TIMESTAMPTZ NOT NULL,

  

    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),

    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),

  

    geom GEOMETRY(POINT, 4326)

        GENERATED ALWAYS AS (

            ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)

        ) STORED,

  

    speed INTEGER NOT NULL DEFAULT 0,

    pdop INTEGER NOT NULL DEFAULT 0,

    hdop INTEGER NOT NULL DEFAULT 0,

    vdop INTEGER NOT NULL DEFAULT 0,

    nsat INTEGER NOT NULL DEFAULT 0,

    ns INTEGER NOT NULL DEFAULT 0,

    course INTEGER NOT NULL DEFAULT 0,

  

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

  

    PRIMARY KEY (id, navigation_time)

);

```

  

Создание hypertable:

  

```sql

SELECT create_hypertable(

    'gps_timeline',

    'navigation_time',

    if_not_exists => TRUE

);

```

  

Индексы:

  

```sql

CREATE INDEX IF NOT EXISTS gps_timeline_device_time_idx

ON gps_timeline(device_id, navigation_time DESC);

  

CREATE INDEX IF NOT EXISTS gps_timeline_packet_idx

ON gps_timeline(device_id, packet_id, navigation_time DESC);

  

CREATE INDEX IF NOT EXISTS gps_timeline_geom_gix

ON gps_timeline USING GIST(geom);

```

  

---

  

## 8.3. Важное правило PostGIS

  

Точка создается в порядке:

  

```sql

ST_MakePoint(longitude, latitude)

```

  

То есть сначала долгота, потом широта.

  

Правильно:

  

```sql

ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)

```

  

Неправильно:

  

```sql

ST_SetSRID(ST_MakePoint(latitude, longitude), 4326)

```

  

---

  

# 9. Таблица gps_current_position

  

## 9.1. Назначение

  

Таблица `gps_current_position` хранит последнюю известную позицию каждого GPS-устройства.

  

В таблице не хранится `bus_number`.

  

Если нужно получить текущую позицию автобуса, необходимо делать JOIN с `bus_trackers`.

  

---

  

## 9.2. Структура таблицы

  

```sql

CREATE TABLE IF NOT EXISTS gps_current_position (

    device_id BIGINT PRIMARY KEY

        REFERENCES bus_trackers(device_id)

        ON UPDATE CASCADE

        ON DELETE CASCADE,

  

    packet_id INTEGER NOT NULL,

  

    navigation_unix_time BIGINT NOT NULL,

    navigation_time TIMESTAMPTZ NOT NULL,

  

    received_unix_time BIGINT NOT NULL,

    received_time TIMESTAMPTZ NOT NULL,

  

    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),

    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),

  

    geom GEOMETRY(POINT, 4326)

        GENERATED ALWAYS AS (

            ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)

        ) STORED,

  

    speed INTEGER NOT NULL DEFAULT 0,

    pdop INTEGER NOT NULL DEFAULT 0,

    hdop INTEGER NOT NULL DEFAULT 0,

    vdop INTEGER NOT NULL DEFAULT 0,

    nsat INTEGER NOT NULL DEFAULT 0,

    ns INTEGER NOT NULL DEFAULT 0,

    course INTEGER NOT NULL DEFAULT 0,

  

    raw_json JSONB NOT NULL,

  

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP

);

```

  

Индексы:

  

```sql

CREATE INDEX IF NOT EXISTS gps_current_position_geom_gix

ON gps_current_position USING GIST(geom);

  

CREATE INDEX IF NOT EXISTS gps_current_position_time_idx

ON gps_current_position(navigation_time DESC);

```

  

---

  

# 10. Логика обработки входящего GPS-пакета

  

На каждый входящий GPS-пакет сервис выполняет следующую последовательность.

  

---

  

## 10.1. Шаг 1. Получить device_id

  

Из входящего пакета:

  

```

  

  "client": 194918639

  

```

  

Сервис получает:

  

```text

device_id = client

device_id = 194918639

```

  

---

  

## 10.2. Шаг 2. Создать или обновить bus_trackers

  

Если `device_id` ранее не существовал, создается новая запись.

  

Если `device_id` уже существовал, обновляется `last_seen_at` и `updated_at`.

  

```sql

INSERT INTO bus_trackers (

    device_id,

    first_seen_at,

    last_seen_at,

    updated_at

)

VALUES (

    $1,

    CURRENT_TIMESTAMP,

    CURRENT_TIMESTAMP,

    CURRENT_TIMESTAMP

)

ON CONFLICT (device_id) DO UPDATE SET

    last_seen_at = CURRENT_TIMESTAMP,

    updated_at = CURRENT_TIMESTAMP;

```

  

---

  

## 10.3. Шаг 3. Записать точку в gps_timeline

  

Каждая точка сохраняется в историю.

  

```sql

INSERT INTO gps_timeline (

    device_id,

    packet_id,

    navigation_unix_time,

    navigation_time,

    received_unix_time,

    received_time,

    latitude,

    longitude,

    speed,

    pdop,

    hdop,

    vdop,

    nsat,

    ns,

    course,

    raw_json

)

VALUES (

    $1,

    $2,

    $3,

    to_timestamp($3),

    $4,

    to_timestamp($4),

    $5,

    $6,

    $7,

    $8,

    $9,

    $10,

    $11,

    $12,

    $13,

    $14::jsonb

);

```

  

---

  

## 10.4. Шаг 4. Обновить gps_current_position

  

Текущая позиция обновляется только если новая точка не старее уже сохраненной.

  

```sql

INSERT INTO gps_current_position (

    device_id,

    packet_id,

    navigation_unix_time,

    navigation_time,

    received_unix_time,

    received_time,

    latitude,

    longitude,

    speed,

    pdop,

    hdop,

    vdop,

    nsat,

    ns,

    course,

    raw_json,

    updated_at

)

VALUES (

    $1,

    $2,

    $3,

    to_timestamp($3),

    $4,

    to_timestamp($4),

    $5,

    $6,

    $7,

    $8,

    $9,

    $10,

    $11,

    $12,

    $13,

    $14::jsonb,

    CURRENT_TIMESTAMP

)

ON CONFLICT (device_id) DO UPDATE SET

    packet_id = EXCLUDED.packet_id,

    navigation_unix_time = EXCLUDED.navigation_unix_time,

    navigation_time = EXCLUDED.navigation_time,

    received_unix_time = EXCLUDED.received_unix_time,

    received_time = EXCLUDED.received_time,

    latitude = EXCLUDED.latitude,

    longitude = EXCLUDED.longitude,

    speed = EXCLUDED.speed,

    pdop = EXCLUDED.pdop,

    hdop = EXCLUDED.hdop,

    vdop = EXCLUDED.vdop,

    nsat = EXCLUDED.nsat,

    ns = EXCLUDED.ns,

    course = EXCLUDED.course,

    raw_json = EXCLUDED.raw_json,

    updated_at = CURRENT_TIMESTAMP

WHERE EXCLUDED.navigation_time >= gps_current_position.navigation_time;

```

  

---

  

# 11. Привязка GPS-устройства к автобусу

  

GPS-сервис не назначает автобус устройству.

  

Привязка выполняется отдельно.

  

Пример:

  

```sql

UPDATE bus_trackers

SET

    bus_number = 'А123ВС',

    updated_at = CURRENT_TIMESTAMP

WHERE device_id = 194918639;

```

  

После этого устройство считается связанным с автобусом.

  

---

  
  

# 14. Alembic-миграция

  

Миграции создаются в существующем API-сервисе.

  

Пример расположения файла:

  

```text

alembic/versions/20260701_0001_add_gps_egts_tables.py

```

  

Go-сервис `gps` не должен создавать таблицы самостоятельно.

  

Пример содержимого миграции:

  

```python

"""add gps egts tables

  

Revision ID: 20260701_0001

Revises: previous_revision_id

Create Date: 2026-07-01

"""

  

from alembic import op

  
  

revision = "20260701_0001"

down_revision = "previous_revision_id"

branch_labels = None

depends_on = None

  
  

def upgrade() -> None:

    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

  

    op.execute("""

        CREATE TABLE IF NOT EXISTS bus_trackers (

            device_id BIGINT PRIMARY KEY,

  

            bus_number VARCHAR(64) NULL

                REFERENCES buses(bus_number)

                ON UPDATE CASCADE

                ON DELETE SET NULL,

  

            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

  

            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,

  

            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP

        )

    """)

  

    op.execute("""

        CREATE INDEX IF NOT EXISTS bus_trackers_bus_number_idx

        ON bus_trackers(bus_number)

    """)

  

    op.execute("""

        CREATE INDEX IF NOT EXISTS bus_trackers_last_seen_idx

        ON bus_trackers(last_seen_at DESC)

    """)

  

    op.execute("""

        CREATE TABLE IF NOT EXISTS gps_timeline (

            id BIGINT GENERATED BY DEFAULT AS IDENTITY,

  

            device_id BIGINT NOT NULL

                REFERENCES bus_trackers(device_id)

                ON UPDATE CASCADE

                ON DELETE CASCADE,

  

            packet_id INTEGER NOT NULL,

  

            navigation_unix_time BIGINT NOT NULL,

            navigation_time TIMESTAMPTZ NOT NULL,

  

            received_unix_time BIGINT NOT NULL,

            received_time TIMESTAMPTZ NOT NULL,

  

            latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),

            longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),

  

            geom GEOMETRY(POINT, 4326)

                GENERATED ALWAYS AS (

                    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)

                ) STORED,

  

            speed INTEGER NOT NULL DEFAULT 0,

            pdop INTEGER NOT NULL DEFAULT 0,

            hdop INTEGER NOT NULL DEFAULT 0,

            vdop INTEGER NOT NULL DEFAULT 0,

            nsat INTEGER NOT NULL DEFAULT 0,

            ns INTEGER NOT NULL DEFAULT 0,

            course INTEGER NOT NULL DEFAULT 0,

  

            raw_json JSONB NOT NULL,

  

            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

  

            PRIMARY KEY (id, navigation_time)

        )

    """)

  

    op.execute("""

        SELECT create_hypertable(

            'gps_timeline',

            'navigation_time',

            if_not_exists => TRUE

        )

    """)

  

    op.execute("""

        CREATE INDEX IF NOT EXISTS gps_timeline_device_time_idx

        ON gps_timeline(device_id, navigation_time DESC)

    """)

  

    op.execute("""

        CREATE INDEX IF NOT EXISTS gps_timeline_packet_idx

        ON gps_timeline(device_id, packet_id, navigation_time DESC)

    """)

  

    op.execute("""

        CREATE INDEX IF NOT EXISTS gps_timeline_geom_gix

        ON gps_timeline USING GIST(geom)

    """)

  

    op.execute("""

        CREATE TABLE IF NOT EXISTS gps_current_position (

            device_id BIGINT PRIMARY KEY

                REFERENCES bus_trackers(device_id)

                ON UPDATE CASCADE

                ON DELETE CASCADE,

  

            packet_id INTEGER NOT NULL,

  

            navigation_unix_time BIGINT NOT NULL,

            navigation_time TIMESTAMPTZ NOT NULL,

  

            received_unix_time BIGINT NOT NULL,

            received_time TIMESTAMPTZ NOT NULL,

  

            latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),

            longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),

  

            geom GEOMETRY(POINT, 4326)

                GENERATED ALWAYS AS (

                    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)

                ) STORED,

  

            speed INTEGER NOT NULL DEFAULT 0,

            pdop INTEGER NOT NULL DEFAULT 0,

            hdop INTEGER NOT NULL DEFAULT 0,

            vdop INTEGER NOT NULL DEFAULT 0,

            nsat INTEGER NOT NULL DEFAULT 0,

            ns INTEGER NOT NULL DEFAULT 0,

            course INTEGER NOT NULL DEFAULT 0,

  

            raw_json JSONB NOT NULL,

  

            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP

        )

    """)

  

    op.execute("""

        CREATE INDEX IF NOT EXISTS gps_current_position_geom_gix

        ON gps_current_position USING GIST(geom)

    """)

  

    op.execute("""

        CREATE INDEX IF NOT EXISTS gps_current_position_time_idx

        ON gps_current_position(navigation_time DESC)

    """)

  
  

def downgrade() -> None:

    op.execute("DROP TABLE IF EXISTS gps_current_position")

    op.execute("DROP TABLE IF EXISTS gps_timeline")

    op.execute("DROP TABLE IF EXISTS bus_trackers")

```

  

---

  

# 15. Go-сервис

  

## 15.1. Назначение

  

Go-сервис отвечает за прием EGTS TCP-подключений, парсинг пакетов и запись данных в PostgreSQL.

  

---

  

## 15.2. Библиотека EGTS

  

В качестве основы используется Go-реализация EGTS-приемника:

  

```text

kuznetsovin/egts-protocol

```

Ссылка на модуль: https://github.com/kuznetsovin/egts-protocol

Допускается один из вариантов:

  

```text

1. Использовать проект как основу и встроить свой PostgreSQL/PostGIS/TimescaleDB store. (Более желательный)

2. Использовать библиотечную часть проекта и написать собственный receiver в папке gps.

```

  

Предпочтительный вариант для проекта:

  

```text

Использовать EGTS-парсер/receiver из kuznetsovin/egts-protocol,

но реализовать собственный storage-слой под текущую базу.

```

  

---

  

## 15.3. Конфигурация сервиса

  

Конфигурация может задаваться через YAML или environment variables.

  

Минимальные параметры:

  

```yaml

server:

  host: "0.0.0.0"

  port: 6000

  connection_live_seconds: 30

  

database:

  dsn: "postgres://user:password@localhost:5432/passenger_flow?sslmode=disable"

  max_connections: 10

  

logging:

  level: "info"

```

  

Также желательно поддержать переменные окружения:

  

```text

GPS_EGTS_HOST

GPS_EGTS_PORT

GPS_DATABASE_DSN

GPS_LOG_LEVEL

```

  

---

  

# 17. PostgreSQL storage в Go

  

Storage-слой должен выполнять одну атомарную операцию на каждую GPS-точку.

  

Операция должна включать:

  

```text

1. UPSERT bus_trackers

2. INSERT gps_timeline

3. UPSERT gps_current_position

```

  

Желательно выполнять эти действия в одной транзакции.

  

---

  

## 17.1. Алгоритм SaveGPSPoint

  

```text

SaveGPSPoint(point):

    1. validate point

    2. begin transaction

    3. upsert bus_trackers

    4. insert gps_timeline

    5. upsert gps_current_position

    6. commit transaction

```

  

Если на любом этапе произошла ошибка:

  

```text

1. rollback transaction

2. записать ошибку в лог

3. не завершать работу сервиса

```

  

---

  

## 17.2. Валидация координат

  

Перед записью в БД сервис должен проверять:

  

```text

latitude >= -90 && latitude <= 90

longitude >= -180 && longitude <= 180

```

  

Если координаты некорректные, точка не записывается.

  

Ошибка должна попасть в лог.

  

---

  

## 17.3. Обработка времени

  

Сервис должен хранить оба времени:

  

```text

navigation_unix_time — время навигационной точки

received_unix_time — время получения/обработки

```

  

В базе дополнительно сохраняются:

  

```text

navigation_time = to_timestamp(navigation_unix_time)

received_time = to_timestamp(received_unix_time)

```

  

---

  

# 18. Обновление gps_current_position

  

Таблица `gps_current_position` обновляется по `device_id`.

  

Если записи еще нет, она создается.

  

Если запись уже есть, она обновляется только при условии:

  

```text

новая navigation_time >= старая navigation_time

```

  

Это защищает от перезаписи актуальной позиции старым пакетом.

  

---

  

# 19. Логирование

  

Сервис должен логировать:

  

```text

старт сервиса

адрес и порт TCP-сервера

успешное подключение GPS-устройства

отключение GPS-устройства

ошибку парсинга EGTS-пакета

ошибку валидации координат

ошибку записи в PostgreSQL

автоматическое создание нового bus_trackers.device_id

```

  

Логи должны быть пригодны для просмотра через Docker logs или systemd journal.

  

---

  

# 20. Поведение при неизвестном устройстве

  

Если пришел пакет:

  

```json

{

  "client": 194918639

}

```

  

И в `bus_trackers` нет `device_id = 194918639`, сервис должен автоматически создать:

  

```text

device_id: 194918639

bus_number: NULL

first_seen_at: now()

last_seen_at: now()

meta_json: {}

```

  

После этого точка должна быть записана в `gps_timeline`, а `gps_current_position` должна быть обновлена.

  

---

  

# 21. Поведение при известном устройстве

  

Если `device_id` уже есть в `bus_trackers`, сервис должен обновить:

  

```text

last_seen_at

updated_at

```

  

Поле `bus_number` при этом не изменяется.

  

---

  

# 22. Поведение при привязанном автобусе

  

Если в `bus_trackers` есть:

  

```text

device_id = 194918639

bus_number = А123ВС

```

  

GPS-сервис продолжает писать данные только по `device_id`.

  

Для получения автобуса используется JOIN.

  

Сам Go-сервис не должен копировать `bus_number` в `gps_timeline` или `gps_current_position`.

  

---

  

# 23. Поведение при удалении автобуса

  

Так как `bus_trackers.bus_number` имеет:

  

```sql

ON DELETE SET NULL

```

  

при удалении автобуса из `buses` связь с устройством должна обнулиться.

  

GPS-история и текущая позиция устройства при этом остаются.

  

---

  

# 24. Масштабирование

  

Сервис должен быть рассчитан минимум на автопарк от 100 устройств с возможностью дальнейшего роста.

  

Для первой версии допускается запись каждой точки отдельной транзакцией.

  

Для следующей версии желательно предусмотреть оптимизацию:

  

```text

1. batch insert в gps_timeline

2. отдельная очередь записи в PostgreSQL

3. ограничение количества одновременных TCP-подключений

4. pgxpool для пула соединений

```

  

---

  

# 25. Требования к надежности

  

Сервис должен:

  

```text

1. Не падать при ошибочном EGTS-пакете.

2. Не падать при неизвестном device_id.

3. Не падать при потере одного TCP-подключения.

4. Корректно закрывать соединение с PostgreSQL при остановке.

5. Обрабатывать SIGTERM/SIGINT.

6. Завершаться gracefully.

7. Логировать ошибки записи в БД.

```

  

---

  

# 26. Healthcheck

  

Желательно добавить HTTP healthcheck-сервер.

  

Минимальный endpoint:

  

```text

GET /healthz

```

  

Ответ при рабочем сервисе:

  

```json

{

  "status": "ok"

}

```

  

Если нет подключения к PostgreSQL:

  

```json

{

  "status": "error",

  "database": "unavailable"

}

```

  

Healthcheck-порт можно вынести отдельно:

  

```yaml

health:

  host: "0.0.0.0"

  port: 8001

```

  

---

  

# 27. Тестирование

  

## 27.1. Unit-тесты

  

Нужно проверить:

  

```text

маппинг client -> device_id

валидацию latitude

валидацию longitude

преобразование unix time

логику выбора новой current position

```

  

---

  

## 27.2. Integration-тесты ()

  

Нужно проверить на тестовой PostgreSQL + PostGIS + TimescaleDB базе:

  

```text

1. неизвестный device_id автоматически создает bus_trackers

2. GPS-точка пишется в gps_timeline

3. gps_current_position создается

4. более новая точка обновляет gps_current_position

5. более старая точка не перезаписывает gps_current_position

6. bus_number может быть NULL

7. bus_number можно назначить позже

```

  
  

---

  

# 28. Критерии приемки

  

Работа считается выполненной, если:

  

```text

1. В проекте появилась отдельная папка gps.

2. Go-сервис запускается отдельно от API.

3. Миграции GPS-таблиц выполняются через api/alembic.

4. Создаются таблицы bus_trackers, gps_timeline, gps_current_position.

5. gps_timeline является TimescaleDB hypertable.

6. В таблицах есть PostGIS geometry POINT.

7. При первом пакете от неизвестного client создается bus_trackers.device_id.

8. bus_trackers.bus_number остается NULL до ручной привязки.

9. Каждая GPS-точка сохраняется в gps_timeline.

10. gps_current_position обновляется только более свежей точкой.

11. Go-сервис не трогает passenger_timeline.

12. Go-сервис не трогает device_current_status.

13. Go-сервис не трогает device_events.

14. Go-сервис не изменяет buses.

15. Go-сервис использует buses только через FK из bus_trackers.

16. Сервис логирует ошибки, но не падает от одного битого пакета.

```

  

---

  

# 29. Итоговая схема данных

  

```text

buses

  ↑

  │ nullable FK

  │

bus_trackers

  device_id PK

  bus_number NULL

  

gps_timeline

  device_id FK

  вся история GPS-точек

  

gps_current_position

  device_id PK

  последняя позиция GPS-устройства

```

  

---

  

# 30. Итоговая схема работы

  

```text

GPS-трекер

   ↓

EGTS TCP

   ↓

Go gps service

   ↓

parse EGTS

   ↓

client -> device_id

   ↓

UPSERT bus_trackers

   ↓

INSERT gps_timeline

   ↓

UPSERT gps_current_position

   ↓

PostgreSQL + TimescaleDB + PostGIS

```

Ты работаешь на локальном пк

Тут доступен go, и docker compose

Используй их для написание и всех тестов

Получение egts идет через прослушку 9000 порта

Так же сделай заготовку под расширение docker-compose.yml,тк запускать gps egts сервис через него