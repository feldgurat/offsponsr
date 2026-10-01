export default {
  app: {
    title: 'offsponsr',
    version: 'Версия {version}',
    loading: 'Загрузка…',
    backendError: {
      title: 'Нет связи с приложением',
      hint: 'Интерфейс не смог подключиться к своей серверной части. Закройте окно и запустите offsponsr заново.',
    },
  },
  welcome: {
    lead: 'Локальная копия ваших подписок sponsr.ru',
    create: 'Создать библиотеку',
    open: 'Открыть существующую',
    hint: 'Библиотека — это папка с базой данных, текстами и медиа. Для новой библиотеки выберите пустую папку.',
    lastFailure: 'Не удалось открыть библиотеку, с которой вы работали в прошлый раз',
  },
  // Keyed by the error codes of the backend (offsponsr/library/errors.py).
  libraryError: {
    missing: 'Папка не найдена. Возможно, диск отключён или папку переместили.',
    not_a_library: 'В этой папке нет библиотеки offsponsr.',
    not_empty: 'Папка не пуста. Для новой библиотеки выберите пустую папку.',
    already_library:
      'В этой папке уже есть библиотека. Откройте её кнопкой «Открыть существующую».',
    locked: 'Библиотека уже открыта в другом окне offsponsr.',
    too_new: 'Библиотека создана более новой версией offsponsr. Обновите приложение.',
    unknown: 'Не удалось открыть папку.',
  },
  library: {
    title: 'Библиотека',
    empty: 'В библиотеке пока нет проектов',
    signInHint: 'Войдите в sponsr.ru, чтобы добавить проекты из ваших подписок.',
    addHint: 'Добавьте проекты из ваших подписок или по ссылке.',
    addProjects: 'Добавить проекты',
    updateAll: 'Обновить всё',
    update: 'Обновить',
    // none | one | few | many
    posts: 'нет постов | {n} пост | {n} поста | {n} постов',
    neverSynced: 'ещё не скачан',
    syncedAt: 'обновлён {date}',
    withoutText: 'без полного текста: {n}',
    running: 'Обновляется',
    queued: 'В очереди',
  },
  addProjects: {
    title: 'Добавить проекты',
    subscriptions: 'Ваши подписки',
    noSubscriptions: 'У этого аккаунта нет платных подписок.',
    inLibrary: 'уже в библиотеке',
    byAddress: 'Проект по ссылке',
    addressPlaceholder: 'https://sponsr.ru/название-проекта/',
    addressHint:
      'Можно добавить любой проект. Скачаются только посты, которые открыты вашему аккаунту.',
    submit: 'Добавить и скачать',
    // Keyed by the error codes of the backend.
    errors: {
      not_signed_in: 'Войдите в sponsr.ru, чтобы увидеть подписки.',
      session_expired: 'Сессия sponsr.ru истекла. Войдите заново.',
      site_unavailable:
        'sponsr.ru не отвечает. Проверьте подключение к интернету и попробуйте ещё раз.',
      site_changed:
        'sponsr.ru ответил в незнакомом формате: возможно, сайт изменился и нужна новая версия offsponsr.',
      site_refused: 'sponsr.ru отказал в доступе.',
      invalid_address: 'Это не похоже на адрес проекта на sponsr.ru.',
      project_not_found: 'На sponsr.ru нет проекта с таким адресом.',
      unknown: 'Не получилось. Подробности в журнале приложения.',
    },
  },
  sync: {
    running: 'Обновляется: {title}',
    preparing: 'Подготовка…',
    progress: '{done} из {total} постов',
    queue: 'В очереди: {n}',
    cancel: 'Отменить',
    cancelling: 'Останавливается…',
    failed: 'Не удалось обновить «{title}»',
    // Keyed by the error codes of the backend.
    errors: {
      not_signed_in: 'Нужен вход в sponsr.ru.',
      session_expired: 'Сессия sponsr.ru истекла. Войдите заново и запустите обновление ещё раз.',
      site_unavailable: 'sponsr.ru не отвечает. Попробуйте позже.',
      site_changed:
        'sponsr.ru ответил в незнакомом формате: возможно, сайт изменился и нужна новая версия offsponsr.',
      site_refused: 'sponsr.ru отказал в доступе к проекту.',
      unknown: 'Неизвестная ошибка. Подробности в журнале приложения.',
    },
  },
  account: {
    signIn: 'Войти',
    signOut: 'Выйти',
    signingIn: 'Войдите в открывшемся окне sponsr.ru',
    withCookie: 'Войти по cookie',
    expired: 'Сессия sponsr.ru истекла. Войдите заново.',
    cookieModal: {
      title: 'Вход по строке Cookie',
      intro: 'Запасной способ на случай, если окно входа не срабатывает.',
      steps: [
        'Откройте sponsr.ru в браузере, где вы уже вошли.',
        'Нажмите F12, перейдите на вкладку «Сеть» (Network) и обновите страницу.',
        'Выберите любой запрос к sponsr.ru и скопируйте значение заголовка Cookie из заголовков запроса.',
        'Вставьте его в поле ниже.',
      ],
      placeholder: 'name=value; name2=value2',
      warning: 'Эта строка даёт доступ к вашему аккаунту. Никому её не передавайте.',
    },
    // Keyed by the error codes of the backend (offsponsr/auth/errors.py).
    errors: {
      no_library: 'Сначала откройте библиотеку.',
      login_in_progress: 'Окно входа уже открыто.',
      different_account:
        'Эта библиотека привязана к другому аккаунту sponsr.ru. Для этого аккаунта создайте отдельную библиотеку.',
      invalid_cookie:
        'sponsr.ru не принимает эти cookie. Скопируйте строку заново из браузера, где вы вошли.',
      site_unavailable:
        'Не удалось связаться с sponsr.ru. Проверьте подключение к интернету и попробуйте ещё раз.',
      unknown: 'Не удалось войти.',
    },
  },
}
