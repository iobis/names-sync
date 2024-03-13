import requests
import os
import logging


logger = logging.getLogger("namessync")


class AlreadyExistsException(Exception):
    pass


class VlizSession:

    def __init__(self):
        self.token = self.get_token()

    def get_token(self):
        """Get a JWT token from VLIZ."""

        url = os.getenv("VLIZ_JWT_ENDPOINT")
        res = requests.post(url, data={
            "_username": os.getenv("VLIZ_USER"),
            "_password": os.getenv("VLIZ_PASSWORD"),
        })
        res.raise_for_status()
        return res.json()

    def fetch_annotated_list(self):
        """Fetch the annotated list from the VLIZ API."""

        logger.info("Fetching annotated list from VLIZ")

        page = 1
        results = []

        while True:
            url = os.getenv("VLIZ_ENDPOINT") + f"/annotated-lists?itemsPerPage=1000&page={page}"
            token = self.token["token"]
            res = requests.get(url, headers={"Authorization": f"Bearer {token}"})
            res.raise_for_status()
            names = res.json()
            if len(names) == 0:
                break
            results = results + names
            page = page + 1

        return results

    def add_annotated_list(self, item: dict):
        url = os.getenv("VLIZ_ENDPOINT") + "/annotated-lists"
        token = self.token["token"]
        res = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json=item)
        res.raise_for_status()
        if res.status_code == 303:
            raise AlreadyExistsException()
        return res.json()
