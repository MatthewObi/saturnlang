def throw_saturn_error(builder, module, lineno, colno, message):
    text_input = builder.filestack[builder.filestack_idx]
    lines = text_input.splitlines()
    prev_str = "\n"
    if lineno > 1:
        line1 = lines[lineno - 2]
        line2 = lines[lineno - 1]
        prev_str += "%s\n%s\n%s^" % (line1, line2, "~" * (colno - 1))
    else:
        line1 = lines[lineno - 1]
        prev_str += "%s\n%s^" % (line1, "~" * (colno - 1))
    raise RuntimeError("%s\n%s (%d:%d): %s" % (
        prev_str,
        module.filestack[module.filestack_idx],
        lineno,
        colno,
        message
    ))
