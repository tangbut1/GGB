from src.collect.custom_search import CustomSearchCollector
c = CustomSearchCollector()
res = c.run_custom_search("美加墨世界杯")
print(f"Results: {len(res)}")
