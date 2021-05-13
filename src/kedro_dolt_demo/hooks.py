# Copyright 2021 QuantumBlack Visual Analytics Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
# NONINFRINGEMENT. IN NO EVENT WILL THE LICENSOR OR OTHER CONTRIBUTORS
# BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF, OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# The QuantumBlack Visual Analytics Limited ("QuantumBlack") name and logo
# (either separately or in combination, "QuantumBlack Trademarks") are
# trademarks of QuantumBlack. The License does not grant you any right or
# license to the QuantumBlack Trademarks. You may not use the QuantumBlack
# Trademarks or any confusingly similar mark as a trademark for your product,
# or use the QuantumBlack Trademarks in any other manner that might cause
# confusion in the marketplace, including but not limited to in advertising,
# on websites, or on software.
#
# See the License for the specific language governing permissions and
# limitations under the License.

"""Project hooks."""
from functools import wraps
import logging
from typing import Any, Dict, Iterable, Optional

import pymysql.cursors
from kedro.config import ConfigLoader
from kedro.framework.hooks import hook_impl
from kedro.io import DataCatalog
from kedro.versioning import Journal

logger = logging.getLogger("KedroDolt")

def log_pymysql_error(f):
    @wraps(f)
    def inner(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except pymysql.err.OperationalError as e:
            logger.warning(repr(e))
    return inner

class KedroDolt:
    def __init__(self, database, branch: str = "master", port: int = 3306, host: str = "localhost", user: str = "root", password: str = ""):
        self._database = database
        self._user = user
        self._port = port
        self._host = host
        self._password = password

        self._branch = branch
        self._original_branch = None

    @hook_impl
    def before_pipeline_run(self, run_params: Dict[str, Any]):
        if (
                "branch" in run_params["extra_params"] and
                run_params["extra_params"]["branch"] is not None
        ):
            self._branch = run_params["extra_params"]["branch"]
            self._original_branch = self._active_branch()
            self._checkout_branch(self._branch)

    @hook_impl
    def after_pipeline_run(self, run_params: Dict[str, Any]):
        commit_message = self._commit_message(run_params=run_params)
        commit = self._commit(commit_message)
        if self._original_branch is not None:
            self._checkout_branch(self._original_branch)
        return commit

    def connection(self):
        return pymysql.connect(
            host=self._host,
            user=self._user,
            port=self._port,
            password=self._password,
            database=self._database,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def _commit_message(self, run_params: Dict[str, Any]):
        return f"Update from kedro run: {run_params['run_id']}"

    @log_pymysql_error
    def _commit(self, message: str):
        res = None
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"select * from dolt_status")
                status = cursor.fetchone()
                if status is not None:
                    cursor.execute(f"select dolt_commit('-am', '{message}') as c")
                    res = cursor.fetchone()["c"]
                    cursor.execute(f"set @@{self._database}_head = '{res}'")
            connection.commit()
        return res

    @log_pymysql_error
    def _active_branch(self):
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select active_branch() as br")
                res = cursor.fetchone()
                return res["br"]

    @log_pymysql_error
    def _checkout_branch(self, branch: str):
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"select * from dolt_branches where name = '{branch}'")
                res = cursor.fetchone()
                if res is None:
                    cursor.execute(f"select dolt_checkout('-b', '{branch}')")
                else:
                    cursor.execute(f"select dolt_checkout('{branch}')")
            connection.commit()

    @hook_impl
    def register_config_loader(
        self, conf_paths: Iterable[str], env: str, extra_params: Dict[str, Any]
    ) -> ConfigLoader:
        return ConfigLoader(conf_paths)

    @hook_impl
    def register_catalog(
        self,
        catalog: Optional[Dict[str, Dict[str, Any]]],
        credentials: Dict[str, Dict[str, Any]],
        load_versions: Dict[str, str],
        save_version: str,
        journal: Journal,
    ) -> DataCatalog:
        return DataCatalog.from_config(
            catalog, credentials, load_versions, save_version, journal
        )
