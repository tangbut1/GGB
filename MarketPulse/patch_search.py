import re

with open("src/collect/custom_search.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add _search_bing_rss
bing_rss_code = """
    def _search_bing_rss(self, keyword: str, max_results: int = 50) -> List[Dict[str, Any]]:
        \"\"\"Bing News RSS \"\"\"
        if self._bing_banned:
            return []
        logger.info(" Bing News RSS : {}", keyword)
        import urllib.parse
        import xml.etree.ElementTree as ET
        from email.utils import parsedate_to_datetime
        import pytz
        
        url = f"https://www.bing.com/news/search?q={urllib.parse.quote(keyword)}&format=rss"
        try:
            resp = self.session.get(url, timeout=self.search_timeout)
            if resp.status_code != 200:
                logger.warning("Bing RSS  {}", resp.status_code)
                if resp.status_code in (403, 429, 503):
                    self._bing_banned = True
                return []
                
            root = ET.fromstring(resp.text)
            items = []
            for item in root.findall(".//item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                description = item.findtext("description", "")
                pub_date = item.findtext("pubDate", "")
                
                dt = datetime.now()
                if pub_date:
                    try:
                        dt = parsedate_to_datetime(pub_date)
                        if dt.tzinfo is not None:
                            dt = dt.astimezone(pytz.utc).replace(tzinfo=None)
                    except Exception:
                        pass
                
                if dt < self.cutoff_date:
                    continue
                        
                source_node = item.find("{*}Source")
                source = source_node.text if source_node is not None else "Bing RSS"
                        
                items.append({
                    "title": title,
                    "url": link,
                    "link": link,
                    "summary": description,
                    "content": description,
                    "source": source,
                    "publish_time": dt.strftime("%Y-%m-%d %H:%M"),
                    "_publish_dt": dt
                })
                if len(items) >= max_results:
                    break
            return items
        except Exception as e:
            logger.debug("Bing RSS : {}", e)
            return []

    # ------------------------------------------------------------------
    def _search_generic(self, keyword: str, remaining: int) -> List[Dict[str, Any]]:"""

content = content.replace("    # ------------------------------------------------------------------\n    def _search_generic(self, keyword: str, remaining: int) -> List[Dict[str, Any]]:", bing_rss_code)

# Add it to search_news pipeline
layer3_code = """
        #   3 Bing/ 
        if len(aggregated) < target_results:
            logger.info(" [Layer 3/3] Bing ...")
            remaining = target_results - len(aggregated)
            bing_results = self._search_generic(keyword, remaining=remaining)
            aggregated.extend(bing_results)
            logger.info("   Bing  → {} ", len(bing_results))"""

layer3_new_code = """
        #   3 Bing RSS  
        if len(aggregated) < target_results:
            logger.info(" [Layer 3/4] Bing RSS ...")
            remaining = target_results - len(aggregated)
            bing_rss_results = self._search_bing_rss(keyword, max_results=remaining)
            aggregated.extend(bing_rss_results)
            logger.info("   Bing RSS  → {} ", len(bing_rss_results))

        #   4 Bing  
        if len(aggregated) < target_results:
            logger.info(" [Layer 4/5] Bing ...")
            remaining = target_results - len(aggregated)
            bing_results = self._search_generic(keyword, remaining=remaining)
            aggregated.extend(bing_results)
            logger.info("   Bing  → {} ", len(bing_results))"""

content = content.replace(layer3_code, layer3_new_code)

# Add early break in auxiliary search
aux_loop_code = """        for term in auxiliary_terms:
            if len(aggregated) >= target_results:
                break"""

aux_loop_new_code = """        for term in auxiliary_terms:
            if len(aggregated) >= target_results:
                break
            if self._google_banned and self._ddg_banned and self._bing_banned:
                logger.warning(" (Google/DDG/Bing)")
                break"""

content = content.replace(aux_loop_code, aux_loop_new_code)

with open("src/collect/custom_search.py", "w", encoding="utf-8") as f:
    f.write(content)

