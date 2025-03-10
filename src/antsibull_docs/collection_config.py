# Author: Felix Fontein <felix@fontein.de>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or
# https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2021, Ansible Project
"""Handle collection-specific config from docs/docsite/config.yml."""

import asyncio
import os
import os.path
import typing as t
from collections.abc import Mapping

import asyncio_pool  # type: ignore[import]
import pydantic as p
from antsibull_core import app_context
from antsibull_core.logging import log
from antsibull_core.pydantic import forbid_extras, get_formatted_error_messages
from antsibull_fileutils.yaml import load_yaml_file

from .schemas.collection_config import CollectionConfig

mlog = log.fields(mod=__name__)


_ANSIBLE_CORE_CONFIG: dict[str, t.Any] = {}


def get_ansible_core_config() -> CollectionConfig:
    return CollectionConfig.model_validate(_ANSIBLE_CORE_CONFIG)


async def load_collection_config(
    collection_name: str,
    collection_path: str,
) -> CollectionConfig:
    """Given a collection name and path, load config data.

    :arg collection_name: Dotted collection name.
    :arg collection_path: Path to the collection.
    :returns: A CollectionConfig instance.
    """
    flog = mlog.fields(func="load_collection_config")
    flog.debug("Enter")

    if collection_name == "ansible.builtin":
        return get_ansible_core_config()

    try:
        config_path = os.path.join(collection_path, "docs", "docsite", "config.yml")
        if os.path.isfile(config_path):
            try:
                return CollectionConfig.model_validate(load_yaml_file(config_path))
            except p.ValidationError:
                pass
        return CollectionConfig()
    finally:
        flog.debug("Leave")


async def load_collections_configs(
    collection_paths: Mapping[str, str],
) -> Mapping[str, CollectionConfig]:
    """Load config data.

    :arg collection_paths: Mapping of collection_name to the collection's path.
    :returns: A mapping of collection_name to CollectionConfig.
    """
    flog = mlog.fields(func="load_collections_configs")
    flog.debug("Enter")

    loaders = {}
    lib_ctx = app_context.lib_ctx.get()

    async with asyncio_pool.AioPool(size=lib_ctx.thread_max) as pool:
        for collection_name, collection_path in collection_paths.items():
            loaders[collection_name] = await pool.spawn(
                load_collection_config(collection_name, collection_path)
            )

        responses = await asyncio.gather(*loaders.values())

    # Note: Python dicts have always had a stable order as long as you don't modify the dict.
    # So loaders (implicitly, the keys) and responses have a matching order here.
    result = dict(zip(loaders, responses))

    flog.debug("Leave")
    return result


def lint_collection_config(collection_path: str) -> list[tuple[str, int, int, str]]:
    """Given a path, lint config.

    :arg collection_path: Path to the collection.
    :returns: List of tuples (filename, row, column, error) indicating linting errors.
    """
    flog = mlog.fields(func="lint_collection_config")
    flog.debug("Enter")

    result: list[tuple[str, int, int, str]] = []

    forbid_extras(CollectionConfig)

    try:
        config_path = os.path.join(collection_path, "docs", "docsite", "config.yml")
        if not os.path.isfile(config_path):
            return result

        config_data = load_yaml_file(config_path)
        try:
            CollectionConfig.model_validate(config_data)
        except p.ValidationError as exc:
            for message in get_formatted_error_messages(exc):
                result.append((config_path, 0, 0, message))

        return result
    finally:
        flog.debug("Leave")
