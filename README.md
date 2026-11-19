# BionicPRO

## Задание 1. Повышение безопасности системы

Архитектура аутентификации BionicPRO. Вход через BFF bionicpro-auth (Spring Boot) по OIDC Authorization Code Flow + PKCE, Keycloak выступает Identity Broker (IdP RU — OIDC/OpenLDAP, IdP EU — SAML/OIDC), сессии и refresh-токены хранятся в Redis. Дополнительно показаны интеграции с интернет-магазином и CRM (Битрикс24), API, PostgreSQL и клиентский tooling.

## Задание: миграция на PKCE

Публичный клиент reports-frontend переведён с обычного Code Grant на Authorization Code Flow + PKCE:

- в `keycloak/realm-export.json` клиенту задан pkce.code.challenge.method: S256, directAccessGrantsEnabled отключён;
- в `frontend/src/App.tsx` добавлен pkceMethod: S256 в init-опции keycloak-js.

## Запуск локально

```bash
docker compose down -v   # обязательно, если Keycloak уже запускался ранее (realm импортируется только при первом старте)
docker compose up -d
```

После старта: http://localhost:3000 (фронтенд), консоль Keycloak — http://localhost:8080 (admin / admin). Тестовые пользователи: user1/password123 (user), prothetic1/prothetic123 (prothetic_user), admin1/admin123 (administrator).

## Проверка выполнения задания

1. Открыть http://localhost:3000, нажать Login, пройти авторизацию через страницу Keycloak, убедиться в редиректе обратно в приложение.

2. Проверка через DevTools вкладка Network: в запросе к /protocol/openid-connect/auth присутствуют параметры code_challenge и code_challenge_method=S256, в обмене кода на токен присутствует code_verifier.

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
