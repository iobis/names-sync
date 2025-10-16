from namessync import sync_to_vliz
from dotenv import load_dotenv
import requests_cache
import logging


logging.basicConfig(level="INFO")
# requests_cache.install_cache("vliz_cache")
load_dotenv()


sync_to_vliz(dry_run=False, max_items=None, overwrite=True)
