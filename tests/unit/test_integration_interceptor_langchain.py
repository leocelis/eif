"""EIFInterceptor works with langchain-core alone (langchain 1.x layout).

Regression: the interceptor imported ``langchain.callbacks.base``, which
langchain 1.x removed, so constructing EIFInterceptor raised
ModuleNotFoundError on a current install; it also required the full
``langchain`` package. The handler must come from langchain_core and must
actually run EIF when a chain ends.
"""

import asyncio

import pytest

pytest.importorskip("langchain_core")

from langchain_core.callbacks.base import BaseCallbackHandler  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402

from eif import session  # noqa: E402
from eif.integration import EIFInterceptor  # noqa: E402


def test_handler_is_a_langchain_core_callback_and_runs_on_chain_end():
    sid = asyncio.run(session.new_session()).session_id
    interceptor = EIFInterceptor(session_id=sid, intercept_chains=True)
    handler = interceptor.get_langchain_handler()
    assert isinstance(handler, BaseCallbackHandler)

    chain = RunnableLambda(lambda _: {"output": "Hollow Ascent has 5,000+ IGDB hype followers."})
    chain.with_config(callbacks=[handler]).invoke("go")

    assert interceptor.last_result is not None
    assert interceptor.last_result["verdict"] in {"PASS", "HALT"}
