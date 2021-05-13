---
title: "Change Data Capture With Kedro and Dolt"
date: "2021-05-13"
author: "Max Hoffman"
authorHref: "https://www.dolthub.com/team#max"
---

# Introduction

We are pleased to introduce a Kedro-Dolt plugin, a collaboration between
Quantum Black and DoltHub designed to expand the data-versioning
abilities of data scientists and engineers.

# What is Kedro?

Kedro is a workflow system that offers both quick prototyping
and production scaling in a single tool. Code is written in Python,
packaged into discrete "nodes," and composed between inputs and
outputs with Python pipelines.

Data management is one instance where Kedro separates from other
workflow managers. A "data catalog" encapsulates data source
configuration, removing IO as a concern for data scientists.

As a quick example, consider the `DataSet` below defined in our
`catalog.yml`:

```python
iris_data:
 type: pandas.CSVDataSet
 filepath: "data/01_raw/iris.csv"
```

Kedro connects `iris_data` as an input to the `split_data` node
with the following declaration:

```python
node(func=split_data, inputs=["iris_data"], ...)
```

At runtime, the `data` argument of `split_data` will now be loaded according
to the dataset configuration for our node input:

```python
def split_data(data: pd.DataFrame, ratio: float) -> Dict[str, Any]:
    ...
```

Cleanly delineating the concerns of data infrastructure and data science
is important for delivering data pipelines. Nodes, data sources, and
pipelines can be customized, composed and executed on a variety of
backends with these simple building blocks.

# What is Dolt?

Dolt is an SQL database with Git-like versioning. Engineers use Dolt in
machine learning workflows to version tabular data in a
production-hardened database. Instead of producing new CSV's for every
workflow run, save deltas between runs. Instead of copying files between
folder namespaces, branch from and merged to a source database. Instead
of hunting for quality bugs with scripts and expectation suites, run
causational analysis on row-level diffs between two data versions.

# Using the Kedro-Dolt Plugin

## Setup

You can clone our project to follow along:
```bash
$ git clone git@github.com:dolthub/kedro-dolt-demo.git
```

