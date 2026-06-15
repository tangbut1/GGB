import pytest
from src.preprocess.cleaner import DataCleaner

def test_clean_text():
    cleaner = DataCleaner()
    
    # Test HTML tags
    assert cleaner.clean_text("<p>Test text</p>") == "Test text"
    
    # Test special characters but keeping valid ones
    assert cleaner.clean_text("Hello World!") == "Hello World!"
    
    # Test empty input
    assert cleaner.clean_text(None) == ""
    assert cleaner.clean_text("") == ""

def test_clean_news_batch():
    cleaner = DataCleaner()
    news_batch = [
        {"title": "<title>News 1</title>", "content": "<div>Content 1</div>"},
        {"title": "", "content": "Content 2"}
    ]
    
    cleaned = cleaner.clean_news_batch(news_batch)
    
    # Cleaned news should filter items without cleaned titles (or original titles)
    # The first item has a title
    assert len(cleaned) == 1
    assert cleaned[0]["title"] == "News 1"
    assert cleaned[0]["content"] == "Content 1"

def test_extract_keywords():
    cleaner = DataCleaner()
    text = "中国经济正在快速增长"
    keywords = cleaner.extract_keywords(text, top_k=2)
    assert len(keywords) <= 2
