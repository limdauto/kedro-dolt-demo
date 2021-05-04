# Kedro Dolt Demo

## Overview

This is a demo project that uses [Dolt](https://docs.dolthub.com/) with Kedro.

To use this:

1. Initialize Dolt repo with `dolt init`
2. Start a Dolt SQL Server with `dolt sql-server --max-connections=11`
3. Run Kedro pipeline with `kedro run`
4. Observe that the train and test datasets are commited to Dolt
5. Try changing `the example_test_data_ratio` and you will be able to see the diff of these datasets in between run. Pretty cool!
