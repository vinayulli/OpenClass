"""Preserve tool schemas while routing authorized mutations to the API."""
import functools
import inspect
from .coordinator import request_action


def remote_tool(function, runtime):
    @functools.wraps(function)
    async def call(*args, **kwargs):
        if runtime.get("actions"):
            return runtime["actions"][0]
        arguments = inspect.signature(function).bind(*args, **kwargs)
        arguments.apply_defaults()
        result = await request_action(function.__name__, dict(arguments.arguments))
        runtime["actions"].append(result)
        return result
    return call
