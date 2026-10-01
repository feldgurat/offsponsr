from offsponsr.library.text import plain_text


def test_markup_is_dropped():
    html = '<h2>Заголовок</h2><p>Первый <b>абзац</b>.</p><p>Второй&nbsp;&amp; последний.</p>'

    # A non-breaking space is a space like any other here.
    assert plain_text(html, 200) == 'Заголовок Первый абзац. Второй & последний.'


def test_blocks_do_not_run_together():
    assert plain_text('<p>раз</p><p>два</p><ul><li>три</li><li>четыре</li></ul>пять<br>шесть', 200) == (
        'раз два три четыре пять шесть'
    )


def test_inline_tags_do_not_split_words():
    assert plain_text('<p>не<i>раз</i>рывно</p>', 200) == 'неразрывно'


def test_long_text_is_cut_at_a_word():
    text = plain_text('<p>' + 'слово ' * 100 + '</p>', 28)

    assert text == 'слово слово слово слово…'
    assert len(text) <= 29


def test_a_cut_never_leaves_punctuation_before_the_ellipsis():
    assert plain_text('<p>Первое, второе, третье и четвёртое</p>', 15) == 'Первое, второе…'


def test_one_long_word_is_cut_anyway():
    assert plain_text('<p>' + 'я' * 100 + '</p>', 10) == 'я' * 10 + '…'


def test_players_scripts_and_styles_are_not_text():
    html = '<p>До</p><iframe src="x">запасной текст</iframe><script>var a = 1</script><style>p {}</style><p>После</p>'

    assert plain_text(html, 200) == 'До После'


def test_no_text():
    assert plain_text(None, 100) == ''
    assert plain_text('', 100) == ''
    assert plain_text('<p><img src="a.webp"></p>', 100) == ''
