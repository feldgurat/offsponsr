"""Made-up answers of sponsr.ru, in the shape of the real ones.

Everything here is invented: the project, the people, the texts. The structure (field names,
value formats, which fields a closed post lacks) follows real answers looked at on 2026-10-01;
no real answer is stored in the repository.
"""

import json

PROJECT_ID = 4242
PROJECT_URL = 'fictional-almanac'
OWNER_EMAIL = 'author@example.com'
USER_ID = 123456

LEVEL_BASIC = 501
LEVEL_HIDDEN = 502
LEVEL_DELETED = 503

TAG_ESSAYS = 71
TAG_TALKS = 72

POST_SHORT = 9006
POST_LONG = 9005
POST_VIDEO = 9004
POST_AUDIO = 9003
POST_CLOSED = 9002
POST_FREE = 9001

KINESCOPE_EMBED = 'https://kinescope.io/aBcDeFgHiJkLmNoPqRsTuV'
VIDEO_ID = '0a1b2c3d-1111-4222-8333-444455556666'
POSTER_ID = '9f8e7d6c-aaaa-4bbb-8ccc-ddddeeeeffff'

# The two direction marks the legacy list puts between words.
MARKS = chr(0x200E) + chr(0x200F)

IMAGE = (
    '<img src="https://media.sponsr.ru/project/4242/post/9006/image/31/imagesprojects42ab12cd.webp?1a2b3c" '
    'data-src="https://media.sponsr.ru/project/4242/post/9006/image/31/imagesprojects42ab12cd.webp?1a2b3c" alt />'
)
VIDEO = (
    f'<iframe src="{KINESCOPE_EMBED}" data-url="/post/video/?video_id={VIDEO_ID}?poster_id={POSTER_ID}" '
    'loading="lazy" allow="autoplay; fullscreen" allowfullscreen="true" frameborder="0" '
    'allowtransparency="true" scrolling="no"></iframe>'
)

FULL_TEXTS = {
    POST_SHORT: f'<p>Короткая заметка целиком помещается в список.</p><p>{IMAGE}</p>',
    POST_LONG: '<h2>Длинное эссе</h2>'
    + ''.join(f'<p>Абзац номер {number} выдуманного эссе.</p>' for number in range(1, 41)),
    POST_VIDEO: f'<p>Запись выдуманной лекции.</p><div>{VIDEO}</div>',
    POST_AUDIO: '<p>Выпуск выдуманного подкаста.</p>',
    POST_FREE: '<p>Открытое объявление для всех.</p>',
}
# What the post list gives for the long post: the beginning only.
TRUNCATED_LONG = FULL_TEXTS[POST_LONG][:300]


def subscribed():
    return {
        'total': 1,
        'list': [
            {
                'id': PROJECT_ID,
                'url': PROJECT_URL,
                'title': 'Вымышленный альманах',
                'owner': {
                    'id': 77,
                    'name': 'Автор Выдуманный',
                    'avatar': '2023-10-14T09:00:00.000Z',
                    'avatarPath': '/images/avatars/0/77/avatar.webp',
                    'email': OWNER_EMAIL,
                },
                'message_access_type': 'all',
                'message_access_value': None,
                'project_status': 'approving',
                'project_offline': None,
                'can_message': 1,
                'last_paid': '2026-09-21T10:15:00.000Z',
                'status': 'active',
                'months': 1,
                'subscribe_can_comment': 1,
                'next_level_id': LEVEL_BASIC,
                'logo': {
                    '1x': '/images/projects/42/4242/logo.webp?5d41402abc4b2a76',
                    '2x': '/images/projects/42/4242/logo@2x.webp?5d41402abc4b2a76',
                },
                'level': {'id': LEVEL_BASIC, 'name': 'Читатель', 'price': '300'},
            }
        ],
    }


