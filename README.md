# offsponsr

Десктоп-приложение, которое хранит локальную копию ваших подписок на [sponsr.ru](https://sponsr.ru) и показывает её в интерфейсе, похожем на сайт. Содержимое обновляется с сайта по кнопке.

Проект в разработке, готовых сборок пока нет.

Чтобы скачивать видео, нужен [ffmpeg](https://ffmpeg.org/): видео приходит частями, и ffmpeg собирает их в один файл. Тексты, картинки, аудио и вложения скачиваются и без него. Если ffmpeg в системе нет, на Windows приложение предложит установить его через winget; в настройках можно указать и свой файл ffmpeg.

## Разработка

Нужны Python 3.12+, [uv](https://docs.astral.sh/uv/) и Node.js 24 LTS.

```bash
uv sync
```

```bash
npm --prefix frontend install
```

Запуск собранного приложения:

```bash
npm --prefix frontend run build
```

```bash
uv run offsponsr
```

Запуск с горячей перезагрузкой интерфейса (два терминала):

```bash
npm --prefix frontend run dev
```

```bash
uv run offsponsr --dev
```

Проверки:

```bash
uv run ruff check
```

```bash
uv run ruff format --check
```

```bash
uv run pytest
```

```bash
npm --prefix frontend run check
```

## Лицензия

BSD-3-Clause, см. [LICENSE](LICENSE). Код скачивания медиа переносится из [sponsrdump](https://github.com/idlesign/sponsrdump) (BSD-3-Clause, © Igor Starikov).
