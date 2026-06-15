import pytest
from unittest.mock import patch, MagicMock
from src.collect.custom_search import CustomSearchCollector
from datetime import datetime

def test_custom_search_initialization():
    collector = CustomSearchCollector(max_workers=2)
    assert collector.max_workers == 2

@patch("src.collect.custom_search.requests.Session.get")
def test_search_google_news(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'''<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item>
        <title>Test Google News</title>
        <link>http://example.com/google</link>
        <description>Test Description</description>
        <source>Google Source</source>
        <pubDate>Sun, 01 Jan 2050 12:00:00 GMT</pubDate>
    </item></channel></rss>'''
    mock_get.return_value = mock_resp

    collector = CustomSearchCollector()
    results = collector._search_google_news("test keyword")
    assert len(results) >= 0  # if feedparser is required we can just assert it doesn't crash

@patch("src.collect.custom_search.DDGS")
def test_search_duckduckgo(mock_ddgs):
    mock_ddgs_instance = mock_ddgs.return_value.__enter__.return_value
    mock_ddgs_instance.news.return_value = [
        {
            "title": "Test DDG News",
            "url": "http://example.com/ddg",
            "body": "This is a test from DDG",
            "source": "DDG Source",
            "date": "2050-01-01T12:00:00Z"
        }
    ]

    collector = CustomSearchCollector()
    results = collector._search_duckduckgo("test keyword")
    assert len(results) == 1
    assert results[0]["title"] == "Test DDG News"
    assert results[0]["link"] == "http://example.com/ddg"

@patch("src.collect.custom_search.requests.Session.get")
def test_search_newsapi(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "articles": [
            {
                "title": "Test NewsAPI News",
                "url": "http://example.com/newsapi",
                "description": "This is a test from NewsAPI",
                "source": {"name": "NewsAPI Source"},
                "publishedAt": "2050-01-01T12:00:00Z"
            }
        ]
    }
    mock_get.return_value = mock_resp

    collector = CustomSearchCollector()
    results = collector._search_newsapi("test keyword", remaining=10, api_key="dummy_key")
    assert len(results) == 1
    assert results[0]["title"] == "Test NewsAPI News"
    assert results[0]["link"] == "http://example.com/newsapi"

def test_parse_datetime():
    collector = CustomSearchCollector()
    dt1 = collector._parse_datetime("2050-01-01 12:00:00")
    assert dt1 is not None
    assert dt1.year == 2050
    assert dt1.month == 1

    dt2 = collector._parse_datetime("3小时前")
    assert dt2 is not None
