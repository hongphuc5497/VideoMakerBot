from pathlib import Path


def test_backgrounds_template_escapes_catalog_values_before_inner_html():
    template = Path("GUI/backgrounds.html").read_text(encoding="utf-8")

    assert "function h(str)" in template
    assert "title=\"${h(key)}\"" in template
    assert "${h(key)}" in template
    assert "${h(value[2])}" in template
