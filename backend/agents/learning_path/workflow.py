from ..workflow import build_workflow


def build(reasoner, context, runtime, result_sink):
    return build_workflow("path", reasoner, context, runtime, result_sink)
