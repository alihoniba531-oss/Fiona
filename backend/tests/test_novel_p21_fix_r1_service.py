"""First-review fixes: PATCH error precedence and stale export placement."""

import pytest

from test_novel_p21_service import (
    BOOK, HEADERS, USER, book, persisted, run, seed_book, seed_chapter, workshop,
)


@pytest.mark.parametrize('appearance', ['', '短发', '外 '*19])
def test_missing_character_returns_404_before_short_appearance_validation(book, appearance):
    before = run(persisted())
    response = book.patch(f'/novels/{BOOK}/characters/unknownid',
                          json={'appearance': appearance}, headers=HEADERS)
    assert response.status_code == 404
    assert response.json()['detail'] == '人物不存在'
    assert run(persisted()) == before


def test_existing_character_still_rejects_short_appearance_without_writing(book):
    before = run(persisted())
    response = book.patch(f'/novels/{BOOK}/characters/C1',
                          json={'appearance': '短发'}, headers=HEADERS)
    assert response.status_code == 422
    assert response.json()['detail'] == '外形至少写 20 个字'
    assert run(persisted()) == before


@pytest.mark.parametrize('body,expected_chapter', [
    ('# 第1章 档案\n\n正文。', '# 第1章 档案\n【待复核】前面章节改过稿，本章尚未按新内容复核。\n\n正文。'),
    ('# 第1章 只有标题', '# 第1章 只有标题\n【待复核】前面章节改过稿，本章尚未按新内容复核。'),
    ('作者手改的第一行。\n第二行。', '【待复核】前面章节改过稿，本章尚未按新内容复核。\n作者手改的第一行。\n第二行。'),
    ('单行正文。', '【待复核】前面章节改过稿，本章尚未按新内容复核。\n单行正文。'),
    ('#没有标题空格\n正文。', '【待复核】前面章节改过稿，本章尚未按新内容复核。\n#没有标题空格\n正文。'),
    ('\n# 第1章 后置标题', '【待复核】前面章节改过稿，本章尚未按新内容复核。\n\n# 第1章 后置标题'),
    ('', '【待复核】前面章节改过稿，本章尚未按新内容复核。\n'),
])
def test_stale_export_marks_after_heading_or_before_unheaded_body(workshop, body, expected_chapter):
    from novel import service

    run(seed_book())
    run(seed_chapter(1, status='stale', body=body))
    before = run(persisted())
    exported = run(service.export(USER, BOOK))
    assert exported == '# 旧档案 Novel\n本书有 1 章待复核：第 1 章。\n\n'+expected_chapter
    assert run(persisted()) == before
