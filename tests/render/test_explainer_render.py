"""Browser-render-grain assertions for the Facebook twin's explainer page.

Catches the same `&xxx;`-in-CSS-content bug class fixed in Job 021 for
telegram, sibling-wide. See twins_local.testing.render for the shared
assertions.
"""

import pytest

from twins_local.testing import (
    assert_explainer_renders_correct_bullet,
    assert_no_entity_artifacts_in_visible_text,
)

pytestmark = pytest.mark.render


def test_explainer_bullet_renders_as_arrow(page, live_server_url):
    assert_explainer_renders_correct_bullet(page, live_server_url)


def test_explainer_visible_text_has_no_entity_artifacts(page, live_server_url):
    assert_no_entity_artifacts_in_visible_text(page, live_server_url)