def _tag(post_id, tag_id, name):
    return {
        'post_id': post_id,
        'tag_id': tag_id,
        'count': 2,
        'ts': '2026-09-01T08:00:00.000Z',
        'tag': {
            'id': tag_id,
            'tag_name': name,
            'image': None,
            'project_id': PROJECT_ID,
            'ts': '2026-08-01T08:00:00.000Z',
        },
    }


def post(post_id, title, date, *, html, truncated, level_id=LEVEL_BASIC, content_type='text', **extra):
    """A readable post as the post list gives it."""
    return _post(
        post_id, title, date, html=html, truncated=truncated, level_id=level_id, content_type=content_type, **extra
    )


def closed_post(post_id, title, date, *, level_id=LEVEL_HIDDEN):
    """A post the account can't read: it comes without its text and without a dozen other fields."""
    return {
        'id': post_id,
        'project_id': PROJECT_ID,
        'level_id': level_id,
        'date': date,
        'title': title,
        'teaser': None,
        'image': None,
        'pinned': 0,
        'access_type': None,
        'access_value': 0,
        'price_old': None,
        'price': None,
        'duration_podcast': 0,
        'duration_text': 600,
        'duration_video': 0,
        'meta_description': None,
        'cnt_likes': 0,
        'cnt_comments': 0,
        'project_access_type': 'active',
        'tags': [],
        'video_posters': [],
        'available': False,
        'isLiked': False,
    }


def tag(post_id, tag_id, name):
    return _tag(post_id, tag_id, name)


def marked(html):
    """Text as the legacy list has it."""
    return _marked(html)


def _post(post_id, title, date, *, html, truncated, level_id=LEVEL_BASIC, content_type='text', **extra):
    post = {
        'id': post_id,
        'project_id': PROJECT_ID,
        'level_id': level_id,
        'date': date,
        'title': title,
        'content_type': content_type,
        'poll': None,
        'teaser': None,
        'rss_teaser': None,
        'image': None,
        'image_access': None,
        'status': 'active',
        'notified': 1,
        'pinned': 0,
        'extended_view': 0,
        'access_type': None,
        'access_value': 0,
        'price_old': None,
        'price': None,
        'duration_podcast': 0,
        'duration_text': 120,
        'duration_video': 0,
        'hide_on_landing': 0,
        'meta_description': None,
        'meta_title': None,
        'created_at': date,
        'updated_at': date,
        'cnt_likes': 3,
        'cnt_comments': 1,
        'views': 250,
        'name_type': None,
        'ts': date,
        'project_access_type': 'active',
        'tags': [],
        'text': {'post_id': post_id, 'text': html, 'ts': date},
        'files': [],
        'video_posters': [],
        'text_truncated': truncated,
        'available': True,
        'isLiked': False,
    }
    post.update(extra)
    return post


