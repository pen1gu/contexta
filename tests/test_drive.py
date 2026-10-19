from contexta.drive import rewrite_thumbnail_url


def test_rewrite_thumbnail_url_s220을_s800으로_바꾼다():
    url = "https://lh3.googleusercontent.com/d/abc=s220"
    assert rewrite_thumbnail_url(url) == "https://lh3.googleusercontent.com/d/abc=s800"


def test_rewrite_thumbnail_url_다른_크기_접미사도_s800으로_바꾼다():
    url = "https://lh3.googleusercontent.com/d/abc=s480"
    assert rewrite_thumbnail_url(url) == "https://lh3.googleusercontent.com/d/abc=s800"


def test_rewrite_thumbnail_url_크기_접미사가_없으면_s800을_붙인다():
    url = "https://lh3.googleusercontent.com/d/abc"
    assert rewrite_thumbnail_url(url) == "https://lh3.googleusercontent.com/d/abc=s800"


def test_rewrite_thumbnail_url_이미_s800이면_그대로_둔다():
    url = "https://lh3.googleusercontent.com/d/abc=s800"
    assert rewrite_thumbnail_url(url) == "https://lh3.googleusercontent.com/d/abc=s800"
