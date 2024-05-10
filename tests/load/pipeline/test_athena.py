import pytest
import datetime  # noqa: I251
from typing import Iterator, Any

import dlt, os
from dlt.common import pendulum
from dlt.common.utils import uniq_id
from tests.cases import table_update_and_row, assert_all_data_types_row
from tests.pipeline.utils import assert_load_info, load_table_counts
from tests.pipeline.utils import load_table_counts
from dlt.destinations.exceptions import CantExtractTablePrefix

from tests.load.pipeline.utils import destinations_configs, DestinationTestConfiguration
from tests.load.utils import (
    TEST_FILE_LAYOUTS,
    FILE_LAYOUT_MANY_TABLES_ONE_FOLDER,
    FILE_LAYOUT_CLASSIC,
    FILE_LAYOUT_TABLE_NOT_FIRST,
)

# mark all tests as essential, do not remove
pytestmark = pytest.mark.essential


@pytest.mark.parametrize(
    "destination_config",
    destinations_configs(default_sql_configs=True, subset=["athena"]),
    ids=lambda x: x.name,
)
def test_athena_destinations(destination_config: DestinationTestConfiguration) -> None:
    pipeline = destination_config.setup_pipeline("athena_" + uniq_id(), dev_mode=True)

    @dlt.resource(name="items", write_disposition="append")
    def items():
        yield {
            "id": 1,
            "name": "item",
            "sub_items": [{"id": 101, "name": "sub item 101"}, {"id": 101, "name": "sub item 102"}],
        }

    pipeline.run(items, loader_file_format=destination_config.file_format)

    # see if we have athena tables with items
    table_counts = load_table_counts(
        pipeline, *[t["name"] for t in pipeline.default_schema._schema_tables.values()]
    )
    assert table_counts["items"] == 1
    assert table_counts["items__sub_items"] == 2
    assert table_counts["_dlt_loads"] == 1

    # load again with schema evloution
    @dlt.resource(name="items", write_disposition="append")
    def items2():
        yield {
            "id": 1,
            "name": "item",
            "new_field": "hello",
            "sub_items": [
                {
                    "id": 101,
                    "name": "sub item 101",
                    "other_new_field": "hello 101",
                },
                {
                    "id": 101,
                    "name": "sub item 102",
                    "other_new_field": "hello 102",
                },
            ],
        }

    pipeline.run(items2)
    table_counts = load_table_counts(
        pipeline, *[t["name"] for t in pipeline.default_schema._schema_tables.values()]
    )
    assert table_counts["items"] == 2
    assert table_counts["items__sub_items"] == 4
    assert table_counts["_dlt_loads"] == 2