def posts_page():
    """The first (and only) page of the project's posts, newest first."""
    closed = {
        # A post the account can't read comes without its text and without a dozen other fields.
        'id': POST_CLOSED,
        'project_id': PROJECT_ID,
        'level_id': LEVEL_HIDDEN,
        'date': '2026-09-26T07:00:00.000Z',
        'title': 'Закрытый материал для старшего уровня',
        'teaser': None,
        'image': '/images/projects/42/4242/1a/bc/de/9002cover.jpg',
        'pinned': 0,
        'access_type': None,
        'access_value': 0,
        'price_old': None,
        'price': None,
        'duration_podcast': 0,
        'duration_text': 600,
        'duration_video': 0,
        'meta_description': None,
        'cnt_likes': 0,
        'cnt_comments': 0,
        'project_access_type': 'active',
        'tags': [],
        'video_posters': [],
        'available': False,
        'isLiked': False,
    }
    return {
        'total': 6,
        'page': 1,
        'limit': 20,
        'list': [
            _post(
                POST_SHORT,
                'Короткая заметка',
                '2026-09-30T18:15:00.000Z',
                html=FULL_TEXTS[POST_SHORT],
                truncated=False,
                content_type='image',
                image='/images/projects/42/4242/7e/yn/u4//42ab12cd_original.webp',
                image_access='/images/projects/42/4242/7e/yn/u4//5d41402abc4b2a76_access.webp',
            ),
            _post(
                POST_LONG,
                'Длинное эссе',
                '2026-09-29T09:00:00.000Z',
                html=TRUNCATED_LONG,
                truncated=True,
                updated_at='2026-09-29T12:30:00.000Z',
                tags=[_tag(POST_LONG, TAG_ESSAYS, 'Эссе')],
            ),
            _post(
                POST_VIDEO,
                'Лекция',
                '2026-09-28T16:00:00.000Z',
                html=FULL_TEXTS[POST_VIDEO],
                truncated=False,
                content_type='video',
                duration_video=3120,
                tags=[_tag(POST_VIDEO, TAG_TALKS, 'Лекции')],
                video_posters=[
                    {
                        'type': 'kinescope',
                        'iframe_src': f'/post/video/?video_id={VIDEO_ID}?poster_id={POSTER_ID}',
                        'poster_url': f'https://kinescopecdn.net/0a1b2c3d/posters/{VIDEO_ID}/{POSTER_ID}.webp?expires=1790000000&sign=abcdef',
                    }
                ],
            ),
            _post(
                POST_AUDIO,
                'Подкаст',
                '2026-09-27T06:30:00.000Z',
                html=FULL_TEXTS[POST_AUDIO],
                truncated=False,
                duration_podcast=1835,
                tags=[_tag(POST_AUDIO, TAG_TALKS, 'Лекции')],
                files=[
                    {
                        'id': 6001,
                        'post_id': POST_AUDIO,
                        'project_id': PROJECT_ID,
                        'user_id': 77,
                        'category': 'podcast',
                        'mime': 'audio/mpeg',
                        'name': 'ALMANAC_012.mp3',
                        'title': 'Альманах, выпуск 12',
                        'path': '/uploads/files/p4242/9003/aaf/zdw/1c2/0123456789abcdef/almanac-012-0123abcd.mp3',
                        'preview_path': None,
                        'size': '48211234',
                        'duration': '1834.56',
                        'chunk': '1048576',
                        'hash': '0123456789abcdef0123456789abcdef',
                        'order': 0,
                        'completed': 0,
                        'is_temp': 0,
                        'is_deleted': 0,
                        'upload_state': 'completed',
                        'upload_uid': None,
                        'kinescope_id': None,
                        'kinescope_short_id': None,
                        'created_at': '2026-09-27T06:00:00.000Z',
                        'ts': '2026-09-27T06:00:00.000Z',
                    }
                ],
            ),
            closed,
            _post(
                POST_FREE,
                'Объявление',
                '2026-09-25T12:00:00.000Z',
                html=FULL_TEXTS[POST_FREE],
                truncated=False,
                level_id=None,
                pinned=1,
            ),
        ],
    }


def _marked(html):
    """Text as the legacy list has it: the invisible marks sit after the spaces."""
    return html.replace(' ', f' {MARKS}')


def more_posts():
    """The same page from the legacy list, which is where the whole texts come from."""
    rows = []
    for post in posts_page()['list']:
        post_id = post['id']
        rows.append(
            {
                'post_id': post_id,
                'project_id': PROJECT_ID,
                'project_title': 'Вымышленный альманах',
                'project_url': PROJECT_URL,
                'project_logo': {
                    '1x': '/images/projects/42/4242/logo.webp',
                    '2x': '/images/projects/42/4242/logo@2x.webp',
                },
                'post_title': post['title'],
                'post_date': post['date'],
                'post_text': _marked(FULL_TEXTS.get(post_id, '')),
                'post_url': f'/{PROJECT_URL}/{post_id}/slug',
                'post_status': 'active',
                'post_image': post.get('image'),
                'post_teaser': None,
                'post_views': 250,
                'post_cnt_likes': 3,
                'post_cnt_comments': 1,
                'post_duration_text': post['duration_text'],
                'post_duration_podcast': post['duration_podcast'],
                'post_duration_video': post['duration_video'],
                'level_id': post['level_id'] or 0,
                'level_name': 'Читатель',
                'level_price': 300,
                'files': None,
                'tags': [],
                'tag_ids': [],
                '_available': post['available'],
                '_available_after_sub': True,
                '_like': False,
            }
        )
    return {'response': {'rows': rows, 'rows_count': len(rows), '_like': False}}


