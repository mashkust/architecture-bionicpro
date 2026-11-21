# BionicPRO

## Задание 1. Повышение безопасности системы

### [Задача 1. Предложите архитектурное решение и доработайте диаграмму C4 для управления учётными данными пользователя.](./task1-c4.png)

### Задача 2. Улучшите безопасность существующего приложения, заменив Code Grant на PKCE.

Публичный клиент reports-frontend переведён с обычного Code Grant на Authorization Code Flow + PKCE:

- в keycloak/realm-export.json клиенту задан pkce.code.challenge.method: S256, directAccessGrantsEnabled отключён;
- в frontend/src/App.tsx добавлен pkceMethod: S256 в init-опции keycloak-js.

#### Запуск локально

```bash
docker compose down -v   # если Keycloak уже запускался ранее
docker compose up -d
```

После старта: http://localhost:3000 (фронтенд), консоль Keycloak — http://localhost:8080 (admin / admin). Тестовые пользователи: user1/password123 (user), prothetic1/prothetic123 (prothetic_user), admin1/admin123 (administrator).

#### Проверка

1. Открыть http://localhost:3000, нажать Login, пройти авторизацию через страницу Keycloak, убедиться в редиректе обратно в приложение.

2. Проверка через Network: в запросе к /protocol/openid-connect/auth присутствуют параметры code_challenge и code_challenge_method=S256, в обмене кода на токен присутствует code_verifier.

3. Проверка настроек клиента в консоли Keycloak:
   - открыть http://localhost:8080, войти как admin / admin, выбрать realm reports-realm;
   - в меню Clients открыть reports-frontend;
   - в блоке Capability config поле Proof Key for Code Exchange Code Challenge Method должно быть S256 (не none), переключатель Direct access grants - выключен.
   - В ответе должен быть pkce.code.challenge.method со значением S256, а directAccessGrantsEnabled отсутствовать. Если вместо S256 указано none — realm не переимпортировался, нужно выполнить docker compose down -v и docker compose up -d.

4. Проверка отключения password-гранта: POST к /realms/reports-realm/protocol/openid-connect/token с grant_type=password для клиента reports-frontend должен вернуть ошибку unauthorized_client.

```bash
curl -s -X POST http://localhost:8080/realms/reports-realm/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=reports-frontend&username=user1&password=password123"
```

## Задание 2. Разработка сервиса отчётов

### [Задача 1. Создать архитектуру решения для подготовки и получения отчётов.](./task2-c4.png)

### Задача 2. Разработать Airflow DAG и настроить его на запуск по расписанию.

#### Запуск локально

```bash
docker compose -f airflow/docker-compose.yaml down -v
docker compose -f airflow/docker-compose.yaml up -d
```

Airflow UI: http://localhost:8081, пользователь admin / admin. DAG bionicpro_etl_reports виден, расписание @daily (00:00 UTC), прошлые запуски success.

#### Проверка

Сид-данные уже лежат во вчерашних сутках, поэтому достаточно просто включить DAG — scheduler сам запустит вчерашний интервал.

1. Вкладка DAGs => включить Pause у bionicpro_etl_reports. Через пару минут в Grid все таски success.

2. Проверить, что ETL отработал: Grid => таск build_report_mart => вкладка Log — строка Mart for <вчера>: 3 rows built.

3. Убедиться, что данные на месте:

```bash
docker compose -f airflow/docker-compose.yaml exec clickhouse clickhouse-client \
  --query "SELECT email, report_date, total_sessions, total_movements FROM bionicpro.report_mart ORDER BY email"
```

В витрине — по одной строке на клиента за вчерашний день:

| email                  | сессии | движений |
| ---------------------- | ------ | -------- |
| prothetic1@example.com | 3      | 3330     |
| prothetic2@example.com | 2      | 3450     |
| prothetic3@example.com | 2      | 1400     |

### Задача 3. Разработать бэкенд API отчётов (Python/FastAPI).

Бэкенд в backend/ (FastAPI, порт 8000) отдаёт подготовленный отчёт через GET /reports. Отчёт не вычисляется на лету: API делает простую выборку из OLAP-витрины bionicpro.report_mart (ClickHouse), которую заранее собрал Airflow DAG bionicpro_etl_reports.

Пользователь определяется по JWT-токену Keycloak (email из claims); токен проверяется по JWKS realm-а (/realms/reports-realm/protocol/openid-connect/certs). Доступ к отчётам ограничен ролями prothetic_user / administrator - 403 для остальных.

#### Запуск локально

```bash
docker compose -f airflow/docker-compose.yaml up -d
docker compose up -d --build
```

API: http://localhost:8000, документация OpenAPI — http://localhost:8000/docs.

#### Проверка

1. Авторизованный путь: открыть http://localhost:3000, войти как prothetic1 / prothetic123, нажать Download Report — фронтенд шлёт GET /reports с Bearer-токеном.

2. Ошибки: без токена — 401; роль user (user1) — 403; нет данных за дату — 404; недоступен ClickHouse — 503.

### Задача 4. Ограничить доступ к эндпоинту отчётности

Доступ к отчёту предоставляется только в отношении себя: пользователь не может запросить отчёт другого пользователя. Email всегда берётся из проверенного JWT, а опциональный параметр user разрешён только если он совпадает с ним — иначе 403.

#### Проверка

Токен берётся из браузера: войти на http://localhost:3000 как prothetic1 / prothetic123, в запросе к /reports скопировать Bearer-токен.

```bash
curl -s -H "Authorization: $TOKEN" "http://localhost:8000/reports?user=prothetic1@example.com"
curl -s -H "Authorization: $TOKEN" "http://localhost:8000/reports?user=prothetic2@example.com"
```

### Задача 5. Кнопка генерации отчёта в UI

В UI (http://localhost:3000) добавлена кнопка Generate Report: она вызывает POST /reports/generate. Бэкенд сам находит день с последними данными телеметрии в ClickHouse и запускает ETL.Если за этот день уже есть успешный run (от предыдущей генерации или backfill), новый не запускается — эндпоинт вернёт already_generated.

Если DAG приостановлен (после пересоздания метаданных Airflow), API-ранны будут висеть в состоянии queued. Включить:

```bash
 docker compose -f airflow/docker-compose.yaml exec airflow airflow dags unpause bionicpro_etl_reports
```

#### Проверка

1. Войти на http://localhost:3000 как prothetic1 / prothetic123.
2. Нажать Generate Report — появится сообщение о запуске генерации.
3. Подождать, нажать Download Report — в ответе должен быть отчёт (200).
4. Убедиться в Airflow UI (http://localhost:8081, admin/admin): DAG bionicpro_etl_reports содержит свежий run в состоянии success.
