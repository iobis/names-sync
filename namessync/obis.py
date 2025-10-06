import psycopg2
import psycopg2.extras
import os
import boto3
import tempfile
import csv
from diskcache import Cache
import logging
import duckdb


logger = logging.getLogger("namessync")
cache = Cache(directory=os.path.expanduser("~/.namessync"))


names_query = """
    with n as (
            select
            concat(datasets.id::text, ';', datasets.url) as url,
            flat->>'scientificName' as scientificName,
            flat->>'scientificNameAuthorship' as scientificNameAuthorship,
            flat->>'scientificNameID' as scientificNameID,
            flat->>'genus' as genus,
            flat->>'family' as family,
            flat->>'order' as order,
            flat->>'class' as class,
            flat->>'phylum' as phylum,
        count(*) as records
        from occurrence
        left join datasets on datasets.id = occurrence.dataset_id
        where aphia is null and flat->>'scientificName' is not null
        group by
            concat(datasets.id::text, ';', datasets.url),
            flat->>'scientificName',
            flat->>'scientificNameAuthorship',
            flat->>'scientificNameID',
            flat->>'genus',
            flat->>'family',
            flat->>'order',
            flat->>'class',
            flat->>'phylum'
    )
    select
        scientificName,
        scientificNameID,
        scientificNameAuthorship,
        genus,
        family,
        "order",
        class,
        phylum,
        sum(records) as records,
        string_agg(url, '|' ORDER BY records desc) as datasets
    from n
    group by
        scientificName,
        scientificNameID,
        scientificNameAuthorship,
        genus,
        family,
        "order",
        class,
        phylum
    order by sum(records) desc
"""


def fetch_nonmatching_parquet():
    """Fetch non matching names from the OBIS parquet dataset."""

    conn = duckdb.connect()
    df = conn.execute("""
        select
            source.scientificName as scientificName,
            source.scientificNameAuthorship as scientificNameAuthorship,
            source.scientificNameID as scientificNameID,
            source.genus as genus,
            source.family as family,
            source.order as order,
            source.class as class,
            source.phylum as phylum,
            count(*) as records,
            first(dataset_id) as dataset,
            first(node_ids) as node
        from read_parquet('/Volumes/acasis/occurrence/*.parquet', union_by_name = true)
        where interpreted.aphiaid is null and source.scientificNameID not ilike '%marinespecies%'
        group by
            source.scientificName,
            source.scientificNameAuthorship,
            source.scientificNameID,
            source.genus,
            source.family,
            source.order,
            source.class,
            source.phylum
    """).fetchdf()
    return df.to_dict("records")


def fetch_nonmatching():
    """Fetch non matching names from the OBIS database. Cached locally for one day."""

    nonmatching = cache.get("non_matching")
    if nonmatching is not None:
        logger.info("Fetching non matching names from local cache")
    else:
        logger.info("Fetching non matching names from database")
        conn = psycopg2.connect(
            "host='%s' dbname='%s' user='%s' password='%s' options='-c statement_timeout=7200s'" % (os.environ["DB_HOST"], os.environ["DB_DB"], os.environ["DB_USER"], os.environ["DB_PASSWORD"]),
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
            application_name="namessync"
        )
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(names_query)
        rows = cur.fetchall()
        nonmatching = [dict(row) for row in rows]
        cur.close()
        conn.close()
        cache.set("non_matching", nonmatching, expire=86400)
    return nonmatching


def export_nonmatching_s3():
    """Export non matching names from the OBIS database to S3 (legacy)."""

    conn = psycopg2.connect("host='%s' dbname='%s' user='%s' password='%s'" % (os.environ["DB_HOST"], os.environ["DB_DB"], os.environ["DB_USER"], os.environ["DB_PASSWORD"]))
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    output_query = "COPY ({0}) TO STDOUT WITH CSV HEADER".format(names_query)

    with tempfile.NamedTemporaryFile(suffix=".txt") as output_file:
        cur.copy_expert(output_query, output_file)
        cur.close()
        conn.close()

        session = boto3.session.Session()
        client = session.client(
            "s3",
            region_name=os.getenv("S3_REGION"),
            endpoint_url=os.getenv("S3_ENDPOINT"),
            aws_access_key_id=os.getenv("S3_ACCESS_ID"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY")
        )

        s3_path = "shared/non_matching_names.csv"
        client.upload_file(output_file.name, "obis-datasets", s3_path, ExtraArgs={"ACL": "public-read"})


def read_nonmatching_s3():
    """Read non matching names from S3 (legacy)."""

    session = boto3.session.Session()
    client = session.client(
        "s3",
        region_name=os.getenv("S3_REGION"),
        endpoint_url=os.getenv("S3_ENDPOINT"),
        aws_access_key_id=os.getenv("S3_ACCESS_ID"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY")
    )
    with tempfile.NamedTemporaryFile(suffix=".csv") as csv_file:
        client.download_file("obis-datasets", "shared/non_matching_names.csv", csv_file.name)
        with open(csv_file.name) as f:
            rows = list(csv.reader(f))
            keys = rows[0]
            rows = rows[1:]
            return [dict(zip(keys, row)) for row in rows]
