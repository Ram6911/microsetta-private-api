import inspect


def has_non_keyword_arguments(func):
    sig = inspect.signature(func)
    params = sig.parameters
    for p in params:
        if params[p].kind != inspect.Parameter.KEYWORD_ONLY:
            return True


def build_param_map(func, param_names):
    sig = inspect.signature(func)
    params = sig.parameters

    desired_set = set(param_names)

    # Argh.  OrderedDict doesn't know how to find the indexes of its keys.
    output = {}
    for idx, (key, value) in enumerate(params.items()):
        if key in desired_set:
            output[key] = (idx, value.default)
    return output


def bind_param_map(param_map, parameter_overrides, func_args, func_kwargs):
    output = {}
    for key in param_map:
        idx, default = param_map[key]
        if idx < len(func_args):
            output[key] = func_args[idx]
        else:
            output[key] = func_kwargs.get(key, default)

    # TODO: We only use this to set survey_template_id on vioscreen callback
    #  would we prefer defaults instead of overrides?
    if parameter_overrides is not None:
        for key in parameter_overrides:
            output[key] = parameter_overrides[key]
    return output
