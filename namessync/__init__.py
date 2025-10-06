from namessync.obis import fetch_nonmatching_parquet
from namessync.vliz import AlreadyExistsException, VlizSession
import logging
from termcolor import colored
import pyworms
import urllib.parse
from datetime import datetime


logger = logging.getLogger("namessync")


def check_name_has_exact_match(scientificname: str, scientificnameauthorship: str):
    matches = pyworms.aphiaRecordsByMatchNames(urllib.parse.quote(scientificname), marine_only=False)
    if matches is not None:
        assert len(matches) == 1
        matches = matches[0]
        for match in matches:
            if match["match_type"] == "exact":
                if scientificnameauthorship is None or scientificnameauthorship == match["authority"]:
                    return True
    return False


def sync_to_vliz(max_items=None, dry_run=False, overwrite=True):
    session = VlizSession()
    non_matching = fetch_nonmatching_parquet()

    # create annotated list map based on name and authorship

    annotated_map = {}
    if not overwrite:
        annotated_list = session.fetch_annotated_list()
        for item in annotated_list:
            key = (item["scientificName"].strip() if item["scientificName"] is not None else "") + "|" + (item["scientificNameAuthorship"].strip() if item["scientificNameAuthorship"] is not None else "")
            if key in annotated_map:
                annotated_map[key].append(item)
            else:
                annotated_map[key] = [item]

    # check non matching names against annotated list

    for item in non_matching:
        key = (item["scientificName"].strip() if item["scientificName"] is not None else "") + "|" + (item["scientificNameAuthorship"].strip() if item["scientificNameAuthorship"] is not None else "")
        if (not overwrite) and key in annotated_map:
            logger.debug(f"Key {key} already in annotated list")
        else:
            try:
                has_exact_match = check_name_has_exact_match(item["scientificName"], item["scientificNameAuthorship"])
            except Exception:
                logger.error(colored(f"Error while querying WoRMS for {key}", "red"))
                continue
            if has_exact_match:
                logger.info(colored(f">>> Key {key} has exact match in WoRMS, skipping", "grey"))
            else:
                logger.info(colored(f">>> Trying to add {key} to the annotated list", "yellow"))
                data = {
                    "scientificName": item["scientificName"],
                    "scientificNameAuthorship": item["scientificNameAuthorship"],
                    "phylum": item["phylum"],
                    "class": item["class"],
                    "order": item["order"],
                    "family": item["family"],
                    "genus": item["genus"],
                    "recordCount": int(item["records"]),
                    "datasetUuid": item["dataset"],
                    "datasetUrl": "https://obis.org/dataset/" + item["dataset"],
                    "node": item["node"][0]
                }
                if not dry_run:
                    try:
                        session.add_annotated_list(data)
                        logger.info(colored(f"    Added {key} to the annotated list", "green"))

                        if max_items is not None:
                            max_items = max_items - 1
                            if max_items == 0:
                                logger.info(colored("Reached max items, stopping", "blue"))
                                break

                    except AlreadyExistsException:
                        logger.info(colored(f"    Key {key} already exists according to API", "red"))
