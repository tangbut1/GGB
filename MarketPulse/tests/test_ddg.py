"""Optional DuckDuckGo integration smoke test.

This test is intentionally dependency-aware: local CI and lightweight agent
environments may not install the optional DDG package or allow outbound network.
"""
import pytest


try:
    from duckduckgo_search import DDGS
except ImportError:
    try:
        from ddgs import DDGS
    except ImportError:
        DDGS = None


@pytest.mark.skip(reason="Needs network and triggers fatal abort on some environments")
def test_duckduckgo_optional_news_smoke():
    if DDGS is None:
        print("SKIP: duckduckgo_search/ddgs is not installed")
        return

    try:
        with DDGS() as ddgs:
            res = list(ddgs.news("Apple", max_results=2))
    except Exception as exc:
        print(f"SKIP: DuckDuckGo integration unavailable: {exc}")
        return

    assert isinstance(res, list)


if __name__ == "__main__":
    test_duckduckgo_optional_news_smoke()
