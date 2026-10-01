from offsponsr.library.models import MediaKind
from offsponsr.sponsr.models import PostFile
from offsponsr.sync.media import MediaRef, media_in_files, media_in_html

from . import site_data

YOUTUBE = '<iframe src="https://www.youtube.com/embed/abcdefghijk?rel=0" allowfullscreen></iframe>'


def test_picture():
    [ref] = media_in_html(f'<p>Текст</p><p>{site_data.IMAGE}</p>')

    assert ref.kind is MediaKind.IMAGE
    assert ref.source_url == (
        'https://media.sponsr.ru/project/4242/post/9006/image/31/imagesprojects42ab12cd.webp?1a2b3c'
    )
    # The cache stamp after `?` is not part of what the picture is.
    assert ref.source_id == 'media.sponsr.ru/project/4242/post/9006/image/31/imagesprojects42ab12cd.webp'


def test_lazy_picture_without_src():
    [ref] = media_in_html('<img data-src="https://media.sponsr.ru/a/b.webp?1" alt>')

    assert ref.source_url == 'https://media.sponsr.ru/a/b.webp?1'


def test_kinescope_video_goes_by_its_uuid():
    [ref] = media_in_html(f'<div>{site_data.VIDEO}</div>')

    assert ref == MediaRef(MediaKind.VIDEO, site_data.VIDEO_ID, site_data.KINESCOPE_EMBED)


def test_kinescope_video_without_uuid_goes_by_its_embed():
    [ref] = media_in_html('<iframe src="https://kinescope.io/aBcDeF123"></iframe>')

    assert ref == MediaRef(MediaKind.VIDEO, 'aBcDeF123', 'https://kinescope.io/aBcDeF123')


def test_foreign_player_is_an_embed():
    [ref] = media_in_html(YOUTUBE)

    assert ref.kind is MediaKind.EMBED
    assert ref.source_url == 'https://www.youtube.com/embed/abcdefghijk?rel=0'
    assert ref.source_id == 'www.youtube.com/embed/abcdefghijk'


def test_everything_in_order_and_once():
    html = f'<p>{site_data.IMAGE}</p>{site_data.VIDEO}{YOUTUBE}<p>{site_data.IMAGE}</p><a href="https://example.com">ссылка</a>'

    assert [ref.kind for ref in media_in_html(html)] == [MediaKind.IMAGE, MediaKind.VIDEO, MediaKind.EMBED]


def test_text_without_media():
    assert media_in_html('<p>Просто текст.</p>') == []
    assert media_in_html('') == []
    assert media_in_html(None) == []


def test_files():
    audio = PostFile(
        id=6001,
        category='podcast',
        mime='audio/mpeg',
        name='a.mp3',
        title='Выпуск',
        path='/u/a.mp3',
        size=10,
        duration=5,
    )
    book = PostFile(id=6002, category='attach', mime='application/pdf', name='book.pdf', path='/u/book.pdf', size=20)
    untitled_audio = PostFile(id=6003, category=None, mime='audio/ogg', name='b.ogg', path='/u/b.ogg')

    assert media_in_files([audio, book, untitled_audio, audio]) == [
        MediaRef(MediaKind.AUDIO, '6001', '/u/a.mp3', title='Выпуск', size=10, duration=5),
        MediaRef(MediaKind.ATTACH, '6002', '/u/book.pdf', title='book.pdf', size=20),
        MediaRef(MediaKind.AUDIO, '6003', '/u/b.ogg', title='b.ogg'),
    ]
