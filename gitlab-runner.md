# Запустите контейнер GitLab Runner

```sh
docker run -d --name gitlab-runner --restart always \
  -v /srv/gitlab-runner/config:/etc/gitlab-runner \
  -v /var/run/docker.sock:/var/run/docker.sock \
  gitlab/gitlab-runner:latest
```


# Запустите процесс регистрации
```sh
docker exec -it gitlab-runner gitlab-runner register
```

Терминал задаст несколько вопросов. Ответьте на них:
- GitLab instance URL: [https://gitlab.com/](https://gitlab.com/) (или ваш собственный домен).
- Registration token: Вставьте токен, полученный на странице Settings > CI/CD > Runners в вашем проекте.
- Description: Любое понятное имя (например, docker-runner-1).
- Executor: Напечатайте docker.
- Default Docker image: Укажите базовый образ, который будет использоваться, если в пайплайне не указан другой (например, alpine:latest или node:20).

