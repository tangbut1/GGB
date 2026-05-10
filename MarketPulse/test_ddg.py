from duckduckgo_search import DDGS
with DDGS() as ddgs:
    res = list(ddgs.news("Apple", max_results=2))
    print(res)