@pytest.mark.parametrize(
    "destination_config",
    destinations_configs(default_sql_configs=True, subset=["athena"]),
    ids=lambda x: x.name,
)
def test_athena_all_datatypes_and_timestamps(
    destination_config: DestinationTestConfiguration,
) -> None:
    pipeline = destination_config.setup_pipeline("athena_" + uniq_id(), dev_mode=True)

    # TIME is not supported
    column_schemas, data_types = table_update_and_row(exclude_types=["time"])

    # apply the exact columns definitions so we process complex and wei types correctly!
    @dlt.resource(table_name="data_types", write_disposition="append", columns=column_schemas)
    def my_resource() -> Iterator[Any]:
        nonlocal data_types
        yield [data_types] * 10

    @dlt.source(max_table_nesting=0)
    def my_source() -> Any:
        return my_resource

    info = pipeline.run(my_source())
    assert_load_info(info)

    with pipeline.sql_client() as sql_client:
        db_rows = sql_client.execute_sql("SELECT * FROM data_types")
        assert len(db_rows) == 10
        db_row = list(db_rows[0])
        # content must equal
        assert_all_data_types_row(
            db_row[:-2],
            parse_complex_strings=True,
            timestamp_precision=sql_client.capabilities.timestamp_precision,
            schema=column_schemas,
        )

        # now let's query the data with timestamps and dates.
        # https://docs.aws.amazon.com/athena/latest/ug/engine-versions-reference-0003.html#engine-versions-reference-0003-timestamp-changes

        # use string representation TIMESTAMP(2)
        db_rows = sql_client.execute_sql(
            "SELECT * FROM data_types WHERE col4 = TIMESTAMP '2022-05-23 13:26:45.176'"
        )
        assert len(db_rows) == 10
        # no rows - TIMESTAMP(6) not supported
        db_rows = sql_client.execute_sql(
            "SELECT * FROM data_types WHERE col4 = TIMESTAMP '2022-05-23 13:26:45.176145'"
        )
        assert len(db_rows) == 0
        # use pendulum
        # that will pass
        db_rows = sql_client.execute_sql(
            "SELECT * FROM data_types WHERE col4 = %s",
            pendulum.datetime(2022, 5, 23, 13, 26, 45, 176000),
        )
        assert len(db_rows) == 10
        # that will return empty list
        db_rows = sql_client.execute_sql(
            "SELECT * FROM data_types WHERE col4 = %s",
            pendulum.datetime(2022, 5, 23, 13, 26, 45, 176145),
        )
        assert len(db_rows) == 0

        # use datetime
        db_rows = sql_client.execute_sql(
            "SELECT * FROM data_types WHERE col4 = %s",
            datetime.datetime(2022, 5, 23, 13, 26, 45, 176000),
        )
        assert len(db_rows) == 10
        db_rows = sql_client.execute_sql(
            "SELECT * FROM data_types WHERE col4 = %s",
            datetime.datetime(2022, 5, 23, 13, 26, 45, 176145),
        )
        assert len(db_rows) == 0

        # check date
        db_rows = sql_client.execute_sql("SELECT * FROM data_types WHERE col10 = DATE '2023-02-27'")
        assert len(db_rows) == 10
        db_rows = sql_client.execute_sql(
            "SELECT * FROM data_types WHERE col10 = %s", pendulum.date(2023, 2, 27)
        )
        assert len(db_rows) == 10
        db_rows = sql_client.execute_sql(
            "SELECT * FROM data_types WHERE col10 = %s", datetime.date(2023, 2, 27)
        )
        assert len(db_rows) == 10


@pytest.mark.parametrize(
    "destination_config",
    destinations_configs(default_sql_configs=True, subset=["athena"]),
    ids=lambda x: x.name,
)
def test_athena_blocks_time_column(destination_config: DestinationTestConfiguration) -> None:
    pipeline = destination_config.setup_pipeline("athena_" + uniq_id(), dev_mode=True)

    column_schemas, data_types = table_update_and_row()

    # apply the exact columns definitions so we process complex and wei types correctly!
    @dlt.resource(table_name="data_types", write_disposition="append", columns=column_schemas)
    def my_resource() -> Iterator[Any]:
        nonlocal data_types
        yield [data_types] * 10

    @dlt.source(max_table_nesting=0)
    def my_source() -> Any:
        return my_resource

    info = pipeline.run(my_source())

    assert info.has_failed_jobs

    assert (
        "Athena cannot load TIME columns from parquet tables"
        in info.load_packages[0].jobs["failed_jobs"][0].failed_message
    )


@pytest.mark.parametrize(
    "destination_config",
    destinations_configs(default_sql_configs=True, subset=["athena"]),
    ids=lambda x: x.name,
)
@pytest.mark.parametrize("layout", TEST_FILE_LAYOUTS)
def test_athena_file_layouts(destination_config: DestinationTestConfiguration, layout) -> None:
    # test wether strange file layouts still work in all staging configs
    pipeline = destination_config.setup_pipeline("athena_file_layout", full_refresh=True)
    os.environ["DESTINATION__FILESYSTEM__LAYOUT"] = layout

    resources = [
        dlt.resource([1, 2, 3], name="items1"),
        dlt.resource([1, 2, 3, 4, 5, 6, 7], name="items2"),
    ]

    # layouts that should not work should raise exception
    if layout in [
        FILE_LAYOUT_CLASSIC,  # table not in own folder
        FILE_LAYOUT_MANY_TABLES_ONE_FOLDER,  # table not in own folder
        FILE_LAYOUT_TABLE_NOT_FIRST,  # table not the first variable
    ]:
        with pytest.raises(CantExtractTablePrefix):
            pipeline.run(resources)
        return

    info = pipeline.run(resources)
    assert_load_info(info)

    table_counts = load_table_counts(
        pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()]
    )
    assert table_counts == {"items1": 3, "items2": 7}