This workflow was originally built using the [Iris starter
project](https://kedro.readthedocs.io/en/stable/02_get_started/05_example_project.html).
We will walk through our modifications shortly.

To create our database, first
[install `dolt`](https://docs.dolthub.com/getting-started/installation):

```bash
$ sudo bash -c 'curl -L https://github.com/dolthub/dolt/releases/latest/download/install.sh | sudo bash'
```

We can create our database with an initialization call:

```bash
$ dolt init
Successfully initialized dolt data repository
```

and expose an sql-server at `root@localhost:3306/kedro_dolt_demo`
by running the following line in a separate window:

```bash
$ dolt sql-server --max-connections=10 -l trace
Starting server with Config HP="localhost:3306"|U="root"|P=""|T="28800000"|R="false"|L="trace"
```

The [catalog
configuration](https://github.com/limdauto/kedro-dolt-demo/blob/main/conf/base/catalog.yml)
in `conf/catalog.yml` shows how we pass this sql connection as a
credential to our data sources:

```python
example_test_x:
  type: pandas.SQLTableDataSet
  table_name: example_test_x
  credentials:
    con: mysql+pymysql://root@localhost:3306/kedro_dolt_demo
  save_args:
    if_exists: replace
```

## Plugin

Kedro uses [`pluggy`-style Hooks](https://pluggy.readthedocs.io/en/latest/)
to register callbacks during stages of a
workflow's lifecycle. The Kedro-Dolt plugin defines
`before_pipeline_run` and `after_pipeline_run` methods to loop into
workflow executions. More information on Kedro Hooks and the available
lifecyle stages exposed can be found in the [Kedro
docs](https://kedro.readthedocs.io/en/latest/07_extend_kedro/02_hooks.html).

Before the pipeline starts we can checkout a database branch if
`--params branch:<value>` is found:

```python
@hook_impl
def before_pipeline_run(self, run_params: Dict[str, Any]):
    if (
        "branch" in run_params["extra_params"] and
        run_params["extra_params"]["branch"] is not None
    ):
       self._branch = run_params["extra_params"]["branch"]
       self._original_branch = self._active_branch
       self._checkout_branch(self._branch)
```

The pipeline cleanup hook commits changes and restores
the original database branch.

```python
@hook_impl
def after_pipeline_run(self, run_params: Dict[str, Any]):
   commit_message = self._commit_message(run_params=run_params)
   self._commit(commit_message)
   if self._original_branch is not None:
       self._checkout_branch(self._original_branch)
```

A Dolt commit persists data analogous to a Git commit.
Commits hold a database root value, message, timestamp and parent
commit reference.

By default, the Kedro-Dolt plugin will record an
execution's run id in the commit:

```python
def _commit_message(self, run_params: Dict[str, Any]):
    return f"Update from kedro run: {run_params['run_id']}"
```

Hooks are declared by populating
[`settings.py`](https://github.com/dolthub/kedro-dolt-demo/blob/main/src/kedro_dolt_demo/settings.py)
in our database configuration:

```python
from kedro_dolt_demo.hooks import ProjectHooks

DOLT_DATABASE="kedro_dolt_demo"
HOOKS = (ProjectHooks(database=DOLT_DATABASE),)
```

## Diffs

Now that we've initialized our repo and connected our hook,
we can execute our workflow:

```bash
$ kedro run --params example_test_data_ratio:0.1
$ kedro run --params example_test_data_ratio:0.2
```

The data from these runs populate our dolt database:

```bash
$ dolt log
commit m3112s3uuird3rtjt28cdeitp5prp6td
Author: Lim Hoang <limdauto@gmail.com>
Date:   Fri Apr 23 23:46:04 +0100 2021

        Update data from Kedro run: 2021-04-23T22.45.45.157Z

commit jc77hh54t97na1hs8i6k8b5pfrh7tiej
Author: Lim Hoang <limdauto@gmail.com>
Date:   Fri Apr 23 23:45:01 +0100 2021

        Update data from Kedro run 2021-04-23T22.44.41.926Z
```

We ran our pipeline with two different hyperparameters so that we can
compare the outputs with `dolt diff`. Diffs traverse the database
to efficiently surface modifications between tables:

```bash
$ dolt diff HEAD HEAD^ example_test_x --limit 5
diff --dolt a/example_test_x b/example_test_x
--- a/example_test_x @ phat5gjncsmcr6ke7hkm71kqi3p3fh2r
+++ b/example_test_x @ ge6u7548i2g1nj3o8ge9ilanmj2hbta0
+-----+--------------+-------------+--------------+-------------+
|     | sepal_length | sepal_width | petal_length | petal_width |
+-----+--------------+-------------+--------------+-------------+
|  +  | 7.2          | 3.6         | 6.1          | 2.5         |
|  +  | 4.9          | 3           | 1.4          | 0.2         |
|  +  | 6.7          | 3.1         | 5.6          | 2.4         |
|  +  | 6.7          | 3           | 5            | 1.7         |
|  +  | 4.4          | 2.9         | 1.4          | 0.2         |
+-----+--------------+-------------+--------------+-------------+
```

Dolt's [system
tables](https://docs.dolthub.com/interfaces/sql/dolt-system-tables#dolt_diff_usdtablename)
retrieve more programmatically useful diff outputs:

```bash
$ dolt sql -q "
    select to_sepal_width, from_sepal_width, diff_type, to_commit, from_commit
    from dolt_diff_example_test_x
    where from_commit = hashof('HEAD^') and
          to_commit = hashof('HEAD')
    limit 5"
+----------------+------------------+-----------+----------------------------------+----------------------------------+
| to_sepal_width | from_sepal_width | diff_type | to_commit                        | from_commit                      |
+----------------+------------------+-----------+----------------------------------+----------------------------------+
| 3.3            | NULL             | added     | bku4billo5s1ldr3qkmej0gffi0urv1q | um0nq2pue9d8vgfsc878arosuala7c6e |
| NULL           | 2.4              | removed   | bku4billo5s1ldr3qkmej0gffi0urv1q | um0nq2pue9d8vgfsc878arosuala7c6e |
| NULL           | 3                | removed   | bku4billo5s1ldr3qkmej0gffi0urv1q | um0nq2pue9d8vgfsc878arosuala7c6e |
| 3.5            | NULL             | added     | bku4billo5s1ldr3qkmej0gffi0urv1q | um0nq2pue9d8vgfsc878arosuala7c6e |
| 3              | NULL             | added     | bku4billo5s1ldr3qkmej0gffi0urv1q | um0nq2pue9d8vgfsc878arosuala7c6e |
+----------------+------------------+-----------+----------------------------------+----------------------------------+
```

## Branching

Here we run our workflow in a fresh branch, isolating our workflow from others:

```bash
$ kedro run --params branch:new,example_test_data_ratio:0.3
```

Branch diffs work the same way as commit diffs:

```bash
$ dolt diff master new example_test_x --limit 5
diff --dolt a/example_test_x b/example_test_x
--- a/example_test_x @ phat5gjncsmcr6ke7hkm71kqi3p3fh2r
+++ b/example_test_x @ icsc2i6mdempgq0dvbocuu90mgfb0jf8
+-----+--------------+-------------+--------------+-------------+
|     | sepal_length | sepal_width | petal_length | petal_width |
+-----+--------------+-------------+--------------+-------------+
|  +  | 6.8          | 3.2         | 5.9          | 2.3         |
|  -  | 6.4          | 2.7         | 5.3          | 1.9         |
|  -  | 4.8          | 3.4         | 1.6          | 0.2         |
|  -  | 5.1          | 3.8         | 1.5          | 0.3         |
|  +  | 4.9          | 2.5         | 4.5          | 1.7         |
+-----+--------------+-------------+--------------+-------------+

```

## Select Query

The Iris demo does not read from our database, but you could use select
statements to link dependencies using specific versions of data:

```python
iris_predictions:
  type: pandas.SQLQueryDataSet
  sql:"SELECT  * FROM example_test_y AS OF HASHOF('new')"
  credentials:
    con: mysql+pymysql://root@localhost:3306/kedro_dolt_demo
  save_args:
    if_exists: replace
```

`HASHOF('new')` resolves the latest commit of our `new` branch, letting
us indirectly track its newest committed data.

We can sample this select query on the command-line:

```bash
$ dolt sql -q "select * from example_test_y as of hashof('new') limit 5"
+--------+------------+-----------+
| setosa | versicolor | virginica |
+--------+------------+-----------+
| 0      | 0          | 1         |
| 0      | 0          | 1         |
| 0      | 0          | 1         |
| 0      | 0          | 1         |
| 0      | 0          | 1         |
+--------+------------+-----------+
```

## Run Id Search

Translating between workflow executions, versions code and versions of
data can be a useful discovery tool. We use the `dolt_commits` system
table below to filter for a commit containing a run id of interest --
`2021-05-03T20.51.27.129Z`:

```bash
$ dolt sql -q "
    select commit_hash, message
    from dolt_commits
    where message like '%2021-05-03T20.51.27.129Z'"
+----------------------------------+------------------------------------------------+
| commit_hash                      | message                                        |
+----------------------------------+------------------------------------------------+
| 2vffmvs72phcuccpnmaud6fgrs8t7p4k | Update from kedro run 2021-05-03T20.51.27.129Z |
+----------------------------------+------------------------------------------------+
```

If we wished to index commits by hyperparameter value, we could customize the
`KedroDolt._commit_message()` method:

```python
def _commit_message(self, run_params: Dict[str, Any]):
    import json
    return f"Update from kedro run: {json.dumps(run_params['extra_params'])}"
```

Resulting in the following commit:

```bash
$  dolt sql -q "select message from dolt_log limit 1"
+------------------------------------------+
| message                                  |
+------------------------------------------+
| Update from kedro run: {"branch": "new"} |
+------------------------------------------+
```

## Conclusion

The Kedro-Dolt plugin currently supports a limited set of features.
We encourage you to [reach out on our
Discord](https://discord.com/invite/RFwfYpu) if you are interested in a
more advanced plugin, want to see how to run Kedro against a production
Dolt instance running like RDS, or just want to learn more about Dolt.
