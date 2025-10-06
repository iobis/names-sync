import requests
import os
import logging


logger = logging.getLogger("namessync")


class AlreadyExistsException(Exception):
    pass


class VlizSession:

    def __init__(self):
        self.set_token()

    def set_token(self):
        self.token = self.get_token()
        logger.info("Updated token")

    def get_token(self):
        """Get a JWT token from VLIZ."""

        url = os.getenv("VLIZ_JWT_ENDPOINT")
        res = requests.post(url, data={
            "_username": os.getenv("VLIZ_USER"),
            "_password": os.getenv("VLIZ_PASSWORD"),
        })
        print(f"Status: {res.status_code}")
        print(f"Response: {res.text}")
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
            logger.debug(f"Received page {page} with {len(names)} names")
            results = results + names
            page = page + 1

        logger.debug(f"Received {len(results)} names in total")
        return results

    def add_annotated_list(self, item: dict, renew_token: bool = True):
        logger.debug(item)
        url = os.getenv("VLIZ_ENDPOINT") + "/annotated-lists"
        token = self.token["token"]
        res = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json=item)
        logger.debug(res.text)
        if res.status_code == 303:
            raise AlreadyExistsException()
        if res.status_code == 500:
            logger.error("TEMPORARILY SKIPPING ERROR 500")
            return
        if res.status_code == 401 and renew_token:
            logger.info("Received status 401, renewing token")
            self.set_token()
            return self.add_annotated_list(item, renew_token=False)
        res.raise_for_status()
        return res.json()