def _level(level_id, name, price, *, visible='visible', status='active', description='<p>Все тексты альманаха.</p>'):
    return {
        'id': level_id,
        'project_id': PROJECT_ID,
        'level_name': name,
        'level_price': price,
        'level_description': description,
        'level_visible': visible,
        'level_status': status,
        'level_limit': None,
        'level_subscribers': 12,
        'level_can_comment': 1,
        'level_comment_disable': 0,
        'is_level_isolated': 0,
        'can_comment': True,
        'change_price_available': None,
        'old_level_price': None,
        'ts': '2025-01-10T10:00:00.000Z',
    }


def levels():
    items = [
        _level(LEVEL_BASIC, 'Читатель', '300'),
        _level(LEVEL_HIDDEN, 'Меценат', '1500', visible='hidden', description='Без разметки'),
        _level(LEVEL_DELETED, 'Старый уровень', '100', status='deleted'),
    ]
    return {'total': len(items), 'page': 1, 'limit': 20, 'list': items}


def playlist():
    items = [
        {
            'id': TAG_ESSAYS,
            'project_id': PROJECT_ID,
            'tag_name': 'Эссе',
            'count': 1,
            'image': None,
            'ts': '2026-08-01T08:00:00.000Z',
        },
        {
            'id': TAG_TALKS,
            'project_id': PROJECT_ID,
            'tag_name': 'Лекции',
            'count': 2,
            'image': None,
            'ts': '2026-08-02T08:00:00.000Z',
        },
    ]
    return {'total': len(items), 'page': 1, 'limit': 20, 'list': items}


def project_page_props():
    return {
        'project': {
            'id': PROJECT_ID,
            'project_url': PROJECT_URL,
            'project_title': 'Вымышленный альманах',
            'project_intent': 'на выдуманные тексты',
            'project_status': 'approving',
            'image': '/images/projects/42/4242/bg.webp?5d41402abc4b2a76',
            'logo': {
                '1x': '/images/projects/42/4242/logo.webp?5d41402abc4b2a76',
                '2x': '/images/projects/42/4242/logo@2x.webp?5d41402abc4b2a76',
            },
            'description': {
                'project_id': PROJECT_ID,
                'description': '<p>Альманах, которого <b>не существует</b>.</p>',
                'lp_description': 'Альманах, которого не существует.',
                'lp_keywords': None,
                'ts': '2025-01-10T10:00:00.000Z',
            },
            'project_stats': {
                'project_active_posts_amount': 6,
                'project_income_all_time': None,
                'project_income_last_month': '0',
                'project_subs_amount': None,
            },
            'ts': '2025-01-10T10:00:00.000Z',
        },
        # The page lists only the levels on offer; the API also gives the deleted ones.
        'projectLevels': levels()['list'][:2],
        'projectStatus': 'active',
        'isAuthorized': True,
        'mediaURL': 'https://media.sponsr.ru',
        'subscribed': subscribed()['list'][0],
        'user': {
            'id': USER_ID,
            'nickname': 'reader',
            'email': 'reader@example.com',
            'role': 'user',
            'status': 'active',
        },
        'posts': [],
    }


def project_page_html(props=None):
    data = {
        'props': {'pageProps': project_page_props() if props is None else props},
        'page': '/project/[projectUrl]',
        'buildId': 'x',
    }
    return (
        '<!DOCTYPE html><html><head><title>Вымышленный альманах</title></head><body><div id="__next"></div>'
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data, ensure_ascii=False)}</script>'
        '</body></html>'
    )
